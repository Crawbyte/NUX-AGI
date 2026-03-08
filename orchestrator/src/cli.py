"""CLI entry point for MAGI deliberation system.

Usage:
    python -m orchestrator.src.cli "Should I invest in this startup?"
    python -m orchestrator.src.cli "Should I change jobs?" --context "Current role: senior dev, 3 years tenure"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parents[2] / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)

from orchestrator.src.orchestrator import Deliberator
from orchestrator.src.services.claude_client import ClaudeClient
from orchestrator.src.services.database import DecisionDB


def format_result(result) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("MAGI DELIBERATION RESULT")
    lines.append("=" * 60)
    lines.append(f"\nQuestion: {result.question}")
    if result.context:
        lines.append(f"Context: {result.context}")
    lines.append("")

    for v in result.agent_votes:
        conf = f"{v.confidence:.0%}"
        lines.append(f"--- {v.agent_name} ---")
        lines.append(f"  Vote: {v.choice.upper()} (confidence: {conf})")
        if v.risk_score is not None:
            lines.append(f"  Risk: {v.risk_score:.0%}")
        if v.opportunity_score is not None:
            lines.append(f"  Opportunity: {v.opportunity_score:.0%}")
        lines.append(f"  Rationale: {v.rationale}")
        lines.append("")

    lines.append("-" * 60)
    lines.append("META-ANALYSIS")
    lines.append("-" * 60)
    lines.append(result.meta_analysis)
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"RECOMMENDATION: {result.recommendation}")
    lines.append("=" * 60)
    lines.append(f"\n(Decision ID: {result.id})")

    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="MAGI - Multi-Agent Governance Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("question", help="The question to deliberate")
    parser.add_argument("--context", default="", help="Additional context for the decision")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    client = ClaudeClient()
    db = DecisionDB()
    await db.initialize()

    try:
        deliberator = Deliberator(client, db)
        print(f"\nDeliberating: {args.question}\n")
        print("Running agents Omega, Lambda, Sigma in parallel...\n")
        result = await deliberator.deliberate(args.question, args.context)
        print(format_result(result))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
