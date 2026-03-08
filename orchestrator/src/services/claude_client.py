"""Claude API client for MAGI deliberation agents.

Wraps the Anthropic SDK to provide structured vote generation via tool use
and meta-analysis via plain text generation.
"""
from __future__ import annotations

import logging
import os

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


class ClaudeClient:
    """Async wrapper around the Anthropic API for agent operations."""

    def __init__(
        self,
        api_key: str | None = None,
        agent_model: str = "claude-sonnet-4-20250514",
        meta_model: str = "claude-opus-4-20250514",
    ) -> None:
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )
        self.agent_model = agent_model
        self.meta_model = meta_model

    async def generate_vote(
        self,
        agent_id: str,
        agent_name: str,
        system_prompt: str,
        question: str,
        context: str = "",
    ) -> AgentVote:
        """Call Claude with tool use to produce a structured AgentVote."""
        user_content = f"**Question to deliberate:**\n{question}"
        if context:
            user_content += f"\n\n**Additional context:**\n{context}"

        logger.info("Requesting vote from %s", agent_name)

        response = await self.client.messages.create(
            model=self.agent_model,
            max_tokens=1024,
            system=system_prompt,
            tools=[VOTE_TOOL],
            tool_choice={"type": "tool", "name": "cast_vote"},
            messages=[{"role": "user", "content": user_content}],
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

    async def meta_analyze(
        self,
        question: str,
        votes: list[AgentVote],
        context: str = "",
    ) -> tuple[str, str]:
        """Use Claude for meta-analysis of all agent votes.

        Returns (full_analysis, recommendation) tuple.
        """
        votes_text = "\n\n".join(
            f"**{v.agent_name}** ({v.agent_id}):\n"
            f"- Vote: {v.choice} (confidence: {v.confidence:.0%})\n"
            f"- Risk score: {v.risk_score or 'N/A'}\n"
            f"- Opportunity score: {v.opportunity_score or 'N/A'}\n"
            f"- Rationale: {v.rationale}"
            for v in votes
        )

        system = (
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

        user_content = f"**Question:** {question}\n\n"
        if context:
            user_content += f"**Context:** {context}\n\n"
        user_content += f"**Agent Votes:**\n\n{votes_text}"

        logger.info("Requesting meta-analysis")

        response = await self.client.messages.create(
            model=self.meta_model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )

        analysis = response.content[0].text

        recommendation = ""
        for line in analysis.split("\n"):
            if line.strip().upper().startswith("RECOMMENDATION:"):
                recommendation = line.strip().split(":", 1)[1].strip()
                break

        if not recommendation:
            recommendation = analysis.split("\n")[-1].strip()

        return analysis, recommendation

    async def close(self) -> None:
        await self.client.close()
