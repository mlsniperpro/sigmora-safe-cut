"""Meta's free, unauthenticated ``GET /v1/status`` (PRE-A §10.7), for ``/healthz`` and the probes."""

from __future__ import annotations

import asyncio

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from safecut import config


class ModelStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    status: str | None = None


class MetaStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_alive: bool
    service_status: str
    service_message: str = ""
    model_statuses: list[ModelStatus] = Field(default_factory=list[ModelStatus])

    @property
    def healthy(self) -> bool:
        return self.is_alive and self.service_status == "operational"


class StatusUnavailableError(RuntimeError):
    """The status endpoint couldn't be read or returned an unexpected shape."""


_MAX_STATUS_BYTES = 64 * 1024


async def fetch_status(
    http: httpx.AsyncClient, base_url: str, *, timeout_s: float = config.CONNECT_TIMEOUT_S
) -> MetaStatus:
    """``timeout_s`` bounds the whole check (a dripping body included), and the body is at most 64 KiB."""
    try:
        async with asyncio.timeout(timeout_s):
            async with http.stream("GET", f"{base_url.rstrip('/')}/status", timeout=timeout_s) as resp:
                resp.raise_for_status()
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > _MAX_STATUS_BYTES:
                        raise StatusUnavailableError("Meta status check failed: the body is over 64 KiB")
        return MetaStatus.model_validate_json(body)
    except (httpx.HTTPError, ValidationError, TimeoutError) as exc:
        raise StatusUnavailableError(f"Meta status check failed: {type(exc).__name__}") from exc
