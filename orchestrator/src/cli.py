"""CLI entry point for MAGI deliberation system.

Usage:
    python -m orchestrator.src.cli "Should I invest in this startup?"
    python -m orchestrator.src.cli "Should I change jobs?" --context "Current role: senior dev, 3 years"
    python -m orchestrator.src.cli "Should I change jobs?" --stream
    python -m orchestrator.src.cli --batch questions.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
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
from orchestrator.src.services.mcp_context import MCPContextProvider


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


def format_vote_live(vote) -> str:
    """Format a single vote for live streaming output."""
    conf = f"{vote.confidence:.0%}"
    parts = [f"  [{vote.agent_name}] {vote.choice.upper()} (confidence: {conf})"]
    if vote.risk_score is not None:
        parts.append(f"    Risk: {vote.risk_score:.0%}")
    if vote.opportunity_score is not None:
        parts.append(f"    Opportunity: {vote.opportunity_score:.0%}")
    parts.append(f"    {vote.rationale}")
    return "\n".join(parts)


async def run_standard(deliberator: Deliberator, question: str, context: str) -> int:
    """Standard (non-streaming) deliberation."""
    print(f"\nDeliberating: {question}\n")
    print("Running agents Omega, Lambda, Sigma in parallel...\n")
    result = await deliberator.deliberate(question, context)
    print(format_result(result))
    return 0


async def run_stream(deliberator: Deliberator, question: str, context: str) -> int:
    """Streaming deliberation with live progress."""
    print(f"\nDeliberating: {question}\n")
    print("=" * 60)
    print("AGENT VOTES (streaming as they complete)")
    print("=" * 60)

    async for event_type, data in deliberator.deliberate_stream(question, context):
        if event_type == "vote":
            print(format_vote_live(data))
            print()

        elif event_type == "thinking":
            print("-" * 60)
            print("META-ANALYSIS (Opus extended thinking)")
            print("-" * 60)

        elif event_type == "meta_chunk":
            print(data, end="", flush=True)

        elif event_type == "result":
            print("\n")
            print("=" * 60)
            print(f"RECOMMENDATION: {data.recommendation}")
            print("=" * 60)
            print(f"\n(Decision ID: {data.id})")

    return 0


async def run_batch(deliberator: Deliberator, batch_file: str) -> int:
    """Submit batch deliberation from a JSON file."""
    path = Path(batch_file)
    if not path.exists():
        print(f"Error: file not found: {batch_file}", file=sys.stderr)
        return 1

    items = json.loads(path.read_text())
    if not isinstance(items, list):
        print("Error: batch file must contain a JSON array", file=sys.stderr)
        return 1

    print(f"\nSubmitting batch of {len(items)} deliberations...")
    print("Agent votes running now (Sonnet)...")

    batch_id = await deliberator.deliberate_batch(items)

    print(f"\nBatch submitted successfully!")
    print(f"  Batch ID: {batch_id}")
    print(f"  Items: {len(items)}")
    print(f"  Cost: 50% discount (Batch API)")
    print(f"\nCheck status:")
    print(f"  python -m orchestrator.src.cli --batch-status {batch_id}")

    return 0


async def run_batch_status(client: ClaudeClient, batch_id: str) -> int:
    """Check batch status and print results if complete."""
    status = await client.get_batch_status(batch_id)
    print(f"\nBatch: {status['id']}")
    print(f"Status: {status['status']}")
    print(f"Counts: {json.dumps(status['counts'], indent=2)}")

    if status["status"] == "ended":
        print("\nResults:")
        print("-" * 60)
        results = await client.get_batch_results(batch_id)
        for r in results:
            print(f"\n[{r['custom_id']}]")
            if "error" in r:
                print(f"  Error: {r['error']}")
            else:
                print(f"  Recommendation: {r['recommendation']}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="MAGI - Multi-Agent Governance Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("question", nargs="?", help="The question to deliberate")
    parser.add_argument("--context", default="", help="Additional context for the decision")
    parser.add_argument("--stream", action="store_true", help="Stream results in real-time")
    parser.add_argument("--batch", metavar="FILE", help="Submit batch from JSON file")
    parser.add_argument("--batch-status", metavar="ID", help="Check batch status by ID")
    parser.add_argument("--thinking-budget", type=int, default=10000, help="Extended thinking token budget (default: 10000)")
    parser.add_argument("--mcp", action="store_true", help="Enrich context via MCP (Calendar, Gmail, Drive, GitHub)")
    parser.add_argument("--mcp-config", metavar="PATH", help="Path to mcp_config.json (default: orchestrator/mcp_config.json)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    client = ClaudeClient(thinking_budget=args.thinking_budget)
    db = DecisionDB()
    await db.initialize()

    try:
        if args.batch_status:
            return await run_batch_status(client, args.batch_status)

        mcp = MCPContextProvider(args.mcp_config) if args.mcp else None
        deliberator = Deliberator(client, db, mcp=mcp)

        if args.batch:
            return await run_batch(deliberator, args.batch)

        if not args.question:
            parser.error("question is required (or use --batch/--batch-status)")

        if args.stream:
            return await run_stream(deliberator, args.question, args.context)

        return await run_standard(deliberator, args.question, args.context)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
