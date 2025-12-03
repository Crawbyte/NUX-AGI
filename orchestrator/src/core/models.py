"""Core Pydantic models for MAGI-lite orchestrator.

This module defines DecisionBrief, Vote and AgentRationale models used by
the multi-agent deliberation flow. Models include validators, helpful
methods, explicit type hints, docstrings and logging that accepts a
`correlation_id` for traceability in logs.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PositiveInt, ValidationError, validator

logger = logging.getLogger(__name__)


class Vote(BaseModel):
    """Single agent vote.

    Attributes:
        agent_id: Unique identifier for the agent casting the vote.
        choice: One of the canonical choices: 'Ω', 'Λ', or 'Σ'.
        weight: Positive integer weight for the vote (defaults to 1).
        timestamp: When the vote was created (UTC).
    """

    agent_id: str = Field(..., description="Agent unique id")
    choice: str = Field(..., description="Vote choice: 'Ω'|'Λ'|'Σ'")
    weight: PositiveInt = Field(1, description="Weight of the vote (>=1)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @validator("choice")
    def validate_choice(cls, v: str) -> str:
        if v not in {"Ω", "Λ", "Σ"}:
            raise ValueError("choice must be one of 'Ω', 'Λ' or 'Σ'")
        return v


class AgentRationale(BaseModel):
    """Rationale provided by an agent.

    Attributes:
        agent_id: The agent that produced the rationale.
        rationale: Free-text explanation of the decision or vote.
        confidence: Optional confidence score between 0.0 and 1.0.
        timestamp: When the rationale was produced.
    """

    agent_id: str = Field(..., description="Agent unique id")
    rationale: str = Field(..., description="Explanation text")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @validator("rationale")
    def non_empty_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale must not be empty")
        return v


class Votes(BaseModel):
    """Tally of votes by symbol.

    Uses identifiers omega='Ω', lambda='Λ', sigma='Σ' internally but
    exposes clear attribute names. All counts are non-negative integers.
    """

    omega: int = Field(0, ge=0, description="Count for 'Ω'")
    lambda_: int = Field(0, ge=0, alias="lambda", description="Count for 'Λ'")
    sigma: int = Field(0, ge=0, description="Count for 'Σ'")

    class Config:
        allow_population_by_field_name = True

    def total(self) -> int:
        """Return total votes counted."""
        return self.omega + self.lambda_ + self.sigma

    def as_dict(self) -> Dict[str, int]:
        """Return dictionary with symbol keys for easy serialization."""
        return {"Ω": self.omega, "Λ": self.lambda_, "Σ": self.sigma}


class DecisionBrief(BaseModel):
    """Representation of a deliberation item.

    Attributes:
        id: Unique identifier for the brief (UUID4 by default).
        question: The question to deliberate.
        impact: Short description of impact or priority.
        alternatives: Candidate alternatives considered.
        votes: Tally of votes (computed from `votes_list` when provided).
        votes_list: Optional list of individual `Vote` objects.
        rule_applied: Optional rule name used to determine `result`.
        result: Optional result after applying a rule.
        sources: List of source identifiers (documents, urls, etc.).
        traceability: Structured metadata for audit and traceability.
        created_at: Timestamp when the brief was created.
    """

    id: UUID = Field(default_factory=uuid4)
    question: str = Field(..., min_length=1)
    impact: Optional[str] = Field(None)
    alternatives: List[str] = Field(..., min_items=1)
    votes: Votes = Field(default_factory=Votes)
    votes_list: Optional[List[Vote]] = Field(None)
    rule_applied: Optional[str] = Field(None)
    result: Optional[str] = Field(None)
    sources: List[str] = Field(default_factory=list)
    traceability: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @validator("alternatives")
    def check_alternatives_non_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("alternatives must contain at least one option")
        for alt in v:
            if not isinstance(alt, str) or not alt.strip():
                raise ValueError("each alternative must be a non-empty string")
        return v

    @validator("votes", pre=True, always=True)
    def populate_votes_from_list(cls, v: Any, values: Dict[str, Any]) -> Votes:
        """If `votes_list` is provided, compute `Votes` tally automatically.

        This validator runs even when a `votes` object is not provided and
        will compute counts from `votes_list` when present.
        """
        votes_list: Optional[List[Vote]] = values.get("votes_list")
        if votes_list:
            omega = lambda_ = sigma = 0
            for vote in votes_list:
                if not isinstance(vote, Vote):
                    # Pydantic may pass raw dicts; try to coerce
                    try:
                        vote = Vote(**vote)  # type: ignore[arg-type]
                    except ValidationError as exc:
                        raise ValueError(f"invalid vote in votes_list: {exc}")
                if vote.choice == "Ω":
                    omega += int(vote.weight)
                elif vote.choice == "Λ":
                    lambda_ += int(vote.weight)
                elif vote.choice == "Σ":
                    sigma += int(vote.weight)
            return Votes(omega=omega, lambda_=lambda_, sigma=sigma)
        # If user provided `votes` directly, trust it or let Pydantic validate
        if isinstance(v, Votes):
            return v
        if isinstance(v, dict):
            return Votes(**v)
        return Votes()

    def apply_rule(self, rule_name: str, correlation_id: Optional[str] = None) -> None:
        """Apply a named rule to compute and set `result`.

        This method updates `rule_applied` and `result` in-place. The
        implementation here demonstrates a simple majority rule and can be
        extended. All significant steps are logged with the provided
        `correlation_id`.

        Args:
            rule_name: The rule identifier to apply. Currently supported:
                - 'simple_majority': choose alternative by comparing Ω vs Λ vs Σ.
            correlation_id: Optional tracing id to include in logs.
        """
        extra = {"correlation_id": correlation_id} if correlation_id else {}
        logger.debug("Applying rule '%s' to DecisionBrief %s", rule_name, self.id, extra=extra)

        try:
            if rule_name == "simple_majority":
                tally = self.votes.as_dict()
                # choose symbol with max votes
                winning_symbol = max(tally.items(), key=lambda kv: kv[1])[0]
                # Map winning symbol to an alternative index if possible
                # Here we assume alternatives align with symbols in order: Ω, Λ, Σ
                symbol_to_index = {"Ω": 0, "Λ": 1, "Σ": 2}
                idx = symbol_to_index.get(winning_symbol, 0)
                if idx < len(self.alternatives):
                    self.result = self.alternatives[idx]
                else:
                    # Fallback: join symbol counts into a short summary
                    self.result = f"No matching alternative for symbol {winning_symbol}; tally={tally}"
            else:
                raise ValueError(f"unsupported rule: {rule_name}")
            self.rule_applied = rule_name
            logger.info("Rule applied '%s' result: %s", rule_name, self.result, extra=extra)
        except Exception as exc:  # broad to ensure model remains consistent
            logger.error("Error applying rule '%s': %s", rule_name, exc, extra=extra)
            raise

    def to_dict(self, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a serializable dict representation, logging the operation.

        Args:
            correlation_id: Optional ID to include in logs for traceability.
        """
        extra = {"correlation_id": correlation_id} if correlation_id else {}
        logger.debug("Serializing DecisionBrief %s", str(self.id), extra=extra)
        # Pydantic's .dict() is safe but normalize Votes to symbol keys
        base = self.dict(exclude={"votes"}, by_alias=True)
        base["votes"] = self.votes.as_dict()
        return base
