"""The API's response bodies, built from a job's state and its contract files (UI-SPEC §8; the web app parses
them with ``web/src/lib/contracts.ts``).

Every file is validated as it is read (``safecut.contracts.load``); a file that isn't there yet is simply left
out of the response, so the shapes grow as the pipeline runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image
from pydantic import BaseModel

from safecut.api.access import Access
from safecut.api.store import JobState
from safecut.api.urls import Signer
from safecut.config import Settings
from safecut.contracts import Audit, Decisions, Job, Plan, Roles, Scene, Tracks, Transcript, load
from safecut.stages import RECEIPT_HTML, REDACTED, stage

#: Share of a phase's work each stage represents, for ``progress`` and ``eta_s``.
WEIGHTS = {
    "prepare": 0.05,
    "track": 0.35,
    "transcribe": 0.10,
    "scene": 0.10,
    "roles": 0.25,
    "decide": 0.05,
    "guard": 0.10,
    "render": 0.40,
    "audit": 0.50,
    "receipt": 0.10,
}
ANALYSE = ("prepare", "track", "transcribe", "scene", "roles", "decide", "guard")
PUBLISH = ("render", "audit", "receipt")


def iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def _json(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def public_audit(audit: Audit) -> dict[str, Any]:
    """``audit.json`` as clients see it: the red team's ``text`` and ``detail`` stay in the job dir (redteam.md
    "Private text"); a hit shows its kind, frame and box, and "text read (n characters)" when it read text."""
    body: dict[str, Any] = _json(audit)
    for key in ("redteam", "redteam_open"):
        entries: list[dict[str, Any]] = body.get(key) or []
        for entry in entries:
            if entry.get("finding") != "hit":
                continue
            text = entry.get("text")
            entry["text"] = f"text read ({len(text)} characters)" if text else None
            entry.pop("detail", None)
    return body


def _optional[M: BaseModel](path: Path, model: type[M]) -> M | None:
    return load(path, model) if path.is_file() else None


def models_used(job_dir: Path, s: Settings) -> dict[str, str]:
    """Which model did which job, from the job's own files where they recorded it, else the config (the API's job
    body and the eval's run config both say this, so neither claims a model that didn't run)."""
    models = {
        "sam": s.sam_model,
        "scene": s.scene_model,
        "roles": s.role_model,
        "escalate": s.escalate_model,
        "asr": s.asr_model,
        "redteam": s.redteam_model,
        "auditor": s.egoblur_model,
    }
    scene = _optional(job_dir / "scene.json", Scene)
    if scene is not None and scene.model:
        models["scene"] = scene.model
    roles = _optional(job_dir / "roles.json", Roles)
    if roles is not None and roles.model:
        models["roles"] = roles.model
    transcript = _optional(job_dir / "transcript.json", Transcript)
    if transcript is not None and transcript.source:
        models["asr"] = transcript.source
    audit = _optional(job_dir / "audit.json", Audit)
    if audit is not None:
        models["auditor"] = audit.egoblur.model
    return models


def models_recorded(job_dir: Path, s: Settings) -> dict[str, str]:
    """Only what the job's files show ran: the trackers named on its tracks, the scene, roles and speech models
    their files record, the escalation when a ruling exists, the auditor ``audit.json`` names and the red team when
    it answered. A stage that never ran is absent (the eval's run configs; the API's job body shows the plan)."""
    ran: dict[str, str] = {}
    tracks = _optional(job_dir / "tracks.json", Tracks)
    if tracks is not None:
        sources = sorted({t.source for t in tracks.tracks if t.source})
        if sources:
            ran["tracks"] = " / ".join(sources)
    scene = _optional(job_dir / "scene.json", Scene)
    if scene is not None and scene.model:
        ran["scene"] = scene.model
    roles = _optional(job_dir / "roles.json", Roles)
    if roles is not None and roles.model:
        ran["roles"] = roles.model
        if any(t.suggested_role is not None for t in roles.tracks):
            ran["escalate"] = s.escalate_model
    transcript = _optional(job_dir / "transcript.json", Transcript)
    if transcript is not None and transcript.source:
        ran["asr"] = transcript.source
    audit = _optional(job_dir / "audit.json", Audit)
    if audit is not None:
        ran["auditor"] = audit.egoblur.model
        if audit.redteam:
            ran["redteam"] = s.redteam_model
    return ran


class Views:
    def __init__(self, settings: Settings, signer: Signer) -> None:
        self.settings = settings
        self.signer = signer
        self.access = Access(settings)

    # -- URLs ---------------------------------------------------------------

    def media_url(self, job_id: str, name: str) -> str:
        return self.signer.sign(f"/v1/jobs/{job_id}/media/{name}")

    @staticmethod
    def media_allowed(job_dir: Path, name: str) -> bool:
        """Only the files a browser needs: the prepared and redacted videos, the receipt, keyframes, thumbnails
        and captions; never raw responses, cost lines or state."""
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or "\\" in name or "\x00" in name:
            return False
        if name in (REDACTED, RECEIPT_HTML, "receipt.json", "captions.vtt"):
            return True
        if len(pure.parts) == 2 and pure.parts[0] in ("som", "thumbs", "keyframes") and pure.suffix == ".jpg":
            return True
        job = _optional(job_dir / "job.json", Job)
        return job is not None and name == job.prepared

    # -- progress -----------------------------------------------------------

    @staticmethod
    def progress(state: JobState, job_dir: Path) -> tuple[float | None, float | None]:
        """``(progress, eta_s)`` for the running phase: the done stages' weights, and the time left at the pace
        so far (none until a tenth of the phase is done)."""
        if state.status not in ("processing", "rendering", "retry_later"):
            return (1.0 if state.status in ("review", "done") else None), None
        names = ANALYSE if state.status != "rendering" else PUBLISH
        total = sum(WEIGHTS[n] for n in names)
        current = state.stage if state.stage in names else None
        done = 0.0
        for name in names:
            if name == current:
                break
            if current is not None or (job_dir / _output(name)).is_file():
                done += WEIGHTS[name]
        fraction = min(done / total, 1.0)
        if state.started_at is None or fraction < 0.1:
            return fraction, None
        elapsed = (datetime.now(UTC) - state.started_at).total_seconds()
        return fraction, max(0.0, round(elapsed * (1 - fraction) / fraction, 1))

    # -- bodies -------------------------------------------------------------

    def code_valid_until(self, state: JobState) -> str | None:
        if state.service is not None:
            return iso(self.settings.code_windows["service"].until)
        if state.code_id is None or state.code_kind is None:
            return None
        grant = self.access.by_code_id(state.code_id)
        return iso(grant.valid_until) if grant else None

    def job(self, state: JobState, job_dir: Path) -> dict[str, Any]:
        progress, eta = self.progress(state, job_dir)
        body: dict[str, Any] = {
            "job_id": state.job_id,
            "mode": state.mode,
            "synthetic": state.synthetic,
            "status": state.status,
            "stage": state.stage,
            "stage_reason": state.stage_reason,
            "eta_s": eta,
            "deletes_at": iso(state.deletes_at),
            "retry_at": iso(state.retry_at),
            "code_valid_until": self.code_valid_until(state),
            "has_render": (job_dir / REDACTED).is_file(),
            "failure": state.failure.model_dump(mode="json", exclude={"detail"}, exclude_none=True)
            if state.failure
            else None,
            "models": self.models(job_dir),
        }
        if progress is not None:
            body["progress"] = progress
        job = _optional(job_dir / "job.json", Job)
        if job is not None:
            body["job"] = {
                "fps": job.fps,
                "width": job.width,
                "height": job.height,
                "frames": job.frames,
                "audio": job.audio,
                "times": job.times,
                "created_at": iso(job.created_at),
                "source_name": job.source,
                "prepared_url": self.media_url(state.job_id, job.prepared),
            }
        decisions = _optional(job_dir / "decisions.json", Decisions)
        if decisions is not None:
            body["items"] = [_json(item) | {"removed_by_creator": item.removed_by_creator} for item in decisions.items]
        tracks = _optional(job_dir / "tracks.json", Tracks)
        if tracks is not None:
            body["tracks"] = [
                {
                    "track_id": t.track_id,
                    "concept": t.concept,
                    "first": t.first,
                    "last": t.last,
                    "reentry_of": t.reentry_of,
                    "child_phrase": t.child_phrase,
                    "boxes": {str(f): list(b) for f, b in t.boxes.items()},
                }
                for t in tracks.tracks
            ]
        roles = _optional(job_dir / "roles.json", Roles)
        if roles is not None:
            body["roles"] = _json(roles)
            body["keyframe_urls"] = {
                name: self.media_url(state.job_id, name) for name in roles.keyframes if (job_dir / name).is_file()
            }
            geometry = self.keyframe_geometry(job_dir, roles, job)
            if geometry is not None:
                body["keyframe_geometry"] = geometry
        for name, model, key in (
            ("plan.json", Plan, "plan"),
            ("transcript.json", Transcript, "transcript"),
            ("scene.json", Scene, "scene"),
        ):
            loaded = _optional(job_dir / name, model)
            if loaded is not None:
                body[key] = _json(loaded)
        audit = _optional(job_dir / "audit.json", Audit)
        if audit is not None:
            body["audit"] = public_audit(audit)
            body["audit_budget_cause"] = audit.audit_budget_cause
        if (job_dir / REDACTED).is_file():
            body["result"] = self.result_urls(state.job_id, job_dir)
        return body

    def result_urls(self, job_id: str, job_dir: Path) -> dict[str, str]:
        urls = {"video_url": self.media_url(job_id, REDACTED)}
        if (job_dir / RECEIPT_HTML).is_file():
            urls["receipt_html_url"] = self.media_url(job_id, RECEIPT_HTML)
        if (job_dir / "receipt.json").is_file():
            urls["receipt_json_url"] = self.media_url(job_id, "receipt.json")
        return urls

    def result(self, state: JobState, job_dir: Path) -> dict[str, Any]:
        audit = load(job_dir / "audit.json", Audit)
        job = load(job_dir / "job.json", Job)
        body: dict[str, Any] = {
            "job_id": state.job_id,
            "mode": state.mode,
            "synthetic": state.synthetic,
            "status": state.status,
            "deletes_at": iso(state.deletes_at),
            "frames": job.frames,
            **self.result_urls(state.job_id, job_dir),
            "captions_url": self.media_url(state.job_id, "captions.vtt") if self.has_captions(job_dir) else None,
            "audit": public_audit(audit),
            "code_valid_until": self.code_valid_until(state),
        }
        return body

    def demo(self, state: JobState, job_dir: Path) -> dict[str, Any]:
        job = load(job_dir / "job.json", Job)
        result = self.result(state, job_dir)
        return {
            "mode": "replay",
            "synthetic": state.synthetic,
            "job": {
                "prepared_url": self.media_url(state.job_id, job.prepared),
                "fps": job.fps,
                "frames": job.frames,
                "times": job.times,
            },
            "video_url": result["video_url"],
            "poster_url": None,
            "captions_url": result["captions_url"],
            "audit": result["audit"],
        }

    def models(self, job_dir: Path) -> dict[str, str]:
        return models_used(job_dir, self.settings)

    @staticmethod
    def keyframe_geometry(job_dir: Path, roles: Roles, job: Job | None) -> dict[str, int] | None:
        first = next((job_dir / k for k in roles.keyframes if (job_dir / k).is_file()), None)
        if first is None or job is None:
            return None
        with Image.open(first) as image:
            width, height = image.size
        # The frame keeps its aspect ratio at the image's width; whatever is left above it is the label bar.
        bar = max(0, height - round(job.height * width / job.width))
        return {
            "bar_h": bar,
            "frame_width": width,
            "frame_height": height - bar,
            "image_width": width,
            "image_height": height,
        }

    @staticmethod
    def has_captions(job_dir: Path) -> bool:
        transcript = _optional(job_dir / "transcript.json", Transcript)
        return transcript is not None and transcript.status == "ok" and bool(transcript.turns)

    @staticmethod
    def captions(job_dir: Path) -> str:
        """WebVTT captions from the transcript's turns (on the prepared clip's clock, UI-SPEC §8 request 7)."""
        transcript = load(job_dir / "transcript.json", Transcript)
        lines = ["WEBVTT", ""]
        for n, turn in enumerate(transcript.turns, 1):
            text = turn.text.replace("-->", "→").strip()
            lines += [str(n), f"{_vtt_time(turn.start)} --> {_vtt_time(max(turn.end, turn.start + 0.5))}", text, ""]
        return "\n".join(lines)


def _vtt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def _output(name: str) -> str:
    return stage(name).output
