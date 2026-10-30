"""A minimal Server-Sent Events decoder for the Responses stream (WHATWG event-stream rules we need)."""

from __future__ import annotations

import codecs
import re
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


#: The only line endings in an event stream (WHATWG): not U+2028, U+2029 or U+0085, which JSON carries raw.
_EOL = re.compile(r"\r\n|\r|\n")


class _LineSplitter:
    """Incremental SSE line splitting: each text is scanned once, so a multi-MB line stays linear."""

    def __init__(self) -> None:
        self._line: list[str] = []  # the current line's text so far
        self._skip_lf = False  # the last text ended with "\r": a leading "\n" completes that "\r\n"

    def feed(self, text: str) -> list[str]:
        if not text:
            return []  # the decoder held a partial character: nothing changes, "\r" state included
        if self._skip_lf and text.startswith("\n"):
            text = text[1:]
        self._skip_lf = False
        if "\r" not in text and "\n" not in text:
            if text:
                self._line.append(text)
            return []
        first, *middle, last = _EOL.split(text)
        lines = ["".join([*self._line, first]), *middle]
        self._line = [last] if last else []
        self._skip_lf = text.endswith("\r")
        return lines

    def close(self) -> list[str]:
        return ["".join(self._line)] if self._line else []


async def aiter_sse_lines(chunks: AsyncIterable[bytes]) -> AsyncIterator[str]:
    """Split a byte stream into SSE lines (``httpx.Response.aiter_bytes()``).

    httpx's ``aiter_lines`` splits on every ``str.splitlines`` separator, so a raw U+2028 inside a JSON
    string would cut an event in two. Undecodable bytes become U+FFFD (inside a string, still valid JSON).
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    splitter = _LineSplitter()
    async for chunk in chunks:
        for line in splitter.feed(decoder.decode(chunk)):
            yield line
    for line in [*splitter.feed(decoder.decode(b"", final=True)), *splitter.close()]:
        yield line


async def aiter_sse(lines: AsyncIterable[str]) -> AsyncIterator[dict[str, Any]]:
    """Async twin of :func:`iter_sse`, for :func:`aiter_sse_lines` output."""
    pending = _Pending()
    async for line in lines:
        event = _feed(pending, line)
        if event is not None:
            yield event
    tail = pending.flush()
    if tail is not None:
        yield tail
