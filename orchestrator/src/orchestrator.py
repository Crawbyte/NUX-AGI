"""Core deliberation engine that runs agents in parallel and synthesizes results."""
from __future__ import annotations

import asyncio
import logging

from orchestrator.src.agents import LambdaAgent, OmegaAgent, SigmaAgent
from orchestrator.src.core.models import AgentVote, DeliberationResult
from orchestrator.src.services.claude_client import ClaudeClient
from orchestrator.src.services.database import DecisionDB

logger = logging.getLogger(__name__)


class Deliberator:
    """Runs the full MAGI deliberation pipeline.

    1. Three agents analyze the question in parallel (Claude Sonnet)
    2. Meta-analyst synthesizes all votes (Claude Opus)
    3. Result is persisted to SQLite
    """

    def __init__(self, claude_client: ClaudeClient, db: DecisionDB) -> None:
        self.agents = [OmegaAgent(), LambdaAgent(), SigmaAgent()]
        self.claude = claude_client
        self.db = db

    async def deliberate(
        self,
        question: str,
        context: str = "",
    ) -> DeliberationResult:
        logger.info("Starting deliberation: %s", question[:80])

        # Phase 1: Run all agents in parallel
        votes: list[AgentVote] = await asyncio.gather(
            *[agent.run(question, context, self.claude) for agent in self.agents]
        )

        logger.info(
            "All agents voted: %s",
            ", ".join(f"{v.agent_name}={v.choice}" for v in votes),
        )

        # Phase 2: Meta-analysis with Claude Opus
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
