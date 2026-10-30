"""WP4 audit loop on synthetic jobs: clean pass, the injected 3-frame leak (E4), every failure path, read-through,
leaks left after pass 3, and the live red-team's call logic (the Meta client stubbed)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from safecut import contracts, pipeline
from safecut.audit import NoRedTeam, loop, replay_redteam
from safecut.audit import leaks as rules
from safecut.audit import redteam as rt
from safecut.audit import run as audit_run
from safecut.audit.detectors import AuditorModel, Detection, YuNet
from safecut.audit.redteam import Answer, Finding, LiveRedTeam, RedteamOutput, ReplayRedTeam
from safecut.config import Settings
from safecut.contracts import Audit, Decisions, Leak, Plan, dump, load
from safecut.decide import run as decide_run
from safecut.decide.geometry import contains as g_contains
from safecut.decide.geometry import encode
from safecut.guard import run as guard_run
from safecut.meta.errors import BudgetExceeded, MetaRefusal, MetaUnavailable
from safecut.receipt import ReceiptError
from safecut.receipt import run as receipt_run
from safecut.render import render
from safecut.render.draw import Frame
from safecut.render.video import read_frames
from tests.safety_jobs import make_job

SETTINGS = Settings(egoblur_model="yunet-face")


def prepared(tmp_path: Path) -> Path:
    job_dir = make_job(tmp_path)
    decide_run(job_dir)
    guard_run(job_dir)
    render(job_dir)
    return job_dir


def audit_of(job_dir: Path) -> Audit:
    return load(job_dir / "audit.json", Audit)


def drop(job_dir: Path, item_id: str, frames: set[int]) -> None:
    """Inject a leak: remove ``item_id``'s plan entries on ``frames`` and re-render."""
    plan = load(job_dir / "plan.json", Plan)
    kept = {f: [e for e in es if not (e.item_id == item_id and f in frames)] for f, es in plan.frames.items()}
    dump(plan.model_copy(update={"frames": {f: es for f, es in kept.items() if es}}), job_dir / "plan.json")
    render(job_dir)


class Scripted:
    """A red-team that answers from a script: frame → findings (grid units), the same on every pass."""

    def __init__(
        self, script: dict[int, list[Finding]], missing: Sequence[int] = (), cause: Any = None, once: bool = False
    ) -> None:
        self.script, self.missing, self.cause, self.once = script, set(missing), cause, once
        self.asked: list[list[int]] = []

    async def ask(self, frames: Sequence[tuple[int, Frame]], approved: Sequence[str], *, bar: int) -> Answer:
        sent = [f for f, _ in frames]
        self.asked.append(sent)
        script = {} if self.once and len(self.asked) > 1 else self.script  # once: a fix the model can't read through
        return Answer(
            findings={f: list(script.get(f, [])) for f in sent if f not in self.missing},
            missing=[f for f in sent if f in self.missing],
            budget_cause=self.cause,
        )


def finding(kind: Any, box: list[int], text: str | None = None) -> Finding:
    return Finding(kind=kind, detail="scripted", text=text, box=box, confidence="high")


def grid(box: tuple[int, int, int, int], bar: int = 40, w: int = 320, h: int = 240) -> list[int]:
    return [round(box[0] * 1000 / w), round((box[1] + bar) * 1000 / (h + bar)),
            round(box[2] * 1000 / w), round((box[3] + bar) * 1000 / (h + bar))]  # fmt: skip


# ---------------------------------------------------------------------------------------------- the loop


def test_a_clean_render_passes_in_one_pass(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    audit_run(job_dir, replay=True, settings=SETTINGS)
    audit = audit_of(job_dir)
    assert (audit.passes, audit.unresolved, audit.blocked_reason, audit.leaks) == (1, 0, None, [])
    assert audit.frames_scanned == 60
    assert audit.egoblur.model == "yunet-face"
    assert audit.egoblur.plates is None
    assert {e.frame // 30 for e in audit.redteam} == {0, 1}
    run = json.loads((job_dir / "raw/audit/run.json").read_text())
    assert (run["detector"], run["redteam_model"], run["frames_scanned"]) == ("yunet-face", None, 60)
    contracts.validate_job_dir(job_dir)


@pytest.mark.entry("E4:injected_leak_patched")
def test_an_injected_3_frame_leak_is_found_and_patched(tmp_path: Path) -> None:
    """E4: a 3-frame hole in the bystander's redaction is found by the detector (every frame) and the red-team,
    patched with an audit patch, re-rendered, and verified clean on the next pass."""
    job_dir = prepared(tmp_path)
    drop(job_dir, "i_2", {30, 31, 32})
    audit_run(job_dir, replay=True, settings=SETTINGS)
    audit = audit_of(job_dir)
    leak_frames = {leak.frame for leak in audit.leaks}
    assert {30, 31, 32} <= leak_frames
    flagged = {leak.frame for leak in audit.leaks if leak.detector == "egoblur"}
    asked = {e.frame for e in audit.redteam}
    assert flagged <= asked  # redteam.md Inputs: "and every frame EgoBlur flagged"
    assert {leak.detector for leak in audit.leaks if leak.frame in (30, 31, 32)} == {"egoblur", "redteam"}
    assert all(leak.patched_item is not None and leak.patched_item.startswith("p_") for leak in audit.leaks)
    assert audit.unresolved == 0
    assert audit.passes >= 2
    decisions = load(job_dir / "decisions.json", Decisions)
    patches = [i for i in decisions.items if i.origin == "audit_patch"]
    assert patches[0].audit_label == "A1"
    assert patches[0].evidence_frames == [30]
    yunet = YuNet()
    job = load(job_dir / "job.json", contracts.Job)
    frames = list(read_frames(job_dir / "redacted.mp4", job))
    for f in (30, 31, 32):
        assert not [d for d in yunet.detect(frames[f]) if d.box[0] > 150]  # the bystander is covered again
    contracts.validate_job_dir(job_dir)


def test_a_leak_that_survives_3_passes_is_unresolved_with_a_spot(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    always = Scripted({30: [finding("face", grid((10, 10, 40, 40)))]})
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=always)
    audit = audit_of(job_dir)
    assert (audit.passes, audit.blocked_reason, audit.unresolved) == (3, "unresolved_leaks", 1)
    unresolved = [leak for leak in audit.leaks if leak.unresolved]
    assert len(unresolved) == 1
    assert unresolved[0].patched_item is None
    assert [s.spot_id for s in audit.spots] == ["s1"]
    assert [len(asked) > 1 for asked in always.asked] == [True, False, False]  # passes 2-3 re-check the leak frame
    contracts.validate_job_dir(job_dir)


def test_text_read_through_a_mosaic_is_flagged_and_its_item_goes_solid(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    plan = load(job_dir / "plan.json", Plan)
    (bystander,) = [e for e in plan.frames[30] if e.item_id == "i_2"]
    x1, y1, _x2, _y2 = bystander.box
    read = Scripted({30: [finding("text", grid((x1 + 2, y1 + 2, x1 + 20, y1 + 12)), "KDA 123X")]}, once=True)
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=read)
    audit = audit_of(job_dir)
    (flagged,) = [leak for leak in audit.leaks if leak.flag]
    assert flagged.through_item == "i_2"
    assert flagged.patched_item == "p_1"  # the finding's own patch, besides the item going solid
    plan = load(job_dir / "plan.json", Plan)
    assert {e.style for es in plan.frames.values() for e in es if e.item_id == "i_2"} == {"solid"}
    contracts.validate_job_dir(job_dir)
    guard_run(job_dir)  # a later re-plan keeps the item solid
    assert {e.style for es in load(job_dir / "plan.json", Plan).frames.values() for e in es if e.item_id == "i_2"} == {
        "solid"
    }
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted({}))  # and so does a re-run of the audit
    assert [leak.through_item for leak in audit_of(job_dir).leaks if leak.flag] == ["i_2"]
    contracts.validate_job_dir(job_dir)


def test_a_finding_on_the_kept_host_is_excused_not_a_leak(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    tracks = load(job_dir / "tracks.json", contracts.Tracks)
    host = next(t for t in tracks.tracks if t.track_id == "face:1").boxes[30]
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted({30: [finding("face", grid(host))]}))
    audit = audit_of(job_dir)
    hits = [e for e in audit.redteam if isinstance(e, contracts.RedteamHit)]
    assert [(h.frame, h.excluded_by) for h in hits] == [(30, "i_1")]
    assert audit.leaks == []
    contracts.validate_job_dir(job_dir)


def test_our_frame_label_is_dropped_but_anything_else_in_the_bar_is_a_whole_frame_leak(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    script = {0: [finding("text", [10, 0, 300, 50], "F 000000")], 30: [finding("face", [10, 0, 300, 50])]}
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted(script))
    audit = audit_of(job_dir)
    assert [e.finding for e in audit.redteam if e.frame == 0] == ["none"]
    face = next(leak for leak in audit.leaks if leak.frame == 30)
    assert face.box == (0, 0, 320, 240)
    contracts.validate_job_dir(job_dir)


def test_a_finding_that_cannot_be_placed_is_never_excused_by_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A face reported in the bar (or with a malformed box) becomes a whole-frame leak, which no kept item excuses
    (fail closed), even a host who fills the frame (stood in for by an exclusion that excuses everything)."""
    job_dir = prepared(tmp_path)
    monkeypatch.setattr(rules, "excluded_by", lambda *_: "i_1")
    script = {0: [finding("face", [1, 2, 3])], 30: [finding("face", [10, 0, 300, 50])]}
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted(script))
    audit = audit_of(job_dir)
    hits = [e for e in audit.redteam if isinstance(e, contracts.RedteamHit) and e.frame in (0, 30)]
    assert hits
    assert all(h.excluded_by is None for h in hits)
    assert {leak.frame for leak in audit.leaks if leak.box == (0, 0, 320, 240)} >= {0, 30}
    contracts.validate_job_dir(job_dir)


def test_unanswered_frames_block_as_audit_failed(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=NoRedTeam())
    audit = audit_of(job_dir)
    assert audit.blocked_reason == "audit_failed"
    assert audit.unresolved >= 2
    contracts.validate_job_dir(job_dir)


def test_a_replay_without_recordings_answers_nothing(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    (job_dir / "raw/redteam/synthetic_truth.json").unlink()
    assert isinstance(replay_redteam(job_dir), NoRedTeam)
    recorded = job_dir / "raw/redteam/frames.json"
    leak = finding("face", [10, 10, 40, 40]).model_dump()
    recorded.write_text(json.dumps({"model": "muse-spark-1.3", "answers": {"0": [[leak], []], "30": [[]]}}))
    replay = replay_redteam(job_dir)
    assert isinstance(replay, ReplayRedTeam)
    blank = np.zeros((2, 2, 3), np.uint8)
    first = asyncio.run(replay.ask([(0, blank), (5, blank)], [], bar=24))
    assert (len(first.findings[0]), first.missing, first.model) == (1, [5], "muse-spark-1.3")
    again = asyncio.run(replay.ask([(0, blank)], [], bar=24))  # the re-check gets the second recorded answer
    assert again.findings == {0: []}
    third = asyncio.run(replay.ask([(0, blank)], [], bar=24))  # asked more often than recorded: unanswered
    assert (third.findings, third.missing, third.model) == ({}, [0], None)


def test_a_budget_stop_blocks_as_over_budget(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    stopped = Scripted({}, missing=range(60), cause="daily_cap")
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=stopped)
    audit = audit_of(job_dir)
    assert (audit.blocked_reason, audit.audit_budget_cause) == ("over_budget", "daily_cap")
    assert audit.unresolved > 0


class Crashing:
    @property
    def model(self) -> AuditorModel:
        return "yunet-face"

    @property
    def detects_plates(self) -> bool:
        return False

    def __init__(self, after: int) -> None:
        self.after, self.seen = after, 0

    def detect(self, frame: Frame) -> list[Detection]:
        if self.seen >= self.after:
            raise RuntimeError("out of memory")
        self.seen += 1
        return []


@pytest.mark.parametrize(("after", "faces"), [(20, 0), (0, None)])
def test_a_detector_crash_leaves_frames_unscanned(tmp_path: Path, after: int, faces: int | None) -> None:
    job_dir = prepared(tmp_path)
    audit_run(job_dir, replay=True, settings=SETTINGS, detector=Crashing(after))
    audit = audit_of(job_dir)
    assert (audit.frames_scanned, audit.egoblur.faces) == (after, faces)
    assert audit.unresolved >= 60 - after
    assert audit.blocked_reason == "audit_failed"
    contracts.validate_job_dir(job_dir)


def test_the_audit_renders_first_when_there_is_no_video(tmp_path: Path) -> None:
    job_dir = make_job(tmp_path)
    decide_run(job_dir)
    guard_run(job_dir)
    audit_run(job_dir, replay=True, settings=SETTINGS)
    assert (job_dir / "redacted.mp4").exists()
    assert audit_of(job_dir).unresolved == 0


# ---------------------------------------------------------------------------------------------- live red-team logic


REFUSED = "refused"
INVALID = "invalid"


class FakeCalls:
    """Stands in for ``responses.create``: from a queue, an output, a refusal, an invalid answer or an exception."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.bodies: list[Any] = []

    async def create(self, client: Any, body: Any, **_: Any) -> Any:
        self.bodies.append(body)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome == REFUSED:
            part = {"type": "refusal", "refusal": "no"}
        else:
            part = {"type": "output_text", "text": "{not json" if outcome == INVALID else outcome.model_dump_json()}
        return SimpleNamespace(response={"output": [{"type": "message", "content": [part]}]})


def frames(*numbers: int) -> list[tuple[int, Frame]]:
    return [(n, np.full((24, 32, 3), 90, dtype=np.uint8)) for n in numbers]


def output(*numbers: int, hits: dict[int, list[Finding]] | None = None) -> RedteamOutput:
    return RedteamOutput.model_validate(
        {"frames": [{"frame": n, "findings": [f.model_dump() for f in (hits or {}).get(n, [])]} for n in numbers]}
    )


def live(tmp_path: Path, calls: FakeCalls, monkeypatch: pytest.MonkeyPatch) -> LiveRedTeam:
    monkeypatch.setattr(rt.responses, "create", calls.create)
    return LiveRedTeam(client=cast(Any, None), settings=Settings(), job_dir=tmp_path)  # responses is stubbed


def test_live_batches_50_frames_a_call_with_a_bar_on_every_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = FakeCalls([output(*range(50)), output(*range(50, 60))])
    got = asyncio.run(live(tmp_path, calls, monkeypatch).ask(frames(*range(60)), ["the host"], bar=24))
    assert sorted(got.findings) == list(range(60))
    assert got.missing == []
    first = calls.bodies[0]
    user = first["input"][1]["content"]
    assert len([p for p in user if p["type"] == "input_image"]) == 50
    assert "the host" in user[0]["text"]
    assert first["store"] is False
    assert first["text"]["format"]["strict"] is True
    recorded = json.loads((tmp_path / "raw/redteam/frames.json").read_text())
    assert len(recorded["answers"]) == 60
    assert all(len(asks) == 1 for asks in recorded["answers"].values())
    assert (tmp_path / "redteam_raw.jsonl").read_text().count("\n") == 2


def test_live_follows_up_once_on_missing_frames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = FakeCalls([output(0, 1, 99), output(2), output()])
    got = asyncio.run(live(tmp_path, calls, monkeypatch).ask(frames(0, 1, 2, 3), [], bar=24))
    assert sorted(got.findings) == [0, 1, 2]
    assert got.missing == [3]  # still missing after the one follow-up
    assert len(calls.bodies) == 2


def test_live_reasks_a_refusal_once_with_the_softer_wording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = FakeCalls([REFUSED, output(0)])
    got = asyncio.run(live(tmp_path, calls, monkeypatch).ask(frames(0), [], bar=24))
    assert sorted(got.findings) == [0]
    assert calls.bodies[1]["input"][1]["content"][0]["text"].startswith(rt.SOFTER)


def test_live_reasks_a_refusal_the_client_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The client raises a refusal it meets while streaming, before any text: re-asked like one in the message."""
    calls = FakeCalls([MetaRefusal("refused (2 chars)"), output(0)])
    got = asyncio.run(live(tmp_path, calls, monkeypatch).ask(frames(0), [], bar=24))
    assert sorted(got.findings) == [0]
    assert calls.bodies[1]["input"][1]["content"][0]["text"].startswith(rt.SOFTER)


@pytest.mark.parametrize("script", [[INVALID, REFUSED], [REFUSED, INVALID], [INVALID, INVALID], [REFUSED, REFUSED]])
def test_live_reasks_at_most_once_per_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: list[str]) -> None:
    """redteam.md: one re-ask in total per call, whatever went wrong; then the frames stay unresolved."""
    calls = FakeCalls([*script, output(0)])
    got = asyncio.run(live(tmp_path, calls, monkeypatch).ask(frames(0), [], bar=24))
    assert len(calls.bodies) == 2
    assert (got.findings, got.missing, got.model) == ({}, [0], None)  # no answer: no model claimed either


def test_live_failures_and_budget_stops_leave_frames_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = FakeCalls([MetaUnavailable("down")])
    got = asyncio.run(live(tmp_path, calls, monkeypatch).ask(frames(0, 1), [], bar=24))
    assert (got.findings, got.missing, got.budget_cause) == ({}, [0, 1], None)
    stop = BudgetExceeded("cap", cap="daily", limit_usd=3.0, needed_usd=4.0)
    got = asyncio.run(live(tmp_path, FakeCalls([stop]), monkeypatch).ask(frames(0), [], bar=24))
    assert (got.missing, got.budget_cause) == ([0], "daily_cap")


def test_with_bar_and_image_part() -> None:
    img = rt.with_bar(np.zeros((20, 30, 3), np.uint8), 7, 24)
    assert img.shape == (44, 30, 3)
    assert int(img[:24].max()) > 0  # the label is drawn in the bar
    assert rt.image_part(img)["image_url"].startswith("data:image/jpeg;base64,")
    merged = rt.merge_frames(output(1, 1, 5), {1})
    assert list(merged) == [1]


class CrashOnRecheck:
    """A detector that scans pass 1 fully, then dies on the first re-check (pass 2)."""

    def __init__(self, frames: int) -> None:
        self.frames, self.calls, self.inner = frames, 0, YuNet()

    @property
    def model(self) -> AuditorModel:
        return "yunet-face"

    @property
    def detects_plates(self) -> bool:
        return False

    def detect(self, frame: Frame) -> list[Detection]:
        self.calls += 1
        if self.calls > self.frames:
            raise RuntimeError("GPU lost")
        return self.inner.detect(frame)


def test_a_crash_while_rechecking_a_fix_is_never_clean(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    drop(job_dir, "i_2", {30, 31, 32})
    audit_run(job_dir, replay=True, settings=SETTINGS, detector=CrashOnRecheck(60))
    audit = audit_of(job_dir)
    assert audit.frames_scanned == 60
    assert audit.unresolved > 0
    assert audit.blocked_reason == "audit_failed"
    contracts.validate_job_dir(job_dir)


class Silent:
    """A red-team that leaves frames out without admitting it."""

    async def ask(self, frames: Sequence[tuple[int, Frame]], approved: Sequence[str], *, bar: int) -> Answer:
        return Answer(findings={})


def test_frames_a_red_team_silently_skips_are_unresolved(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Silent())
    audit = audit_of(job_dir)
    assert (audit.blocked_reason, audit.unresolved >= 2) == ("audit_failed", True)


def test_a_re_run_keeps_the_earlier_fixes_on_record(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    drop(job_dir, "i_2", {30, 31, 32})
    audit_run(job_dir, replay=True, settings=SETTINGS)
    first = audit_of(job_dir)
    assert first.leaks
    guard_run(job_dir)
    render(job_dir)
    audit_run(job_dir, replay=True, settings=SETTINGS)
    second = audit_of(job_dir)
    assert {(leak.frame, leak.patched_item) for leak in first.leaks} <= {(leak.frame, leak.patched_item)
                                                                         for leak in second.leaks}  # fmt: skip
    assert second.unresolved == 0
    contracts.validate_job_dir(job_dir)


def test_a_malformed_box_keeps_its_finding_as_a_whole_frame_leak() -> None:
    """redteam.md: a finding whose box isn't 4 integers stays a leak with a whole-frame box; the frame's other
    findings, and the response, still stand."""
    raw = {"frames": [{"frame": 0, "findings": [
        {"kind": "face", "detail": "d", "text": None, "box": [1.5, 2, 3, 4], "confidence": "low"},
        {"kind": "face", "detail": "d", "text": None, "box": [10, None, 30, 40], "confidence": "low"},
        {"kind": "plate", "detail": "d", "text": "KDA", "box": [10, 20, 30, 40], "confidence": "high"},
    ]}]}  # fmt: skip
    got = RedteamOutput.model_validate_json(json.dumps(raw))
    boxes = [f.box for f in got.frames[0].findings]
    assert boxes == [[], [], [10, 20, 30, 40]]
    assert rules.grid_box(boxes[0], width=320, height=240, bar=40) is None  # → the whole frame


class RaisesOnSecondAsk(Scripted):
    """A red team whose second ask dies with an error nothing in the loop catches (a bug, a lost worker)."""

    async def ask(self, frames: Sequence[tuple[int, Frame]], approved: Sequence[str], *, bar: int) -> Answer:
        if self.asked:
            raise RuntimeError("worker lost")
        return await super().ask(frames, approved, bar=bar)


def test_a_crash_part_way_never_leaves_the_old_clean_verdict(tmp_path: Path) -> None:
    """redteam.md "Never default to clean": the audit retires the receipt and blocks audit.json before it changes
    anything, so a crash after patching leaves a blocked audit and no receipt, never the old clean ones."""
    job_dir = prepared(tmp_path)
    audit_run(job_dir, replay=True, settings=SETTINGS)
    pipeline.approve(job_dir, how="auto_policy")
    receipt_run(job_dir, settings=SETTINGS)
    drop(job_dir, "i_2", {30, 31, 32})
    with pytest.raises(RuntimeError, match="worker lost"):
        audit_run(job_dir, replay=True, settings=SETTINGS, redteam=RaisesOnSecondAsk({}))
    audit = audit_of(job_dir)
    assert (audit.blocked_reason, audit.unresolved) == ("audit_failed", 60)
    assert not (job_dir / "receipt.json").exists()
    with pytest.raises(ReceiptError, match=r"current redacted\.mp4"):  # no audit finished on this video: no receipt
        receipt_run(job_dir, settings=SETTINGS)


def test_the_audit_redraws_a_video_drawn_from_another_plan(tmp_path: Path) -> None:
    """A crash between writing a patched plan and finishing its render leaves an old video: the next audit redraws
    it from the current plan before checking anything."""
    job_dir = prepared(tmp_path)
    plan = load(job_dir / "plan.json", Plan)
    drop(job_dir, "i_2", {30, 31, 32})  # the video now lacks the bystander on 30-32 ...
    dump(plan, job_dir / "plan.json")  # ... while the plan on disk covers them (the render never ran)
    audit_run(job_dir, replay=True, settings=SETTINGS)
    audit = audit_of(job_dir)
    assert not [leak for leak in audit.leaks if leak.frame in (30, 31, 32)]  # redrawn: nothing leaked there
    assert audit.unresolved == 0


def test_a_frame_whose_detections_were_not_all_judged_is_unscanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_dir = prepared(tmp_path)
    real = rules.excluded_by

    def flaky(kind: Any, box: Any, frame: int, decisions: Any, by_track: Any) -> str | None:
        if frame == 59:
            raise RuntimeError("judging failed")
        return real(kind, box, frame, decisions, by_track)

    monkeypatch.setattr(rules, "excluded_by", flaky)
    audit_run(job_dir, replay=True, settings=SETTINGS)
    audit = audit_of(job_dir)
    assert audit.frames_scanned < 60
    assert audit.blocked_reason == "audit_failed"


class Moving(Scripted):
    """A red team that reads text on frame 30 at a new place on every ask (each patch lands where it was)."""

    async def ask(self, frames: Sequence[tuple[int, Frame]], approved: Sequence[str], *, bar: int) -> Answer:
        x = 100 + 50 * len(self.asked)
        self.script = {30: [finding("text", grid((x, 60, x + 40, 80)), "AMINA K.")]}
        return await super().ask(frames, approved, bar=bar)


def test_a_re_run_never_forgets_a_leak_it_left_unresolved(tmp_path: Path) -> None:
    """Run 1 ends with an unresolved text leak no patch covers (found in its last pass). Run 2, on that same video,
    with a model that now says nothing: the leak is found again and patched, never silently dropped."""
    job_dir = prepared(tmp_path)
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Moving({}))
    one = audit_of(job_dir)
    assert one.blocked_reason == "unresolved_leaks"
    (left,) = [x for x in one.leaks if x.unresolved]
    silent = Scripted({})
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=silent)
    two = audit_of(job_dir)
    assert two.passes >= 2  # found again from the record and patched (the model alone found nothing)
    again = [x for x in two.leaks if (x.frame, x.box) == (left.frame, left.box)]
    assert again
    assert all(x.patched_item is not None and not x.unresolved for x in again)
    assert left.frame in silent.asked[0]  # and its frame was asked again
    contracts.validate_job_dir(job_dir)


def test_a_crash_while_patching_keeps_the_leaks_and_rechecks_the_fixes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_dir = prepared(tmp_path)
    leak = finding("text", grid((100, 60, 140, 80)), "AMINA K.")

    def crash(_: Path) -> Path:
        raise RuntimeError("render died")

    monkeypatch.setattr(loop, "render", crash)
    with pytest.raises(RuntimeError, match="render died"):
        audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted({30: [leak]}))
    monkeypatch.undo()
    rerun = Scripted({})
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=rerun)
    audit = audit_of(job_dir)
    assert [x.frame for x in audit.leaks if x.detector == "redteam"] == [30]  # kept on record
    assert 30 in rerun.asked[0]  # and the fix re-read by the model
    assert not (job_dir / "raw/audit/pending.json").exists()
    contracts.validate_job_dir(job_dir)


def test_a_blocked_re_run_keeps_its_detector_leaks_valid(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    drop(job_dir, "i_2", {30, 31, 32})
    audit_run(job_dir, replay=True, settings=SETTINGS)
    audit_run(job_dir, replay=True, settings=SETTINGS, detector=CrashOnRecheck(0))
    audit = audit_of(job_dir)
    assert audit.blocked_reason == "audit_failed"
    assert audit.egoblur.faces is not None
    contracts.validate_job_dir(job_dir)


def test_a_mosaic_read_through_never_counts_as_cover_for_its_unresolved_leak() -> None:
    plan = Plan.model_validate({
        "padding": {"face": 0.15, "default": 0.08, "px": 8},
        "temporal": {"extend": 8, "backfill": 15, "gap_hold_s": 2.0},
        "frames": {30: [{"item_id": "i_2", "shape": "box", "box": (90, 50, 150, 110), "mask": None,
                         "style": "pixelate", "grid": (90, 50, 10)}]},
    })  # fmt: skip
    read = Leak(frame=30, box=(100, 60, 140, 80), kind="text", detector="redteam", patched_item=None,
                flag="redaction_too_weak", through_item="i_2", unresolved=True)  # fmt: skip
    (again,) = loop.reopened([read], plan, Decisions(items=[]), height=240, width=320)
    assert (again.unresolved, again.through_item) == (False, "i_2")
    solid = plan.model_copy(update={"frames": {30: [plan.frames[30][0].model_copy(update={"style": "solid",
                                                                                         "grid": None})]}})  # fmt: skip
    assert loop.reopened([read], solid, Decisions(items=[]), height=240, width=320) == []


@pytest.mark.parametrize("dies_on", ["plan.json", "decisions.json"])
def test_a_crash_between_plan_and_decisions_is_re_planned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dies_on: str
) -> None:
    """A text leak only the red team can see is patched; the process dies writing one of the two files. The re-run,
    with a model that now says nothing, still leaves a plan that renders the patch over the leak."""
    job_dir = prepared(tmp_path)
    box = (100, 60, 140, 80)
    real = loop.dump

    def dies(model: Any, path: Path) -> Path:
        if path.name == dies_on and path.parent == job_dir:
            patched = (isinstance(model, Decisions) and any(i.origin == "audit_patch" for i in model.items)) or (
                isinstance(model, Plan) and any(e.source == "audit_patch" for es in model.frames.values() for e in es)
            )
            if patched:
                raise RuntimeError("killed")
        return real(model, path)

    monkeypatch.setattr(loop, "dump", dies)
    with pytest.raises(RuntimeError, match="killed"):
        audit_run(
            job_dir, replay=True, settings=SETTINGS, redteam=Scripted({30: [finding("text", grid(box), "AMINA")]})
        )
    monkeypatch.undo()
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted({}))
    contracts.validate_job_dir(job_dir)  # the plan and the decisions agree again
    plan = load(job_dir / "plan.json", Plan)
    assert any(e.source == "audit_patch" and g_contains(e.box, box) for e in plan.frames[30])


def test_a_crash_right_after_the_placeholder_never_forgets_an_unresolved_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_dir = prepared(tmp_path)
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Moving({}))
    (left,) = [x for x in audit_of(job_dir).leaks if x.unresolved]

    def dies(*_: Any) -> bool:
        raise RuntimeError("killed after the placeholder")

    monkeypatch.setattr(loop, "planned_in_full", dies)
    with pytest.raises(RuntimeError, match="killed"):
        audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted({}))
    assert audit_of(job_dir).blocked_reason == "audit_failed"  # the placeholder
    monkeypatch.undo()
    audit_run(job_dir, replay=True, settings=SETTINGS, redteam=Scripted({}))
    again = [x for x in audit_of(job_dir).leaks if (x.frame, x.box) == (left.frame, left.box)]
    assert again
    assert all(x.patched_item is not None for x in again)


def test_a_mask_entry_covers_only_its_mask_not_its_box() -> None:
    mask = np.zeros((240, 320), dtype=np.bool_)
    mask[50:110, 220:280] = True
    mask[50:60, 270:280] = False  # the top-right corner is outside the outline
    entry = {"item_id": "i_2", "shape": "mask", "box": (220, 50, 280, 110), "mask": encode(mask).model_dump(),
             "style": "solid", "grid": None}  # fmt: skip
    plan = Plan.model_validate({
        "padding": {"face": 0.15, "default": 0.08, "px": 8},
        "temporal": {"extend": 8, "backfill": 15, "gap_hold_s": 2.0}, "frames": {30: [entry]},
    })  # fmt: skip
    corner = Leak(frame=30, box=(270, 50, 280, 60), kind="text", detector="redteam", patched_item=None,
                  unresolved=True)  # fmt: skip
    inside = corner.model_copy(update={"box": (230, 70, 250, 90)})
    got = loop.reopened([corner, inside], plan, Decisions(items=[]), height=240, width=320)
    assert [x.box for x in got] == [(270, 50, 280, 60)]


def test_faces_are_counted_on_the_pass_that_first_scans_a_frame(tmp_path: Path) -> None:
    """Pass 1's detector dies at once; pass 2 (after a patch) scans every frame: the faces are counted there."""
    job_dir = prepared(tmp_path)
    clean = prepared(tmp_path / "clean")
    audit_run(clean, replay=True, settings=SETTINGS)
    faces = audit_of(clean).egoblur.faces
    assert faces

    class DiesFirst(CrashOnRecheck):
        def detect(self, frame: Frame) -> list[Detection]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("GPU lost")
            return self.inner.detect(frame)

    leak = finding("text", grid((100, 60, 140, 80)), "AMINA K.")
    audit_run(job_dir, replay=True, settings=SETTINGS, detector=DiesFirst(0), redteam=Scripted({30: [leak]}, once=True))
    audit = audit_of(job_dir)
    assert audit.frames_scanned == 60
    assert audit.egoblur.faces is not None
    assert audit.egoblur.faces > 0
