"""Abstract base class for agents in MAGI-lite.

Defines the interface every agent should implement: producing a `Vote`
and an `AgentRationale` for a given `DecisionBrief`. Includes helpers
for consistent logging with `correlation_id` and a small `AgentError`
exception type for agent-level failures.
"""
from __future__ import annotations

import abc
import logging
from typing import Any, Dict, Optional

from orchestrator.src.core.models import AgentRationale, DecisionBrief, Vote

logger = logging.getLogger("orchestrator.agent")


class AgentError(Exception):
    """Generic exception raised for agent-specific failures."""


class BaseAgent(abc.ABC):
    """Abstract base agent.

    Subclasses must implement `decide` and `rationale` which encapsulate
    the agent's decision-making and explanation logic. Implementations
    should be asynchronous-friendly because agents may call external
    services (LLMs, databases, etc.).

    Attributes:
        agent_id: Unique id for the agent.
        name: Human-friendly name.
        logger: Logger instance to use; if None, the module logger is used.
    """

    def __init__(self, agent_id: str, name: Optional[str] = None, logger_: Optional[logging.Logger] = None) -> None:
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self.agent_id: str = agent_id
        self.name: str = name or agent_id
        self.logger: logging.Logger = logger_ or logger

    def _log(self, level: int, msg: str, correlation_id: Optional[str] = None, **kwargs: Any) -> None:
        """Helper to log messages including `correlation_id` in the extra dict.

        Args:
            level: Logging level (e.g., logging.INFO).
            msg: Message format string.
            correlation_id: Optional correlation id for traceability.
            kwargs: Additional attributes to include in `extra`.
        """
        extra = {"agent_id": self.agent_id}
        if correlation_id:
            extra["correlation_id"] = correlation_id
        extra.update(kwargs or {})
        self.logger.log(level, msg, extra=extra)

    @abc.abstractmethod
    async def decide(self, brief: DecisionBrief, correlation_id: Optional[str] = None) -> Vote:
        """Produce a `Vote` for the supplied `DecisionBrief`.

        Implementations must return a validated `Vote` instance. Any
        exceptions should raise `AgentError` or let higher-level code
        handle them.

        Args:
            brief: The `DecisionBrief` to consider.
            correlation_id: Optional id for tracing logs across services.

        Returns:
            A `Vote` instance representing the agent's choice.
        """

    @abc.abstractmethod
    async def rationale(self, brief: DecisionBrief, correlation_id: Optional[str] = None) -> AgentRationale:
        """Return an `AgentRationale` explaining the agent's decision.

        This should be concise and, if available, include a `confidence`
        score between 0.0 and 1.0.
        """

    async def run(self, brief: DecisionBrief, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Convenience runner that executes `decide` and `rationale`.

        Returns a dict with keys `vote` and `rationale`.
        """
        try:
            self._log(logging.DEBUG, "Agent run start", correlation_id=correlation_id)
            vote = await self.decide(brief, correlation_id=correlation_id)
            rationale = await self.rationale(brief, correlation_id=correlation_id)

            if not isinstance(vote, Vote):
                raise AgentError(f"decide() must return Vote, got {type(vote)}")
            if not isinstance(rationale, AgentRationale):
                raise AgentError(f"rationale() must return AgentRationale, got {type(rationale)}")

            self._log(logging.INFO, "Agent run completed", correlation_id=correlation_id, vote=vote.dict(), rationale=rationale.dict())
            return {"vote": vote, "rationale": rationale}

        except Exception as exc:
            self._log(logging.ERROR, "Agent run failed: %s", correlation_id=correlation_id, exc=exc)
            # Wrap unexpected exceptions in AgentError to provide a consistent API
            if isinstance(exc, AgentError):
                raise
            raise AgentError(str(exc)) from exc
