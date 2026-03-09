"""Core deliberation engine that runs agents in parallel and synthesizes results."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from orchestrator.src.agents import LambdaAgent, OmegaAgent, SigmaAgent
from orchestrator.src.core.models import AgentVote, DeliberationResult
from orchestrator.src.services.claude_client import ClaudeClient
from orchestrator.src.services.database import DecisionDB
from orchestrator.src.services.mcp_context import MCPContextProvider

logger = logging.getLogger(__name__)


class Deliberator:
    """Runs the full MAGI deliberation pipeline.

    1. (Optional) Enrich context via MCP (Calendar, Gmail, Drive, GitHub)
    2. Three agents analyze the question in parallel (Claude Sonnet 4.6)
    3. Meta-analyst synthesizes all votes with extended thinking (Claude Opus 4.6)
    4. Result is persisted to SQLite

    Supports standard, streaming, and batch modes.
    """

    def __init__(
        self,
        claude_client: ClaudeClient,
        db: DecisionDB,
        mcp: MCPContextProvider | None = None,
    ) -> None:
        self.agents = [OmegaAgent(), LambdaAgent(), SigmaAgent()]
        self.claude = claude_client
        self.db = db
        self.mcp = mcp

    async def _enrich_context(self, question: str, context: str) -> str:
        """Enrich context via MCP if available."""
        if self.mcp and self.mcp.enabled:
            logger.info("Enriching context via MCP...")
            return await self.mcp.gather_context(question, context)
        return context

    async def deliberate(
        self,
        question: str,
        context: str = "",
    ) -> DeliberationResult:
        """Standard deliberation: run agents, meta-analyze, persist."""
        logger.info("Starting deliberation: %s", question[:80])

        # Phase 0: Enrich context via MCP (Calendar, Gmail, Drive, GitHub)
        context = await self._enrich_context(question, context)

        # Phase 1: Run all agents in parallel
        votes: list[AgentVote] = await asyncio.gather(
            *[agent.run(question, context, self.claude) for agent in self.agents]
        )

        logger.info(
            "All agents voted: %s",
            ", ".join(f"{v.agent_name}={v.choice}" for v in votes),
        )

        # Phase 2: Meta-analysis with Claude Opus (extended thinking)
        analysis, recommendation = await self.claude.meta_analyze(
            question, votes, context
        )

        # Phase 3: Build and persist result
        result = DeliberationResult(
            question=question,
            context=context,
            agent_votes=votes,
            meta_analysis=analysis,
            recommendation=recommendation,
        )

        await self.db.save_decision(result)
        logger.info("Deliberation complete: %s -> %s", result.id, recommendation[:80])

        return result

    async def deliberate_stream(
        self,
        question: str,
        context: str = "",
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """Streaming deliberation: yields events as they happen.

        Events:
        - ("vote", AgentVote) — emitted as each agent completes
        - ("thinking", None) — meta-analysis thinking started
        - ("meta_chunk", str) — streaming text chunk from meta-analysis
        - ("result", DeliberationResult) — final persisted result
        """
        logger.info("Starting streaming deliberation: %s", question[:80])

        # Phase 0: Enrich context via MCP
        context = await self._enrich_context(question, context)

        # Phase 1: Run agents, yield votes as they complete
        tasks = [
            asyncio.create_task(agent.run(question, context, self.claude))
            for agent in self.agents
        ]

        votes: list[AgentVote] = []
        for coro in asyncio.as_completed(tasks):
            vote = await coro
            votes.append(vote)
            yield ("vote", vote)

        logger.info(
            "All agents voted: %s",
            ", ".join(f"{v.agent_name}={v.choice}" for v in votes),
        )

        # Phase 2: Stream meta-analysis
        yield ("thinking", None)

        full_analysis_parts: list[str] = []
        async for chunk in self.claude.meta_analyze_stream(question, votes, context):
            full_analysis_parts.append(chunk)
            yield ("meta_chunk", chunk)

        # Phase 3: Build and persist result
        full_analysis = "".join(full_analysis_parts)
        _, recommendation = ClaudeClient._parse_recommendation(full_analysis)

        result = DeliberationResult(
            question=question,
            context=context,
            agent_votes=votes,
            meta_analysis=full_analysis,
            recommendation=recommendation,
        )

        await self.db.save_decision(result)
        logger.info("Deliberation complete: %s -> %s", result.id, recommendation[:80])

        yield ("result", result)

    async def deliberate_batch(
        self,
        items: list[dict],
    ) -> str:
        """Submit multiple deliberations as a batch (50% cost savings).

        Each item: {"question": str, "context": str}
        Returns batch_id for polling.

        Agent votes run immediately (cheap Sonnet calls), only
        the expensive Opus meta-analyses are batched.
        """
        logger.info("Starting batch deliberation for %d items", len(items))

        # Phase 1: Run agent votes for all questions in parallel
        async def get_votes(item: dict) -> dict:
            question = item["question"]
            context = item.get("context", "")
            votes = await asyncio.gather(
                *[agent.run(question, context, self.claude) for agent in self.agents]
            )
            return {
                "id": f"delib-{hash(question) & 0xFFFFFFFF:08x}",
                "question": question,
                "context": context,
                "votes": list(votes),
            }

        deliberations = await asyncio.gather(*[get_votes(item) for item in items])

        # Phase 2: Submit all meta-analyses as a batch
        batch_id = await self.claude.create_batch(list(deliberations))
        logger.info("Batch submitted: %s", batch_id)

        return batch_id
