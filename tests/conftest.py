"""Shared fixtures: settings with a fake key, a fresh ledger, and a Meta client whose sleeps are recorded."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from hypothesis import HealthCheck
from hypothesis import settings as hypothesis_settings
from pydantic import SecretStr

from safecut.config import Settings
from safecut.contracts import CostLine, read_cost_lines
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import MetaClient

# Property-test volume: "dev" for every run, "soak" (HYPOTHESIS_PROFILE=soak) for long background runs.
hypothesis_settings.register_profile("dev", max_examples=300, deadline=None)
hypothesis_settings.register_profile(
    "soak", max_examples=20_000, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

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


def rle_string(runs: list[int]) -> str:
    """Encode run lengths as a COCO compressed RLE string (cocoapi ``rleToString``)."""
    out: list[str] = []
    for i, run in enumerate(runs):
        x = run - runs[i - 2] if i > 2 else run
        more = True
        while more:
            c = x & 0x1F
            x >>= 5
            more = (x != -1) if c & 0x10 else (x != 0)
            if more:
                c |= 0x20
            out.append(chr(c + 48))
    return "".join(out)


def narrow_patch(job_dir: Path, first: int) -> None:
    """Start the example's audit patch p_1 at ``first`` (it spans the whole 12-frame clip), so a test can put a
    frame outside it. Drops the receipt, which would (rightly) disagree with the edit."""
    decisions = json.loads((job_dir / "decisions.json").read_text())
    next(i for i in decisions["items"] if i["item_id"] == "p_1")["first"] = first
    (job_dir / "decisions.json").write_text(json.dumps(decisions))
    plan = json.loads((job_dir / "plan.json").read_text())
    for frame, entries in plan["frames"].items():
        if int(frame) < first:
            entries[:] = [e for e in entries if e["item_id"] != "p_1"]
    (job_dir / "plan.json").write_text(json.dumps(plan))
    (job_dir / "receipt.json").unlink(missing_ok=True)
