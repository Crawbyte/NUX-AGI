"""FastAPI application for MAGI deliberation system.

Endpoints:
- GET  /health              - Health check
- POST /deliberate           - Run full multi-agent deliberation
- POST /deliberate/stream    - Stream deliberation via SSE
- POST /deliberate/batch     - Submit batch deliberation (50% savings)
- GET  /batch/{id}           - Check batch status
- GET  /batch/{id}/results   - Get batch results
- GET  /decisions            - List recent decisions
- GET  /decisions/{id}       - Get a specific decision
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[2] / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestrator.src.core.models import DeliberationResult
from orchestrator.src.orchestrator import Deliberator
from orchestrator.src.services.claude_client import ClaudeClient
from orchestrator.src.services.database import DecisionDB
from orchestrator.src.services.mcp_context import MCPContextProvider

logger = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO)

deliberator: Deliberator | None = None
db: DecisionDB | None = None
claude: ClaudeClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global deliberator, db, claude
    claude = ClaudeClient()
    db = DecisionDB()
    await db.initialize()
    mcp = MCPContextProvider()
    deliberator = Deliberator(claude, db, mcp=mcp if mcp.enabled else None)
    mcp_status = f"MCP active ({', '.join(mcp.servers)})" if mcp.enabled else "MCP disabled"
    logger.info("MAGI initialized (Sonnet 4.6 + Opus 4.6 w/ extended thinking, %s)", mcp_status)
    yield
    await claude.close()
    logger.info("MAGI system shut down")


app = FastAPI(title="MAGI Deliberation System", version="0.3.0", lifespan=lifespan)


class DeliberateRequest(BaseModel):
    question: str
    context: str = ""


class BatchRequest(BaseModel):
    items: list[DeliberateRequest]


# ── Health ──────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.3.0"}


# ── Standard deliberation ──────────────────────────────────────

@app.post("/deliberate")
async def deliberate(req: DeliberateRequest) -> dict:
    if not deliberator:
        raise HTTPException(status_code=503, detail="System not initialized")
    result = await deliberator.deliberate(req.question, req.context)
    return result.model_dump(mode="json")


# ── Streaming deliberation (SSE) ───────────────────────────────

@app.post("/deliberate/stream")
async def deliberate_stream(req: DeliberateRequest):
    if not deliberator:
        raise HTTPException(status_code=503, detail="System not initialized")

    async def event_generator():
        async for event_type, data in deliberator.deliberate_stream(req.question, req.context):
            if event_type == "vote":
                yield f"event: vote\ndata: {json.dumps(data.model_dump(mode='json'))}\n\n"
            elif event_type == "thinking":
                yield f"event: thinking\ndata: {{}}\n\n"
            elif event_type == "meta_chunk":
                yield f"event: meta\ndata: {json.dumps({'text': data})}\n\n"
            elif event_type == "result":
                yield f"event: result\ndata: {json.dumps(data.model_dump(mode='json'))}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Batch deliberation ─────────────────────────────────────────

@app.post("/deliberate/batch")
async def deliberate_batch(req: BatchRequest) -> dict:
    if not deliberator:
        raise HTTPException(status_code=503, detail="System not initialized")
    items = [{"question": item.question, "context": item.context} for item in req.items]
    batch_id = await deliberator.deliberate_batch(items)
    return {"batch_id": batch_id, "items": len(items)}


@app.get("/batch/{batch_id}")
async def batch_status(batch_id: str) -> dict:
    if not claude:
        raise HTTPException(status_code=503, detail="System not initialized")
    return await claude.get_batch_status(batch_id)


@app.get("/batch/{batch_id}/results")
async def batch_results(batch_id: str) -> list[dict]:
    if not claude:
        raise HTTPException(status_code=503, detail="System not initialized")
    return await claude.get_batch_results(batch_id)


# ── Decision history ───────────────────────────────────────────

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
