"""Claude API client for MAGI deliberation agents.

Wraps the Anthropic SDK to provide structured vote generation via tool use,
meta-analysis with extended thinking, prompt caching, streaming, and batch support.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

import anthropic

from orchestrator.src.core.models import AgentVote

logger = logging.getLogger(__name__)

VOTE_TOOL = {
    "name": "cast_vote",
    "description": (
        "Cast your structured vote on the question. You MUST call this tool "
        "with your analysis. choice='approve' means you support proceeding, "
        "'reject' means you advise against, 'abstain' means insufficient info."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "choice": {
                "type": "string",
                "enum": ["approve", "reject", "abstain"],
                "description": "Your vote on the question.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "How confident you are in this vote (0.0 to 1.0).",
            },
            "risk_score": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Risk level assessment (0=no risk, 1=extreme risk). Optional.",
            },
            "opportunity_score": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Opportunity level assessment (0=no opportunity, 1=massive opportunity). Optional.",
            },
            "rationale": {
                "type": "string",
                "description": "Your reasoning for this vote. Be specific and concise.",
            },
        },
        "required": ["choice", "confidence", "rationale"],
    },
}

META_SYSTEM_PROMPT = (
    "You are the Meta-Analyst for MAGI, a multi-agent governance system. "
    "Three specialized agents have analyzed a question and cast their votes. "
    "Your job is to synthesize their perspectives into a final recommendation.\n\n"
    "Structure your response as:\n"
    "1. Brief synthesis of the three perspectives\n"
    "2. Points of agreement and disagreement\n"
    "3. Your weighted recommendation (considering each agent's confidence)\n"
    "4. Final one-line recommendation starting with 'RECOMMENDATION:'\n\n"
    "Be direct and actionable. No fluff."
)


class ClaudeClient:
    """Async wrapper around the Anthropic API for agent operations.

    Features:
    - Prompt caching on agent system prompts (~90% savings on repeated calls)
    - Extended thinking on meta-analysis (deeper reasoning via Opus)
    - Streaming support for real-time CLI/SSE output
    - Batch API for non-urgent deliberations (50% cost reduction)
    """

    def __init__(
        self,
        api_key: str | None = None,
        agent_model: str = "claude-sonnet-4-6-20250514",
        meta_model: str = "claude-opus-4-6-20250514",
        thinking_budget: int = 10000,
    ) -> None:
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )
        self.agent_model = agent_model
        self.meta_model = meta_model
        self.thinking_budget = thinking_budget

    # ── Agent voting (Sonnet + prompt caching) ──────────────────────

    async def generate_vote(
        self,
        agent_id: str,
        agent_name: str,
        system_prompt: str,
        question: str,
        context: str = "",
    ) -> AgentVote:
        """Call Claude with tool use and prompt caching to produce a structured AgentVote."""
        user_content = f"**Question to deliberate:**\n{question}"
        if context:
            user_content += f"\n\n**Additional context:**\n{context}"

        logger.info("Requesting vote from %s", agent_name)

        response = await self.client.messages.create(
            model=self.agent_model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[VOTE_TOOL],
            tool_choice={"type": "tool", "name": "cast_vote"},
            messages=[{"role": "user", "content": user_content}],
        )

        # Log cache performance
        if hasattr(response, "usage"):
            usage = response.usage
            cached = getattr(usage, "cache_read_input_tokens", 0)
            if cached:
                logger.info(
                    "%s cache hit: %d tokens read from cache", agent_name, cached
                )

        for block in response.content:
            if block.type == "tool_use" and block.name == "cast_vote":
                vote_data = block.input
                return AgentVote(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    choice=vote_data["choice"],
                    confidence=vote_data["confidence"],
                    risk_score=vote_data.get("risk_score"),
                    opportunity_score=vote_data.get("opportunity_score"),
                    rationale=vote_data["rationale"],
                )

        raise RuntimeError(f"Agent {agent_name} did not produce a vote via tool use")

    # ── Meta-analysis helpers ───────────────────────────────────────

    def _build_meta_messages(
        self,
        question: str,
        votes: list[AgentVote],
        context: str = "",
    ) -> tuple[list[dict], str]:
        """Build system (cached) and user content for meta-analysis."""
        votes_text = "\n\n".join(
            f"**{v.agent_name}** ({v.agent_id}):\n"
            f"- Vote: {v.choice} (confidence: {v.confidence:.0%})\n"
            f"- Risk score: {v.risk_score or 'N/A'}\n"
            f"- Opportunity score: {v.opportunity_score or 'N/A'}\n"
            f"- Rationale: {v.rationale}"
            for v in votes
        )

        system = [
            {
                "type": "text",
                "text": META_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        user_content = f"**Question:** {question}\n\n"
        if context:
            user_content += f"**Context:** {context}\n\n"
        user_content += f"**Agent Votes:**\n\n{votes_text}"

        return system, user_content

    @staticmethod
    def _parse_recommendation(analysis: str) -> tuple[str, str]:
        """Extract recommendation line from analysis text."""
        recommendation = ""
        for line in analysis.split("\n"):
            if line.strip().upper().startswith("RECOMMENDATION:"):
                recommendation = line.strip().split(":", 1)[1].strip()
                break
        if not recommendation:
            recommendation = analysis.split("\n")[-1].strip()
        return analysis, recommendation

    # ── Meta-analysis: standard (extended thinking) ─────────────────

    async def meta_analyze(
        self,
        question: str,
        votes: list[AgentVote],
        context: str = "",
    ) -> tuple[str, str]:
        """Use Claude Opus with extended thinking for deep meta-analysis.

        Returns (full_analysis, recommendation) tuple.
        """
        system, user_content = self._build_meta_messages(question, votes, context)

        logger.info("Requesting meta-analysis with extended thinking (budget=%d)", self.thinking_budget)

        response = await self.client.messages.create(
            model=self.meta_model,
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            },
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )

        # Extract text content (skip thinking blocks)
        analysis = ""
        for block in response.content:
            if block.type == "text":
                analysis += block.text

        if hasattr(response, "usage"):
            usage = response.usage
            cached = getattr(usage, "cache_read_input_tokens", 0)
            logger.info(
                "Meta-analysis usage: input=%d, output=%d, cached=%d",
                usage.input_tokens, usage.output_tokens, cached,
            )

        return self._parse_recommendation(analysis)

    # ── Meta-analysis: streaming ────────────────────────────────────

    async def meta_analyze_stream(
        self,
        question: str,
        votes: list[AgentVote],
        context: str = "",
    ) -> AsyncIterator[str]:
        """Stream meta-analysis with extended thinking. Yields text chunks only."""
        system, user_content = self._build_meta_messages(question, votes, context)

        logger.info("Streaming meta-analysis with extended thinking")

        async with self.client.messages.stream(
            model=self.meta_model,
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            },
            system=system,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    # ── Batch API (50% cost reduction) ──────────────────────────────

    async def create_batch(
        self,
        deliberations: list[dict],
    ) -> str:
        """Submit meta-analyses as a batch for 50% cost reduction.

        Each item: {"id": str, "question": str, "context": str, "votes": list[AgentVote]}
        Returns the batch ID for polling.
        """
        requests = []
        for item in deliberations:
            system, user_content = self._build_meta_messages(
                item["question"], item["votes"], item.get("context", "")
            )
            requests.append({
                "custom_id": item["id"],
                "params": {
                    "model": self.meta_model,
                    "max_tokens": 16000,
                    "thinking": {
                        "type": "enabled",
                        "budget_tokens": self.thinking_budget,
                    },
                    "system": system,
                    "messages": [{"role": "user", "content": user_content}],
                },
            })

        batch = await self.client.messages.batches.create(requests=requests)
        logger.info("Batch created: %s (%d requests)", batch.id, len(requests))
        return batch.id

    async def get_batch_status(self, batch_id: str) -> dict:
        """Check batch processing status."""
        batch = await self.client.messages.batches.retrieve(batch_id)
        return {
            "id": batch.id,
            "status": batch.processing_status,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "counts": {
                "processing": batch.request_counts.processing,
                "succeeded": batch.request_counts.succeeded,
                "errored": batch.request_counts.errored,
                "canceled": batch.request_counts.canceled,
                "expired": batch.request_counts.expired,
            },
        }

    async def get_batch_results(self, batch_id: str) -> list[dict]:
        """Retrieve completed batch results."""
        results = []
        async for result in self.client.messages.batches.results(batch_id):
            if result.result.type == "succeeded":
                analysis = ""
                for block in result.result.message.content:
                    if block.type == "text":
                        analysis += block.text
                analysis_text, recommendation = self._parse_recommendation(analysis)
                results.append({
                    "custom_id": result.custom_id,
                    "analysis": analysis_text,
                    "recommendation": recommendation,
                })
            else:
                results.append({
                    "custom_id": result.custom_id,
                    "error": str(result.result),
                })
        return results

    async def close(self) -> None:
        await self.client.close()
