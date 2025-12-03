#!/usr/bin/env python3
"""Quick runnable test for Pydantic models in MAGI-lite.

This script exercises `DecisionBrief`, `Vote`, `Votes` and `AgentRationale`
without requiring FastAPI. It's intended to be runnable after installing
the project's Python dependencies (e.g., in a virtualenv).

Usage:
    python orchestrator/tests/run_models_quick.py

The script prints useful diagnostics and exits with a non-zero code on failure.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Dict

# Ensure repository root is on sys.path so `orchestrator` package resolves
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from orchestrator.src.core.models import AgentRationale, DecisionBrief, Vote
except ModuleNotFoundError as exc:
    print("Module import error:", exc)
    print("Make sure you run this script from the repo root and that dependencies are installed:")
    print("  python3 -m venv .venv && source .venv/bin/activate && pip install -r orchestrator/requirements.txt")
    raise


def run() -> int:
    try:
        # Build a DecisionBrief with a few votes
        brief = DecisionBrief(
            question="Which option is best?",
            alternatives=["Option A", "Option B", "Option C"],
            votes_list=[
                {"agent_id": "agent1", "choice": "Ω", "weight": 2},
                {"agent_id": "agent2", "choice": "Λ", "weight": 1},
                {"agent_id": "agent3", "choice": "Λ", "weight": 1},
            ],
            sources=["doc:requirements", "url:https://example.com/context"],
            traceability={"created_by": "run_models_quick"},
        )

        print("Created DecisionBrief:")
        print(brief.to_dict(correlation_id="test-run-1"))

        # Verify votes tally
        tally: Dict[str, int] = brief.votes.as_dict()
        assert tally == {"Ω": 2, "Λ": 2, "Σ": 0}, f"unexpected tally: {tally}"
        print("Votes tally OK:", tally)

        # Apply a simple majority rule
        brief.apply_rule("simple_majority", correlation_id="test-run-1")
        print("Applied rule, result:", brief.result)

        # Round-trip serialization
        data = brief.to_dict(correlation_id="test-run-1")
        recreated = DecisionBrief(**data)
        assert recreated.votes.as_dict() == brief.votes.as_dict()
        print("Roundtrip serialization OK")

        # Test AgentRationale and Vote model direct usage
        rationale = AgentRationale(agent_id="agent1", rationale="I prefer A due to X.")
        vote = Vote(agent_id="agent1", choice="Ω", weight=1)
        print("AgentRationale:", rationale.dict())
        print("Vote:", vote.dict())

        return 0

    except Exception as exc:
        print("ERROR during model quick test:")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(run())
