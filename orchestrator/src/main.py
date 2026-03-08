"""FastAPI application for MAGI deliberation system.

Endpoints:
- GET  /health          - Health check
- POST /deliberate      - Run full multi-agent deliberation
- GET  /decisions       - List recent decisions
- GET  /decisions/{id}  - Get a specific decision
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[2] / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from orchestrator.src.core.models import DeliberationResult
from orchestrator.src.orchestrator import Deliberator
from orchestrator.src.services.claude_client import ClaudeClient
from orchestrator.src.services.database import DecisionDB

logger = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO)

deliberator: Deliberator | None = None
db: DecisionDB | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global deliberator, db
    claude = ClaudeClient()
    db = DecisionDB()
    await db.initialize()
    deliberator = Deliberator(claude, db)
    logger.info("MAGI system initialized")
    yield
    await claude.close()
    logger.info("MAGI system shut down")


app = FastAPI(title="MAGI Deliberation System", version="0.2.0", lifespan=lifespan)


class DeliberateRequest(BaseModel):
    question: str
    context: str = ""


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.2.0"}


@app.post("/deliberate")
async def deliberate(req: DeliberateRequest) -> dict:
    if not deliberator:
        raise HTTPException(status_code=503, detail="System not initialized")
    result = await deliberator.deliberate(req.question, req.context)
    return result.model_dump(mode="json")


@app.get("/decisions")
async def list_decisions(limit: int = 50) -> list[dict]:
    if not db:
        raise HTTPException(status_code=503, detail="System not initialized")
    results = await db.list_decisions(limit=limit)
    return [r.model_dump(mode="json") for r in results]


@app.get("/decisions/{decision_id}")
async def get_decision(decision_id: str) -> dict:
    if not db:
        raise HTTPException(status_code=503, detail="System not initialized")
    result = await db.get_decision(decision_id)
    if not result:
        raise HTTPException(status_code=404, detail="Decision not found")
    return result.model_dump(mode="json")
