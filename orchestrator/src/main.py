"""FastAPI application for MAGI-lite orchestrator.

Provides minimal endpoints used during development and testing:
- GET /health: health check
- POST /deliberate: accept a DecisionBrief payload and optionally apply a rule

Includes logging with an optional `X-Correlation-ID` header for traceability.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from orchestrator.src.core.models import DecisionBrief

logger = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO)


def get_correlation_id(header_value: Optional[str]) -> Optional[str]:
    """Normalize correlation id header value.

    Args:
        header_value: Raw header value from `X-Correlation-ID` (may be None).

    Returns:
        A string id or None.
    """
    if not header_value:
        return None
    return header_value.strip() or None


app = FastAPI(title="MAGI-lite Orchestrator")


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    correlation_id = get_correlation_id(request.headers.get("x-correlation-id"))
    extra = {"correlation_id": correlation_id} if correlation_id else {}
    logger.warning("Pydantic validation error: %s", exc, extra=extra)
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "correlation_id": correlation_id})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    correlation_id = get_correlation_id(request.headers.get("x-correlation-id"))
    extra = {"correlation_id": correlation_id} if correlation_id else {}
    logger.exception("Unhandled exception: %s", exc, extra=extra)
    return JSONResponse(status_code=500, content={"detail": str(exc), "correlation_id": correlation_id})


@app.get("/health")
async def health_check(x_correlation_id: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Simple health endpoint.

    Returns a small JSON payload and logs the check with correlation id.
    """
    correlation_id = get_correlation_id(x_correlation_id)
    extra = {"correlation_id": correlation_id} if correlation_id else {}
    logger.info("Health check", extra=extra)
    return {"status": "ok", "correlation_id": correlation_id}


@app.post("/deliberate")
async def deliberate(request: Request, rule: Optional[str] = None, x_correlation_id: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Accept a DecisionBrief JSON payload, optionally apply a rule and return the updated brief.

    Request body should be compatible with `DecisionBrief` model. If `rule`
    query parameter is provided, `DecisionBrief.apply_rule` will be called.
    """
    correlation_id = get_correlation_id(x_correlation_id)
    extra = {"correlation_id": correlation_id} if correlation_id else {}

    payload = await request.json()
    logger.debug("Received deliberate payload: %s", payload, extra=extra)

    try:
        brief = DecisionBrief(**payload)
    except ValidationError as exc:
        logger.warning("Invalid DecisionBrief payload: %s", exc, extra=extra)
        raise

    logger.info("Created DecisionBrief %s", str(brief.id), extra=extra)

    if rule:
        try:
            brief.apply_rule(rule, correlation_id=correlation_id)
        except Exception as exc:
            logger.error("Error applying rule '%s': %s", rule, exc, extra=extra)
            raise HTTPException(status_code=400, detail=str(exc))

    result = brief.to_dict(correlation_id=correlation_id)
    logger.info("Deliberation result for %s: %s", str(brief.id), result, extra=extra)

    return result
