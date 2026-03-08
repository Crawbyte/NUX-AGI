"""SQLite persistence for deliberation results."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

from orchestrator.src.core.models import AgentVote, DeliberationResult

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "decisions.db"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    context TEXT DEFAULT '',
    agent_votes TEXT NOT NULL,
    meta_analysis TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class DecisionDB:
    """Async SQLite storage for deliberation results."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or DEFAULT_DB_PATH)

    async def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(CREATE_TABLE)
            await db.commit()
        logger.info("Database initialized at %s", self.db_path)

    async def save_decision(self, result: DeliberationResult) -> str:
        votes_json = json.dumps(
            [v.model_dump(mode="json") for v in result.agent_votes]
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO decisions (id, question, context, agent_votes, meta_analysis, recommendation, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(result.id),
                    result.question,
                    result.context,
                    votes_json,
                    result.meta_analysis,
                    result.recommendation,
                    result.created_at.isoformat(),
                ),
            )
            await db.commit()
        logger.info("Saved decision %s", result.id)
        return str(result.id)

    async def get_decision(self, decision_id: str) -> DeliberationResult | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM decisions WHERE id = ?", (decision_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_result(row)

    async def list_decisions(self, limit: int = 50) -> list[DeliberationResult]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [_row_to_result(r) for r in rows]


def _row_to_result(row: aiosqlite.Row) -> DeliberationResult:
    votes_data = json.loads(row["agent_votes"])
    return DeliberationResult(
        id=row["id"],
        question=row["question"],
        context=row["context"],
        agent_votes=[AgentVote(**v) for v in votes_data],
        meta_analysis=row["meta_analysis"],
        recommendation=row["recommendation"],
        created_at=row["created_at"],
    )
