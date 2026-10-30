"""WP5 step 1: the stage registry, the pipeline's resume/cap/approval rules, the replay network guard and the CLI."""

from __future__ import annotations

import dataclasses
import json
import shutil
import socket
import sys
import types
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecut import netguard, pipeline
from safecut.cli import app
from safecut.config import Settings
from safecut.contracts import (
    JOB_FILES,
    Approval,
    CostLine,
    DecisionItem,
    Decisions,
    Intake,
    Job,
    append_cost_line,
    dump,
    load,
)
from safecut.stages import APPROVAL, INTAKE, REDACTED, STAGES, Stage, StageError, StageUnavailable, phase, stage

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"
CLIP = Path(__file__).resolve().parent.parent / "fixtures" / "clips" / "counter_24fps.mp4"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_lists_every_stage_in_pipeline_order() -> None:
    assert [s.name for s in STAGES] == [
        "prepare",
        "track",
        "transcribe",
        "scene",
        "roles",
        "decide",
        "guard",
        "render",
        "audit",
        "receipt",
    ]
    assert [s.name for s in phase("analyse")][-1] == "guard"
    assert [s.name for s in phase("publish")] == ["render", "audit", "receipt"]
    for s in STAGES:
        assert s.output in JOB_FILES or s.output == REDACTED
    assert stage("render").inputs[-1] == APPROVAL


def test_unknown_stage_names_the_known_ones() -> None:
    with pytest.raises(KeyError, match="known: prepare"):
        stage("nope")


def _module(name: str, run: Callable[..., Path] | None) -> Iterator[None]:
    module = types.ModuleType(name)
    if run is not None:
        module.run = run  # type: ignore[attr-defined] -- a stand-in stage module built for the test
    sys.modules[name] = module
    yield
    del sys.modules[name]


def test_missing_module_is_unavailable_and_names_the_lane() -> None:
    missing = Stage("x", "safecut.no_such_stage", "job.json", (), "SAFECUT-SENSE", "analyse", paid=False)
    with pytest.raises(StageUnavailable, match="lane SAFECUT-SENSE"):
        missing.runner()


def test_a_module_whose_own_import_fails_is_not_hidden_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fake_broken_stage.py").write_text("import fake_dependency_that_is_absent\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    broken = Stage("x", "fake_broken_stage", "job.json", (), "SAFECUT-SENSE", "analyse", paid=False)
    with pytest.raises(ModuleNotFoundError, match="fake_dependency_that_is_absent"):
        broken.runner()
    nested = Stage("x", "fake_broken_parent.child", "job.json", (), "SAFECUT-SENSE", "analyse", paid=False)
    with pytest.raises(StageUnavailable):
        nested.runner()


def test_runner_rejects_a_run_without_keyword_only_replay() -> None:
    gen = _module("tests.fake_positional", lambda job_dir, replay=False: job_dir)
    next(gen)
    try:
        with pytest.raises(StageError, match="keyword-only"):
            Stage("x", "tests.fake_positional", "job.json", (), "SAFECUT-SENSE", "analyse", paid=False).runner()
    finally:
        next(gen, None)
    gen = _module("tests.fake_no_run", None)
    next(gen)
    try:
        with pytest.raises(StageError, match="no run"):
            Stage("x", "tests.fake_no_run", "job.json", (), "SAFECUT-SENSE", "analyse", paid=False).runner()
    finally:
        next(gen, None)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _example_job(job_dir: Path) -> Job:
    data = json.loads((EXAMPLE / "job.json").read_text())
    data["job_id"] = job_dir.name
    return Job.model_validate(data)


class FakeStages:
    """Stand-in stage modules registered under ``tests.fake_stage_<n>``, counting their calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.names: list[str] = []

    def make(
        self,
        output: str,
        *,
        paid: bool = False,
        inputs: tuple[str, ...] = (INTAKE,),
        write: Callable[[Path], object] | None = None,
    ) -> Stage:
        name = f"tests.fake_stage_{len(self.names)}"

        def run(job_dir: Path, *, replay: bool = False) -> Path:
            self.calls.append(f"{output}:{'replay' if replay else 'live'}")
            if write is not None:
                write(job_dir)
            else:
                (job_dir / output).write_text(_example_job(job_dir).model_dump_json())
            return job_dir / output

        module = types.ModuleType(name)
        module.run = run  # type: ignore[attr-defined] -- stand-in stage module
        sys.modules[name] = module
        self.names.append(name)
        return Stage(output, name, output, inputs, "SAFECUT-SENSE", "analyse", paid=paid)

    def close(self) -> None:
        for name in self.names:
            sys.modules.pop(name, None)


@pytest.fixture
def fakes() -> Iterator[FakeStages]:
    made = FakeStages()
    yield made
    made.close()


@pytest.fixture
def job(tmp_path: Path) -> Path:
    job_dir = tmp_path / "j_test"
    pipeline.create_job(CLIP, job_dir, created_at=datetime(2026, 10, 30, tzinfo=UTC))
    return job_dir


def test_create_job_copies_the_clip_and_writes_intake(job: Path) -> None:
    intake = load(job / INTAKE, Intake)
    assert intake.source == CLIP.name
    assert intake.mode == "live"
    assert intake.consented is False
    assert pipeline.source_clip(job).read_bytes() == CLIP.read_bytes()
    with pytest.raises(pipeline.PipelineError, match="already holds a job"):
        pipeline.create_job(CLIP, job)
    with pytest.raises(pipeline.PipelineError, match="no such clip"):
        pipeline.create_job(job / "missing.mp4", job.parent / "other")


def test_a_finished_stage_is_skipped_until_an_input_or_its_output_changes(job: Path, fakes: FakeStages) -> None:
    s = fakes.make("job.json")
    assert pipeline.run_stage(job, s, replay=False).event == "done"
    assert pipeline.run_stage(job, s, replay=False).event == "skipped"
    assert fakes.calls == ["job.json:live"]
    intake = load(job / INTAKE, Intake)
    (job / INTAKE).write_text(intake.model_copy(update={"consented": True}).model_dump_json())
    assert pipeline.run_stage(job, s, replay=False).event == "done"
    (job / "job.json").write_text((job / "job.json").read_text() + " ")
    assert pipeline.run_stage(job, s, replay=False).event == "done"
    assert pipeline.run_stage(job, s, replay=False, force=True).event == "done"
    events = [e["event"] for e in pipeline.read_log(job) if e["stage"] == "job.json"]
    assert events.count("done") == 4
    assert events.count("skipped") == 1
    assert all(e["job_id"] == "j_test" for e in pipeline.read_log(job))


def test_a_failed_stage_is_logged_and_reruns(job: Path, fakes: FakeStages) -> None:
    def boom(job_dir: Path) -> None:
        raise RuntimeError("model said no")

    failing = fakes.make("job.json", write=boom)
    with pytest.raises(RuntimeError, match="model said no"):
        pipeline.run_stage(job, failing, replay=False)
    last = list(pipeline.read_log(job))[-1]
    assert last["event"] == "failed"
    assert "model said no" in last["error"]
    assert not pipeline.is_fresh(job, failing)


def test_a_torn_log_line_is_ignored_and_the_stage_reruns(job: Path, fakes: FakeStages) -> None:
    s = fakes.make("job.json")
    pipeline.run_stage(job, s, replay=False)
    with (job / "job_log.jsonl").open("a") as handle:
        handle.write('{"stage": "job.json", "event": "do')
    assert pipeline.is_fresh(job, s)


def test_an_invalid_output_fails_the_stage(job: Path, fakes: FakeStages) -> None:
    s = fakes.make("job.json", write=lambda d: (d / "job.json").write_text('{"job_id": 1}'))
    with pytest.raises(pipeline.StageOutputInvalid, match=r"job\.json"):
        pipeline.run_stage(job, s, replay=False)
    missing = fakes.make("tracks.json", write=lambda d: None)
    with pytest.raises(pipeline.StageOutputInvalid, match="did not write"):
        pipeline.run_stage(job, missing, replay=False)


def _cost(job: Path, usd: float, *, estimated: bool = False) -> None:
    append_cost_line(
        CostLine(
            ts=datetime.now(UTC),
            provider="meta",
            job_id=job.name,
            stage="track",
            model="sam-3.1",
            attempt=1,
            units={"frames": 50.0},
            usd=usd,
            estimated=estimated,
            request_id=None,
            cap=None,
            code_kind="owner",
            code_id=None,
        ),
        job / "cost.jsonl",
    )


def test_the_job_cap_stops_a_paid_stage_before_it_runs(job: Path, fakes: FakeStages) -> None:
    paid = fakes.make("job.json", paid=True)
    _cost(job, 1.0)
    _cost(job, 0.5, estimated=True)
    assert pipeline.job_spend(job) == pytest.approx(1.5)
    with pytest.raises(pipeline.JobCapReached, match=r"1\.5000"):
        pipeline.run_stage(job, paid, replay=False, settings=Settings(job_usd_cap=1.5))
    assert fakes.calls == []
    assert pipeline.run_stage(job, paid, replay=False, settings=Settings(job_usd_cap=1.6)).event == "done"
    free = fakes.make("tracks.json", write=lambda d: shutil.copy(EXAMPLE / "tracks.json", d / "tracks.json"))
    assert pipeline.run_stage(job, free, replay=False, settings=Settings(job_usd_cap=0.01)).event == "done"


def test_replay_never_reaches_the_network_and_skips_the_cap(job: Path, fakes: FakeStages) -> None:
    def dial(job_dir: Path) -> None:
        socket.create_connection(("192.0.2.1", 443), timeout=1)

    dialing = fakes.make("job.json", paid=True, write=dial)
    with pytest.raises(netguard.NetworkBlocked):
        pipeline.run_stage(job, dialing, replay=True, settings=Settings(job_usd_cap=0.01))
    assert not netguard.active()
    _cost(job, 5.0)
    ok = fakes.make("job.json", paid=True)
    assert pipeline.run_stage(job, ok, replay=True, settings=Settings(job_usd_cap=0.01)).event == "done"
    assert fakes.calls[-1] == "job.json:replay"


def test_approval_pins_the_decisions_it_approved(job: Path) -> None:
    with pytest.raises(pipeline.PipelineError, match="nothing to approve"):
        pipeline.approve(job, how="review")
    with pytest.raises(pipeline.NotApproved, match="not been approved"):
        pipeline.check_approval(job)
    shutil.copy(EXAMPLE / "decisions.json", job / "decisions.json")
    shutil.copy(EXAMPLE / "plan.json", job / "plan.json")
    approval = pipeline.approve(job, how="auto_policy")
    assert load(job / APPROVAL, Approval) == approval
    assert pipeline.check_approval(job).how == "auto_policy"
    assert pipeline.status(job) == "publishing"
    decisions = load(job / "decisions.json", Decisions)
    flipped = next(i for i in decisions.items if i.decision == "hide" and not i.locked)
    edited = flipped.model_copy(update={"decision": "keep", "style": None, "decided_by": "creator"})
    dump(Decisions(items=[edited if i is flipped else i for i in decisions.items]), job / "decisions.json")
    with pytest.raises(pipeline.NotApproved, match="changed after approval"):
        pipeline.publish(job, replay=True)


def _patch(n: int) -> DecisionItem:
    return DecisionItem(
        item_id=f"p_{n}",
        track_ids=[],
        kind="other",
        decision="hide",
        reason="Added by the audit: the final check found this after rendering and covered it.",
        evidence_frames=[3],
        style="solid",
        decided_by="policy",
        locked=True,
        origin="audit_patch",
        audit_label=f"A{n}",
        box=(0, 0, 10, 10),
        first=2,
        last=4,
    )


def test_an_audit_patch_after_approval_keeps_the_approval(job: Path) -> None:
    """The audit appends locked ``p_<n>`` hides after approval (API-NOTES §12): a re-run of the audit, or a
    publish resumed after a crash, must still find the plan approved; any other change still needs approving."""
    shutil.copy(EXAMPLE / "decisions.json", job / "decisions.json")
    shutil.copy(EXAMPLE / "plan.json", job / "plan.json")
    pipeline.approve(job, how="review")
    decisions = load(job / "decisions.json", Decisions)
    dump(Decisions(items=[*decisions.items, _patch(2), _patch(3)]), job / "decisions.json")
    assert pipeline.check_approval(job).how == "review"
    first = decisions.items[0]
    reworded = first.model_copy(update={"reason": first.reason + " (edited)"})
    dump(Decisions(items=[reworded, *decisions.items[1:], _patch(2)]), job / "decisions.json")
    with pytest.raises(pipeline.NotApproved, match="changed after approval"):
        pipeline.check_approval(job)


def test_a_stage_that_rewrites_an_earlier_output_keeps_that_stage_fresh(job: Path, fakes: FakeStages) -> None:
    """roles appends the miss loop's tracks to tracks.json (WP2 step 5): track must not read as stale afterwards,
    or a resume would re-run SAM (paid) and drop the miss-loop tracks."""
    track = fakes.make("tracks.json", write=lambda d: shutil.copy(EXAMPLE / "tracks.json", d / "tracks.json"))

    def roles_writes(d: Path) -> None:
        shutil.copy(EXAMPLE / "roles.json", d / "roles.json")
        (d / "tracks.json").write_text((d / "tracks.json").read_text() + " ")  # the appended tracks

    roles = fakes.make("roles.json", inputs=("tracks.json",), write=roles_writes)
    roles = dataclasses.replace(roles, also_writes=("tracks.json",))
    pipeline.run_stage(job, track, replay=False)
    pipeline.run_stage(job, roles, replay=False)
    assert pipeline.is_fresh(job, track)
    assert pipeline.is_fresh(job, roles)
    assert pipeline.run_stage(job, track, replay=False).event == "skipped"
    (job / "tracks.json").write_text((job / "tracks.json").read_text() + "  ")  # anything else still counts
    assert not pipeline.is_fresh(job, track)


def test_the_audit_is_never_refused_by_the_cap_it_reports_itself(job: Path, fakes: FakeStages) -> None:
    """redteam.md: a cap that stops the audit ends ``blocked_reason: over_budget`` (needs_you, [Run the audit
    again]), so the pipeline lets a ``caps_itself`` stage run and record it instead of refusing up front."""
    audit = dataclasses.replace(fakes.make("job.json", paid=True), caps_itself=True)
    _cost(job, 5.0)
    assert pipeline.run_stage(job, audit, replay=False, settings=Settings(job_usd_cap=1.0)).event == "done"
    assert stage("audit").caps_itself
    assert not any(s.caps_itself for s in STAGES if s.name != "audit")
    assert stage("roles").also_writes == ("tracks.json",)


def test_status_follows_the_files(job: Path) -> None:
    assert pipeline.status(job) == "new"
    shutil.copy(EXAMPLE / "tracks.json", job / "tracks.json")
    assert pipeline.status(job) == "analysing"
    shutil.copy(EXAMPLE / "plan.json", job / "plan.json")
    assert pipeline.status(job) == "review"
    shutil.copy(EXAMPLE / "receipt.json", job / "receipt.json")
    assert pipeline.status(job) == "done"


def test_analyse_needs_an_intake_and_a_known_until(tmp_path: Path) -> None:
    with pytest.raises(pipeline.PipelineError, match="create the job first"):
        pipeline.analyse(tmp_path, replay=True)
    (tmp_path / INTAKE).write_text("{}")
    with pytest.raises(StageError, match="not in the analyse phase"):
        pipeline.analyse(tmp_path, replay=True, until="render")


def test_find_recording_matches_the_manifest_sha(tmp_path: Path) -> None:
    raw = tmp_path / "demo" / "raw"
    raw.mkdir(parents=True)
    (raw / "manifest.json").write_text(json.dumps({"source_sha256": "ab" * 32, "synthetic": True}))
    (tmp_path / "junk" / "raw").mkdir(parents=True)
    (tmp_path / "junk" / "raw" / "manifest.json").write_text("not json")
    assert pipeline.find_recording("ab" * 32, tmp_path) == tmp_path / "demo"
    assert pipeline.find_recording("cd" * 32, tmp_path) is None
    assert pipeline.find_recording("ab" * 32, tmp_path / "absent") is None
    job_dir = tmp_path / "j"
    job_dir.mkdir()
    pipeline.attach_recording(job_dir, tmp_path / "demo")
    assert (job_dir / "raw" / "manifest.json").is_file()
    with pytest.raises(pipeline.PipelineError, match="no raw/"):
        pipeline.attach_recording(job_dir, tmp_path / "nothing")


def test_source_clip_needs_exactly_one_file(tmp_path: Path) -> None:
    with pytest.raises(pipeline.PipelineError, match="found 0"):
        pipeline.source_clip(tmp_path)
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "a.mp4").write_bytes(b"a")
    (tmp_path / "source" / "b.mp4").write_bytes(b"b")
    with pytest.raises(pipeline.PipelineError, match="found 2"):
        pipeline.source_clip(tmp_path)


# ---------------------------------------------------------------------------
# Network guard
# ---------------------------------------------------------------------------


def test_netguard_blocks_outbound_but_not_loopback() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        with netguard.blocked():
            assert netguard.active()
            with pytest.raises(netguard.NetworkBlocked):
                socket.getaddrinfo("api.meta.ai", 443)
            with pytest.raises(netguard.NetworkBlocked):
                socket.create_connection(("192.0.2.1", 443), timeout=1)
            sock = socket.socket()
            with pytest.raises(netguard.NetworkBlocked):
                sock.connect_ex(("2001:db8::1", 443, 0, 0))
            sock.close()
            with socket.create_connection(("localhost", port), timeout=2):
                pass
            with netguard.blocked():  # nested: leaving the inner block keeps the outer one
                pass
            assert netguard.active()
        assert not netguard.active()
    finally:
        server.close()


@pytest.mark.parametrize(
    ("host", "local"),
    [
        (None, True),
        ("", True),
        ("localhost", True),
        ("127.0.0.5", True),
        ("::1", True),
        ("[::1]", True),
        (b"127.0.0.1", True),
        ("0.0.0.0", True),  # noqa: S104 -- a bind-all literal as test data
        ("api.meta.ai", False),
        ("10.0.0.1", False),
        (443, False),
        ("fe80::1%eth0", False),
    ],
)
def test_is_local(host: object, local: bool) -> None:
    assert netguard._is_local(host) is local  # pyright: ignore[reportPrivateUsage] -- unit under test


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

runner = CliRunner()


def test_cli_stage_that_is_not_built_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(self: Stage) -> None:
        raise StageUnavailable(self)

    monkeypatch.setattr(Stage, "runner", unavailable)
    pipeline.create_job(CLIP, tmp_path / "j")
    result = runner.invoke(app, ["track", "--job", str(tmp_path / "j"), "--replay"])
    assert result.exit_code == 3
    assert "stage 'track' is not in this build yet: safecut.track (lane SAFECUT-SENSE)" in result.output
    result = runner.invoke(app, ["validate", "--job", str(tmp_path)])
    assert result.exit_code == 4
    assert "job.json: missing" in result.output


def test_cli_validate_accepts_the_example_job(tmp_path: Path) -> None:
    shutil.copytree(EXAMPLE, tmp_path / "j_example")
    result = runner.invoke(app, ["validate", "--job", str(tmp_path / "j_example")])
    assert result.exit_code == 0, result.output
    assert "j_example: valid" in result.output


def test_cli_run_in_replay_needs_a_recording(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(CLIP), "--out", str(tmp_path / "j"), "--replay"])
    assert result.exit_code == 1
    assert "no recorded responses" in result.output
    assert not (tmp_path / "j").exists()


def test_cli_prepare_without_a_clip_or_intake_explains(tmp_path: Path) -> None:
    result = runner.invoke(app, ["prepare", "--job", str(tmp_path / "j"), "--live"])
    assert result.exit_code == 1
    assert "pass the clip" in result.output


def test_cli_approve_and_publish_report_typed_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["approve", "--job", str(tmp_path)])
    assert result.exit_code == 1
    assert "nothing to approve" in result.output
    result = runner.invoke(app, ["publish", "--job", str(tmp_path), "--live"])
    assert result.exit_code == 1
    assert "not been approved" in result.output


def test_cli_never_reports_a_blocked_audit_as_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "publish", lambda job, replay: [])
    blocked = types.SimpleNamespace(blocked_reason="unresolved_leaks", unresolved=4)
    monkeypatch.setattr("safecut.cli.load", lambda path, model: blocked)
    result = runner.invoke(app, ["publish", "--job", str(tmp_path), "--replay"])
    assert result.exit_code == 6
    assert "unresolved_leaks, 4 unresolved" in result.output
    monkeypatch.setattr("safecut.cli.load", lambda path, model: types.SimpleNamespace(blocked_reason=None))
    assert runner.invoke(app, ["publish", "--job", str(tmp_path), "--replay"]).exit_code == 0


def test_cli_runs_a_registered_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fakes: FakeStages) -> None:
    fake = fakes.make("job.json")
    monkeypatch.setattr(Stage, "runner", lambda self: sys.modules[fake.module].run)  # pyright: ignore[reportUnknownLambdaType, reportUnknownMemberType] -- routes every stage to the stand-in
    pipeline.create_job(CLIP, tmp_path / "j_cli")
    result = runner.invoke(app, ["prepare", "--job", str(tmp_path / "j_cli"), "--live"])
    assert result.exit_code == 0, result.output
    assert "prepare: wrote" in result.output
    assert load(tmp_path / "j_cli" / "job.json", Job).job_id == "j_cli"


def test_a_replay_is_synthetic_unless_its_manifest_says_otherwise(tmp_path: Path) -> None:
    assert pipeline.recording_is_synthetic(tmp_path) is False  # no recording: a live job
    raw = tmp_path / "raw"
    raw.mkdir()
    for content, expected in (
        ('{"synthetic": false}', False),
        ('{"synthetic": true}', True),
        ("{}", True),
        ("not json", True),
    ):
        (raw / "manifest.json").write_text(content)
        assert pipeline.recording_is_synthetic(tmp_path) is expected, content


def test_netguard_refuses_a_local_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("no_proxy", "localhost")
    try:
        assert port in netguard.proxy_ports()
        with netguard.blocked(), pytest.raises(netguard.NetworkBlocked):
            socket.create_connection(("127.0.0.1", port), timeout=2)
    finally:
        server.close()


def test_the_single_stage_audit_command_exits_6_on_a_blocked_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "check_approval", lambda job: None)
    monkeypatch.setattr(
        pipeline,
        "run_stage",
        lambda job, stage, replay, force: pipeline.StageResult(stage.name, "done", job / stage.output, 0.1),
    )
    monkeypatch.setattr(
        "safecut.cli.load", lambda path, model: types.SimpleNamespace(blocked_reason="audit_failed", unresolved=2)
    )
    for command in ("audit", "receipt"):
        result = runner.invoke(app, [command, "--job", str(tmp_path), "--replay"])
        assert result.exit_code == 6, (command, result.output)
