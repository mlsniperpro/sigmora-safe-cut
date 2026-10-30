"""A fake Meta Model API for offline tests of the live code paths: the endpoints SENSE calls, answered from the
synthetic demo scene's ground truth (``scripts/make_demo_job.py``'s responder)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import respx

from safecut.config import Settings
from safecut.meta import sam
from scripts import make_demo_job as demo
from tests.conftest import BASE, sse

CLIP = Path("fixtures/clips") / demo.CLIP_NAME
_PROMPT = re.compile(
    r"<(\d+)f>(\d+)(?:<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);[^|]*\|>)?<\|point;x=(\d+);y=(\d+);[^|]*\|>"
)
_LABELS = re.compile(r"F(\d+): \[([^\]]*)\]")
_DISPUTE = re.compile(r"^([^\s:]+(?: [^\s:]+)?:\d+): \[", re.MULTILINE)


class FakeMeta:
    """Meta's endpoints, answered from the demo scene's ground truth."""

    def __init__(self, job_dir: Path) -> None:
        self.job_dir = job_dir
        self.files: dict[str, bool] = {}
        self.calls: list[str] = []

    def responder(self) -> demo.Responder:
        """The responder for the job: ``job_dir`` itself, or the one job under it (a job named at run time)."""
        job = self.job_dir
        if not (job / "job.json").exists():
            job = next(p.parent for p in sorted(self.job_dir.glob("*/job.json")))
        return demo.Responder(job, Settings(sam_fps=8))

    def upload(self, request: httpx.Request) -> httpx.Response:
        file_id = f"file-{len(self.files) + 1}"
        self.files[file_id] = True
        self.calls.append("files:upload")
        return httpx.Response(200, json={"id": file_id, "object": "file", "purpose": "user_data"})

    def delete(self, request: httpx.Request, file_id: str) -> httpx.Response:
        self.files[file_id] = False
        self.calls.append("files:delete")
        return httpx.Response(200, json={"id": file_id, "object": "file", "deleted": True})

    def asr(self, request: httpx.Request) -> httpx.Response:
        assert b'"mode": "DIARIZATION"' in request.content
        self.calls.append("asr")
        return httpx.Response(200, json=self.responder().asr("transcribe", {}))

    def responses(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["store"] is False
        texts = [p["text"] for m in body["input"] for p in m["content"] if p["type"] == "input_text"]
        if body["model"] == "sam-3.1":
            self.calls.append("sam")
            events = self.responder().sam("live", self._sam_info(texts[0]))
        else:
            name = body["text"]["format"]["name"]
            self.calls.append(name)
            events = self._muse(name, texts)
            usage = {"input_tokens": 1200, "output_tokens": 300, "input_tokens_details": {"cached_tokens": 0}}
            events[-1]["response"]["usage"] = usage
        return httpx.Response(200, content=sse(*events), headers={"content-type": "text/event-stream"})

    def _sam_info(self, text: str) -> dict[str, Any]:
        if not text.startswith("<"):
            return {"kind": "phrase", "concept": text}
        prompts = []
        for m in _PROMPT.finditer(text):
            box = (int(m[3]), int(m[4]), int(m[5]) + 1, int(m[6]) + 1) if m[3] is not None else None
            prompts.append(sam.ObjectPrompt(int(m[2]), int(m[1]), (int(m[7]), int(m[8])), box))
        return {"kind": "object_prompt", "prompts": prompts}

    def _muse(self, name: str, texts: list[str]) -> list[dict[str, Any]]:
        responder = self.responder()
        per_frame = [(int(f), [x.strip() for x in labels.split(",") if x.strip()])
                     for f, labels in _LABELS.findall(texts[-1])]  # fmt: skip
        frames = [f for f, _ in per_frame]
        if name == "scene_pass":
            return responder.scene("scene", {})
        if name == "role_pass":
            last = texts[-1]
            k = 1 if "Judge every label" in last else 2 if "simply a bystander" in last else 3
            tag = "pass2" if any("added last round" in t for t in texts) else "pass1"
            info = {"vote": k, "frames": frames, "labels_per_frame": per_frame}
            return responder.vote(f"{tag}-w0-v{k}", info)
        assert name == "escalation"
        return responder.escalate("w0", {"frames": frames, "disputed": _DISPUTE.findall(texts[-1])})


@contextmanager
def serving(fake: FakeMeta) -> Iterator[respx.MockRouter]:
    """Route Meta's endpoints to ``fake`` for the duration."""
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post("files").mock(side_effect=fake.upload)
        router.get("files").mock(return_value=httpx.Response(200, json={"data": [], "has_more": False}))
        router.delete(path__regex=r"/files/(?P<file_id>file-\d+)$").mock(side_effect=fake.delete)
        router.post("responses/input_tokens").mock(return_value=httpx.Response(200, json={"input_tokens": 1200}))
        router.post("responses").mock(side_effect=fake.responses)
        router.post("asr/transcribe").mock(side_effect=fake.asr)
        yield router
