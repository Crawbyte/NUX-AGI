#!/usr/bin/env python3
"""Quick runnable test for Pydantic v2 models in MAGI.

Usage:
    python orchestrator/tests/run_models_quick.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.src.core.models import (
    AgentRationale,
    AgentVote,
    DecisionBrief,
    DeliberationResult,
    Vote,
)


def run() -> int:
    try:
        # Test AgentVote (new model)
        vote = AgentVote(
            agent_id="omega",
            agent_name="Omega (Risk Analyst)",
            choice="reject",
            confidence=0.85,
            risk_score=0.7,
            rationale="High risk due to market uncertainty.",
        )
        print("AgentVote:", vote.model_dump(mode="json"))
        assert vote.choice == "reject"
        assert vote.confidence == 0.85
        print("AgentVote OK")

        # Test DeliberationResult (new model)
        result = DeliberationResult(
            question="Should we proceed?",
            agent_votes=[
                AgentVote(agent_id="omega", agent_name="Omega", choice="reject", confidence=0.8, rationale="Too risky"),
                AgentVote(agent_id="lambda", agent_name="Lambda", choice="approve", confidence=0.9, rationale="Great opportunity"),
                AgentVote(agent_id="sigma", agent_name="Sigma", choice="approve", confidence=0.6, rationale="On balance, yes"),
            ],
            meta_analysis="Two agents approve, one rejects. Opportunity outweighs risk.",
            recommendation="Proceed with caution.",
        )
        print("\nDeliberationResult summary:")
        print(result.summary())
        assert len(result.agent_votes) == 3
        print("DeliberationResult OK")

        # Test legacy DecisionBrief with votes_list
        brief = DecisionBrief(
            question="Which option is best?",
            alternatives=["Option A", "Option B", "Option C"],
            votes_list=[
                {"agent_id": "agent1", "choice": "Ω", "weight": 2},
                {"agent_id": "agent2", "choice": "Λ", "weight": 1},
                {"agent_id": "agent3", "choice": "Λ", "weight": 1},
            ],
            sources=["doc:requirements"],
        )
        tally = brief.votes.as_dict()
        assert tally == {"Ω": 2, "Λ": 2, "Σ": 0}, f"unexpected tally: {tally}"
        print("\nDecisionBrief tally OK:", tally)

        brief.apply_rule("simple_majority", correlation_id="test-run-1")
        print("Applied rule, result:", brief.result)

        # Roundtrip serialization
        data = brief.to_dict()
        recreated = DecisionBrief(**data)
        assert recreated.votes.as_dict() == brief.votes.as_dict()
        print("Roundtrip OK")

        # Legacy models
        rationale = AgentRationale(agent_id="agent1", rationale="I prefer A due to X.")
        legacy_vote = Vote(agent_id="agent1", choice="Ω", weight=1)
        print("\nAgentRationale:", rationale.model_dump())
        print("Vote:", legacy_vote.model_dump())

        print("\n--- ALL TESTS PASSED ---")
        return 0

    except Exception:
        print("ERROR during model quick test:")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(run())
