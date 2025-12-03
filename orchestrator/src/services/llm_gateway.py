"""LLM gateway wrapper for OpenRouter with retries and logging.

This module provides `LLMGateway`, a thin async wrapper around an LLM
provider HTTP API (OpenRouter by default). It uses `httpx.AsyncClient`
for requests and `tenacity` for robust retries. All public methods
accept an optional `correlation_id` which is added to logs for
traceability.

The implementation is intentionally minimal and provider-agnostic so it
can be extended to support multiple providers.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import httpx
from tenacity import (  # type: ignore
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger("orchestrator.llm_gateway")


class GatewayError(Exception):
    """Raised when the gateway cannot complete a request."""


class LLMGateway:
    """Async wrapper around an LLM HTTP API (OpenRouter by default).

    Args:
        api_key: API key to authorize requests. If not provided, will try
            `OPENROUTER_API_KEY` environment variable.
        base_url: Base URL for the LLM provider API. Defaults to
            OpenRouter chat completions endpoint prefix.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openrouter.ai/v1",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("API key not provided and OPENROUTER_API_KEY not set")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    def _headers(self, correlation_id: Optional[str] = None) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return headers

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, GatewayError)),
        reraise=True,
    )
    async def _post(self, path: str, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Internal POST with retries.

        This method is wrapped with tenacity to retry transient network
        errors. It returns the JSON-decoded response or raises a
        GatewayError on non-2xx responses.
        """
        url = path if path.startswith("http") else f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        headers = self._headers(correlation_id=correlation_id)
        extra = {"correlation_id": correlation_id} if correlation_id else {}
        logger.debug("LLMGateway POST %s payload=%s", url, payload, extra=extra)

        try:
            resp = await self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("HTTP error during request: %s", exc, extra=extra)
            raise

        if resp.status_code >= 400:
            logger.error("LLM provider returned error: %s %s", resp.status_code, resp.text, extra=extra)
            raise GatewayError(f"LLM provider error {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
        except Exception as exc:
            logger.exception("Failed to decode JSON response", extra=extra)
            raise GatewayError("invalid json response") from exc

        logger.debug("LLM response: %s", data, extra=extra)
        return data

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.0,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate text/completion from the LLM provider.

        This method calls the OpenRouter chat completion endpoint by
        default. The payload follows a minimal schema and can be
        extended as needed.

        Returns the parsed JSON response from the provider.
        """
        if not prompt:
            raise ValueError("prompt must be a non-empty string")

        path = "/chat/completions"
        payload: Dict[str, Any] = {
            "model": model or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(temperature),
        }

        try:
            result = await self._post(path, payload, correlation_id=correlation_id)
            return result
        except Exception as exc:
            extra = {"correlation_id": correlation_id} if correlation_id else {}
            logger.exception("Error generating from LLM", extra=extra)
            raise

    async def close(self) -> None:
        """Close the underlying HTTP client.

        Call this when the gateway is no longer needed to free resources.
        """
        try:
            await self._client.aclose()
        except Exception:
            logger.exception("Error closing HTTP client")
