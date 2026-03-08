"""Core Pydantic v2 models for MAGI deliberation system.

Defines models for agent voting, deliberation briefs, and structured
outputs from Claude tool use.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class AgentVote(BaseModel):
    """Structured vote produced by a Claude agent via tool use."""

    agent_id: str
    agent_name: str
    choice: Literal["approve", "reject", "abstain"]
    confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float | None = Field(None, ge=0.0, le=1.0)
    opportunity_score: float | None = Field(None, ge=0.0, le=1.0)
    rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("rationale")
    @classmethod
    def non_empty_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale must not be empty")
        return v


class Vote(BaseModel):
    """Legacy single agent vote (kept for backward compatibility)."""

    agent_id: str = Field(..., description="Agent unique id")
    choice: str = Field(..., description="Vote choice: 'Ω'|'Λ'|'Σ'")
    weight: int = Field(1, gt=0, description="Weight of the vote (>=1)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("choice")
    @classmethod
    def validate_choice(cls, v: str) -> str:
        if v not in {"Ω", "Λ", "Σ"}:
            raise ValueError("choice must be one of 'Ω', 'Λ' or 'Σ'")
        return v


class AgentRationale(BaseModel):
    """Rationale provided by an agent."""

    agent_id: str = Field(..., description="Agent unique id")
    rationale: str = Field(..., description="Explanation text")
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("rationale")
    @classmethod
    def non_empty_rationale(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale must not be empty")
        return v


class Votes(BaseModel):
    """Tally of votes by symbol."""

    model_config = ConfigDict(populate_by_name=True)

    omega: int = Field(0, ge=0, description="Count for 'Ω'")
    lambda_: int = Field(0, ge=0, alias="lambda", description="Count for 'Λ'")
    sigma: int = Field(0, ge=0, description="Count for 'Σ'")

    def total(self) -> int:
        return self.omega + self.lambda_ + self.sigma

    def as_dict(self) -> dict[str, int]:
        return {"Ω": self.omega, "Λ": self.lambda_, "Σ": self.sigma}


class DecisionBrief(BaseModel):
    """Representation of a deliberation item."""

    id: UUID = Field(default_factory=uuid4)
    question: str = Field(..., min_length=1)
    impact: str | None = None
    alternatives: list[str] = Field(..., min_length=1)
    votes: Votes = Field(default_factory=Votes)
    votes_list: list[Vote] | None = None
    rule_applied: str | None = None
    result: str | None = None
    sources: list[str] = Field(default_factory=list)
    traceability: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("alternatives")
    @classmethod
    def check_alternatives_non_empty(cls, v: list[str]) -> list[str]:
        for alt in v:
            if not isinstance(alt, str) or not alt.strip():
                raise ValueError("each alternative must be a non-empty string")
        return v

    @model_validator(mode="before")
    @classmethod
    def populate_votes_from_list(cls, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return data
        votes_list = data.get("votes_list")
        if votes_list:
            omega = lambda_ = sigma = 0
            for vote in votes_list:
                if isinstance(vote, dict):
                    choice = vote.get("choice", "")
                    weight = int(vote.get("weight", 1))
                elif isinstance(vote, Vote):
                    choice = vote.choice
                    weight = vote.weight
                else:
                    continue
                if choice == "Ω":
                    omega += weight
                elif choice == "Λ":
                    lambda_ += weight
                elif choice == "Σ":
                    sigma += weight
            data["votes"] = {"omega": omega, "lambda": lambda_, "sigma": sigma}
        return data

    def apply_rule(self, rule_name: str, correlation_id: str | None = None) -> None:
        extra = {"correlation_id": correlation_id} if correlation_id else {}

        if rule_name == "simple_majority":
            tally = self.votes.as_dict()
            winning_symbol = max(tally.items(), key=lambda kv: kv[1])[0]
            symbol_to_index = {"Ω": 0, "Λ": 1, "Σ": 2}
            idx = symbol_to_index.get(winning_symbol, 0)
            if idx < len(self.alternatives):
                self.result = self.alternatives[idx]
            else:
                self.result = f"No matching alternative for {winning_symbol}; tally={tally}"
        else:
            raise ValueError(f"unsupported rule: {rule_name}")

        self.rule_applied = rule_name
        logger.info("Rule applied '%s' result: %s", rule_name, self.result, extra=extra)

    def to_dict(self, correlation_id: str | None = None) -> dict[str, Any]:
        extra = {"correlation_id": correlation_id} if correlation_id else {}
        logger.debug("Serializing DecisionBrief %s", str(self.id), extra=extra)
        base = self.model_dump(exclude={"votes"}, by_alias=True)
        base["votes"] = self.votes.as_dict()
        return base


class DeliberationResult(BaseModel):
    """Final result of a multi-agent deliberation."""

    id: UUID = Field(default_factory=uuid4)
    question: str
    context: str = ""
    agent_votes: list[AgentVote]
    meta_analysis: str
    recommendation: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def summary(self) -> str:
        lines = [f"Question: {self.question}", ""]
        for v in self.agent_votes:
            lines.append(f"  [{v.agent_name}] {v.choice} (confidence: {v.confidence:.0%})")
            lines.append(f"    {v.rationale}")
        lines.append("")
        lines.append(f"Recommendation: {self.recommendation}")
        return "\n".join(lines)
