"""A minimal Server-Sent Events decoder for the Responses stream (WHATWG event-stream rules we need)."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, cast

import orjson


class SSEDecodeError(ValueError):
    """An event's ``data`` isn't a JSON object."""


@dataclass
class _Pending:
    event: str | None = None
    data: list[str] = field(default_factory=list[str])

    def flush(self) -> dict[str, Any] | None:
        if not self.data:
            self.event = None
            return None
        payload = "\n".join(self.data)
        name = self.event
        self.event = None
        self.data = []
        if payload == "[DONE]":
            return None
        try:
            decoded: Any = orjson.loads(payload)
        except orjson.JSONDecodeError as exc:
            raise SSEDecodeError(f"event data is not JSON: {exc}") from exc
        if not isinstance(decoded, dict):
            raise SSEDecodeError("event data is not a JSON object")
        obj = cast(dict[str, Any], decoded)
        if name and "type" not in obj:
            obj["type"] = name
        return obj


def _feed(pending: _Pending, line: str) -> dict[str, Any] | None:
    line = line.rstrip("\r")
    if line == "":
        return pending.flush()
    if line.startswith(":"):
        return None
    name, _, value = line.partition(":")
    value = value.removeprefix(" ")
    if name == "data":
        pending.data.append(value)
    elif name == "event":
        pending.event = value
    return None


def iter_sse(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Decode text lines (without trailing newlines) into JSON event objects."""
    pending = _Pending()
    for line in lines:
        event = _feed(pending, line)
        if event is not None:
            yield event
    tail = pending.flush()
    if tail is not None:
        yield tail


async def aiter_sse(lines: AsyncIterable[str]) -> AsyncIterator[dict[str, Any]]:
    """Async twin of :func:`iter_sse`, for ``httpx.Response.aiter_lines()``."""
    pending = _Pending()
    async for line in lines:
        event = _feed(pending, line)
        if event is not None:
            yield event
    tail = pending.flush()
    if tail is not None:
        yield tail
