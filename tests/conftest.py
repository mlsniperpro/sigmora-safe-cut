"""Shared fixtures: settings with a fake key, a fresh ledger, and a Meta client whose sleeps are recorded."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from safecut.config import Settings
from safecut.contracts import CostLine, read_cost_lines
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import MetaClient

BASE = "https://api.meta.ai/v1"
FAKE_KEY = "sk-test-not-a-real-key"


@pytest.fixture
def settings() -> Settings:
    return Settings(model_api_key=SecretStr(FAKE_KEY))


@pytest.fixture
def ledger() -> LocalLedger:
    return LocalLedger()


class Harness:
    """A client plus what it did: sleeps it asked for and the cost lines it wrote."""

    def __init__(self, client: MetaClient, sleeps: list[float], cost_path: Path) -> None:
        self.client = client
        self.sleeps = sleeps
        self.cost_path = cost_path

    def costs(self) -> list[CostLine]:
        return list(read_cost_lines(self.cost_path))


@pytest.fixture
async def make_harness(
    settings: Settings, ledger: LocalLedger, tmp_path: Path
) -> AsyncIterator[Callable[..., Harness]]:
    made: list[MetaClient] = []

    def factory(*, job_id: str | None = "j_test", caller: Caller | None = None, cfg: Settings | None = None) -> Harness:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        cost_path = tmp_path / f"cost-{len(made)}.jsonl"
        client = MetaClient(
            cfg or settings,
            job_id=job_id,
            caller=caller or Caller.local("eval"),
            ledger=ledger,
            cost_path=cost_path,
            sleep=fake_sleep,
            jitter=lambda: 0.0,
        )
        made.append(client)
        return Harness(client, sleeps, cost_path)

    yield factory
    for client in made:
        await client.aclose()


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


def sse(*events: dict[str, Any]) -> bytes:
    """Encode events as an SSE body, the way the Responses stream sends them."""
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


def completed(response: dict[str, Any]) -> dict[str, Any]:
    return {"type": "response.completed", "response": response}


def text_response(text: str, *, usage: dict[str, Any] | None = None, rid: str = "resp_1") -> dict[str, Any]:
    return {
        "id": rid,
        "status": "completed",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}],
        "usage": usage
        or {"input_tokens": 1000, "output_tokens": 200, "output_tokens_details": {"reasoning_tokens": 50}},
    }


def stream_response(*events: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=sse(*events), headers={"content-type": "text/event-stream"})
