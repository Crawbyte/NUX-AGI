"""Abstract base class for MAGI deliberation agents."""
from __future__ import annotations

import abc
import logging
from typing import Any

from orchestrator.src.core.models import AgentVote

logger = logging.getLogger("orchestrator.agent")


class AgentError(Exception):
    """Exception raised for agent-specific failures."""


class BaseAgent(abc.ABC):
    """Abstract base agent for the MAGI deliberation system.

    Each agent has a unique perspective defined by its system prompt.
    Agents produce structured votes via Claude tool use.
    """

    def __init__(self, agent_id: str, name: str) -> None:
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self.agent_id = agent_id
        self.name = name

    @property
    @abc.abstractmethod
    def system_prompt(self) -> str:
        """The system prompt that defines this agent's perspective."""

    async def run(
        self,
        question: str,
        context: str,
        claude_client: Any,
    ) -> AgentVote:
        """Execute the agent: call Claude with this agent's persona and return a vote."""
        try:
            logger.info("Agent %s starting deliberation", self.name)
            vote = await claude_client.generate_vote(
                agent_id=self.agent_id,
                agent_name=self.name,
                system_prompt=self.system_prompt,
                question=question,
                context=context,
            )
            logger.info("Agent %s voted: %s (confidence: %.0f%%)", self.name, vote.choice, vote.confidence * 100)
            return vote
        except Exception as exc:
            logger.error("Agent %s failed: %s", self.name, exc)
            raise AgentError(f"Agent {self.name} failed: {exc}") from exc
