"""Round-trip and rule tests for every data contract (ARCHITECTURE.md §3, PRE-A §12)."""

from __future__ import annotations

import copy
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from safecut import contracts as c

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _raw(name: str) -> Any:
    return json.loads((EXAMPLE / name).read_text())


@pytest.mark.parametrize("name", sorted(c.JOB_FILES))
def test_example_round_trips(name: str, tmp_path: Path) -> None:
    model_type = c.JOB_FILES[name]
    first = c.load(EXAMPLE / name, model_type)
    out = c.dump(first, tmp_path / name)
    second = c.load(out, model_type)
    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_dump_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    job = c.load(EXAMPLE / "job.json", c.Job)
    c.dump(job, tmp_path / "nested" / "job.json")
    assert [p.name for p in (tmp_path / "nested").iterdir()] == ["job.json"]


def test_load_reports_missing_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(c.ContractError, match=r"job\.json: missing"):
        c.load(tmp_path / "job.json", c.Job)
    (tmp_path / "job.json").write_text("{not json")
    with pytest.raises(c.ContractError, match=r"job\.json: 1 error"):
        c.load(tmp_path / "job.json", c.Job)


def test_example_job_dir_passes_cross_file_checks() -> None:
    loaded = c.validate_job_dir(EXAMPLE)
    assert set(loaded) == set(c.JOB_FILES)


def test_unknown_keys_are_rejected() -> None:
    data = _raw("job.json") | {"fsp": 30}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        c.Job.model_validate(data)


# --- job.json ---------------------------------------------------------------


def test_job_times_must_match_frames_and_be_non_decreasing() -> None:
    data = _raw("job.json")
    with pytest.raises(ValidationError, match="times has"):
        c.Job.model_validate(data | {"times": data["times"][:-1]})
    bad = list(data["times"])
    bad[3], bad[4] = bad[4], bad[3]
    with pytest.raises(ValidationError, match="non-decreasing"):
        c.Job.model_validate(data | {"times": bad})
    repeated = list(data["times"])
    repeated[2] = repeated[1]
    assert c.Job.model_validate(data | {"times": repeated}).times[2] == repeated[1]


def test_job_fps_is_an_int_from_1_to_30_and_created_at_needs_a_zone() -> None:
    data = _raw("job.json")
    with pytest.raises(ValidationError):
        c.Job.model_validate(data | {"fps": 31})
    with pytest.raises(ValidationError):
        c.Job.model_validate(data | {"fps": 29.97})
    with pytest.raises(ValidationError, match="timezone"):
        c.Job.model_validate(data | {"created_at": "2026-10-27T10:00:00"})


# --- boxes ------------------------------------------------------------------


class _BoxHolder(BaseModel):
    box: c.Box


@given(
    x1=st.integers(0, 2000),
    y1=st.integers(0, 2000),
    w=st.integers(-5, 2000),
    h=st.integers(-5, 2000),
)
def test_box_accepts_exactly_non_empty_half_open_boxes(x1: int, y1: int, w: int, h: int) -> None:
    box = (x1, y1, x1 + w, y1 + h)
    if w > 0 and h > 0:
        assert _BoxHolder(box=box).box == box
    else:
        with pytest.raises(ValidationError, match="empty"):
            _BoxHolder(box=box)


def test_box_rejects_negative_corners() -> None:
    with pytest.raises(ValidationError, match="negative"):
        _BoxHolder(box=(-1, 0, 10, 10))


# --- tracks.json ------------------------------------------------------------


def test_track_id_must_match_concept_and_frames_stay_in_span() -> None:
    data = _raw("tracks.json")
    t = copy.deepcopy(data)
    t["tracks"][0]["track_id"] = "person:1"
    with pytest.raises(ValidationError, match="must start with its concept"):
        c.Tracks.model_validate(t)
    t = copy.deepcopy(data)
    t["tracks"][0]["boxes"]["10"] = [0, 0, 5, 5]
    with pytest.raises(ValidationError, match="outside"):
        c.Tracks.model_validate(t)


def test_track_ids_unique_and_static_tracks_have_no_masks() -> None:
    data = _raw("tracks.json")
    t = copy.deepcopy(data)
    t["tracks"][1]["track_id"] = "face:1"
    with pytest.raises(ValidationError, match="unique"):
        c.Tracks.model_validate(t)
    t = copy.deepcopy(data)
    t["tracks"][3]["masks"] = {"9": {"size": [720, 1280], "counts": "x"}}
    with pytest.raises(ValidationError, match="static track"):
        c.Tracks.model_validate(t)


def test_request_concept_is_null_exactly_for_object_prompts() -> None:
    data = _raw("tracks.json")
    t = copy.deepcopy(data)
    t["requests"][0]["kind"] = "object_prompt"
    with pytest.raises(ValidationError, match="concept is null"):
        c.Tracks.model_validate(t)
    t["requests"][0]["concept"] = None
    assert c.Tracks.model_validate(t).requests[0].concept is None


@pytest.mark.parametrize("file_id", ["file-abc123", "file_abc123", "file-000"])
def test_both_file_id_spellings_are_accepted(file_id: str) -> None:
    data = _raw("tracks.json")
    data["requests"][0]["file_id"] = file_id
    assert c.Tracks.model_validate(data).requests[0].file_id == file_id


def test_sam_object_must_point_at_a_request() -> None:
    data = _raw("tracks.json")
    data["tracks"][0]["sam_object"]["request"] = 9
    with pytest.raises(ValidationError, match="no requests"):
        c.Tracks.model_validate(data)


# --- transcript.json --------------------------------------------------------


def test_failed_transcript_shape() -> None:
    failed = {"status": "failed", "source": None, "source_kind": None, "degraded": True, "turns": []}
    assert c.Transcript.model_validate(failed).status == "failed"
    with pytest.raises(ValidationError, match="failed or skipped"):
        c.Transcript.model_validate(failed | {"degraded": False})


def test_transcript_turn_rules() -> None:
    data = _raw("transcript.json")
    t = copy.deepcopy(data)
    t["turns"][0]["speaker"] = "A"
    with pytest.raises(ValidationError, match="pattern"):
        c.Transcript.model_validate(t)
    t = copy.deepcopy(data)
    t["turns"].reverse()
    with pytest.raises(ValidationError, match="sorted"):
        c.Transcript.model_validate(t)
    t = copy.deepcopy(data)
    t["turns"][0]["end"] = -0.1
    with pytest.raises(ValidationError):
        c.Transcript.model_validate(t)


# --- scene.json / roles.json ------------------------------------------------


def test_scene_intro_fields_are_both_or_neither_and_approx_time_is_an_enum() -> None:
    data = _raw("scene.json")
    s = copy.deepcopy(data)
    s["participants"][0]["introduction_quote"] = None
    with pytest.raises(ValidationError, match="both set or both null"):
        c.Scene.model_validate(s)
    s = copy.deepcopy(data)
    s["candidate_objects"][0]["approx_time"] = "mid-clip"
    with pytest.raises(ValidationError):
        c.Scene.model_validate(s)


def test_failed_scene_has_no_model() -> None:
    data = _raw("scene.json") | {"status": "failed"}
    with pytest.raises(ValidationError, match="model is set exactly"):
        c.Scene.model_validate(data)
    assert c.Scene.model_validate(data | {"model": None}).status == "failed"


def test_failed_role_pass_leaves_every_track_unsure() -> None:
    data = _raw("roles.json") | {"status": "failed", "model": None}
    with pytest.raises(ValidationError, match="unsure"):
        c.Roles.model_validate(data)


def test_missed_needs_a_point_or_box_and_escalation_fields_need_escalation() -> None:
    data = _raw("roles.json")
    r = copy.deepcopy(data)
    r["missed"][0]["point"] = None
    r["missed"][0]["box"] = None
    with pytest.raises(ValidationError, match="point or a box"):
        c.Roles.model_validate(r)
    r = copy.deepcopy(data)
    r["tracks"][0]["escalation_frames"] = [1]
    with pytest.raises(ValidationError, match="without an escalation"):
        c.Roles.model_validate(r)


# --- decisions.json ---------------------------------------------------------


def test_children_are_locked_hides() -> None:
    item = _raw("decisions.json")["items"][0] | {"kind": "child"}
    with pytest.raises(ValidationError, match="children"):
        c.DecisionItem.model_validate(item)
    ok = item | {"decision": "hide", "style": "solid", "locked": True}
    assert c.DecisionItem.model_validate(ok).locked


def test_keep_has_no_style_and_hide_has_one() -> None:
    item = _raw("decisions.json")["items"][0]
    with pytest.raises(ValidationError, match="style is null"):
        c.DecisionItem.model_validate(item | {"style": "solid"})
    with pytest.raises(ValidationError, match="style is null"):
        c.DecisionItem.model_validate(item | {"decision": "hide"})


def test_audit_patch_rules() -> None:
    patch = _raw("decisions.json")["items"][4]
    for broken in (
        {"box": None},
        {"locked": False},
        {"track_ids": ["face:1"]},
        {"audit_label": None},
        {"last": 1},
    ):
        with pytest.raises(ValidationError, match="audit patch"):
            c.DecisionItem.model_validate(patch | broken)
    tracked = _raw("decisions.json")["items"][0]
    with pytest.raises(ValidationError, match="only for audit patches"):
        c.DecisionItem.model_validate(tracked | {"box": [0, 0, 5, 5]})


def test_decision_ids_and_labels_unique() -> None:
    data = _raw("decisions.json")
    d = copy.deepcopy(data)
    d["items"][1]["item_id"] = "i_1"
    with pytest.raises(ValidationError, match="item_id"):
        c.Decisions.model_validate(d)


# --- plan.json --------------------------------------------------------------


def test_plan_entry_shape_and_grid_rules() -> None:
    entry = _raw("plan.json")["frames"]["5"][0]
    with pytest.raises(ValidationError, match="mask is set exactly"):
        c.PlanEntry.model_validate(entry | {"shape": "mask"})
    with pytest.raises(ValidationError, match="grid is set exactly"):
        c.PlanEntry.model_validate(entry | {"style": "pixelate"})


# --- audit.json -------------------------------------------------------------


def test_publish_gate_invariant() -> None:
    data = _raw("audit.json")
    assert c.Audit.model_validate(data).publishable
    with pytest.raises(ValidationError, match="blocked_reason is set exactly"):
        c.Audit.model_validate(data | {"unresolved": 3})
    blocked = c.Audit.model_validate(data | {"unresolved": 3, "blocked_reason": "audit_failed"})
    assert not blocked.publishable
    with pytest.raises(ValidationError, match="audit_budget_cause"):
        c.Audit.model_validate(data | {"unresolved": 3, "blocked_reason": "over_budget"})
    over = data | {"unresolved": 3, "blocked_reason": "over_budget", "audit_budget_cause": "job_cap"}
    assert c.Audit.model_validate(over).audit_budget_cause == "job_cap"


def test_blocked_reason_is_required() -> None:
    data = _raw("audit.json")
    del data["blocked_reason"]
    with pytest.raises(ValidationError, match="blocked_reason"):
        c.Audit.model_validate(data)


def test_leak_link_rules() -> None:
    leak = _raw("audit.json")["leaks"][0]
    with pytest.raises(ValidationError, match="through_item"):
        c.Leak.model_validate(leak | {"flag": "redaction_too_weak"})
    with pytest.raises(ValidationError, match="unresolved leak"):
        c.Leak.model_validate(leak | {"unresolved": True})


def test_egoblur_counts_are_null_when_not_run() -> None:
    data = _raw("audit.json")
    data["egoblur"] = {"model": "yunet-face", "faces": 1, "plates": None}
    assert c.Audit.model_validate(data).egoblur.plates is None


# --- receipt.json -----------------------------------------------------------


def test_receipt_hash_is_checked_and_chains() -> None:
    first = c.load(EXAMPLE / "receipt.json", c.Receipt)
    tampered = first.model_dump(mode="json") | {"cost_usd": 0.01}
    with pytest.raises(ValidationError, match="hash does not match"):
        c.Receipt.model_validate(tampered)
    body = c.ReceiptBody.model_validate(
        {k: v for k, v in first.model_dump(mode="json").items() if k != "hash"} | {"prev_hash": first.hash}
    )
    second = c.Receipt.seal(body)
    assert second.prev_hash == first.hash
    assert second.hash != first.hash


def test_canonical_json_is_sorted_compact_utf8() -> None:
    assert c.canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'
    with pytest.raises(ValueError, match="Out of range"):
        c.canonical_json({"x": float("nan")})


@given(
    cost=st.floats(0, 100, allow_nan=False),
    notes=st.lists(st.text(max_size=40), max_size=3),
)
def test_receipt_seal_round_trips(cost: float, notes: list[str]) -> None:
    data = _raw("receipt.json")
    data.pop("hash")
    data["cost_usd"] = cost
    data["data_handling"]["notes"] = notes
    sealed = c.Receipt.seal(c.ReceiptBody.model_validate(data))
    again = c.Receipt.model_validate_json(sealed.model_dump_json())
    assert again.hash == sealed.hash


def test_store_flag_must_follow_store_by_model() -> None:
    dh = _raw("receipt.json")["data_handling"]
    with pytest.raises(ValidationError, match="any"):
        c.DataHandling.model_validate(dh | {"store": True})
    with pytest.raises(ValidationError, match="both"):
        c.DataHandling.model_validate(dh | {"no_store_param": ["sam-3.1"]})


# --- cost.jsonl and files.json ----------------------------------------------


def _cost(**overrides: Any) -> c.CostLine:
    base: dict[str, Any] = {
        "ts": "2026-10-27T10:00:00Z",
        "job_id": "j_01",
        "stage": "role",
        "model": "muse-spark-1.3",
        "attempt": 1,
        "units": {"input": 1000, "cached": 0, "output": 100, "reasoning": 50},
        "usd": 0.0017,
        "estimated": False,
        "request_id": "resp_1",
        "code_kind": "eval",
        "provider": "meta",
        "code_id": None,
    }
    return c.CostLine.model_validate(base | overrides)


def test_cost_line_rules() -> None:
    assert _cost().cap is None
    with pytest.raises(ValidationError, match="system"):
        _cost(job_id=None)
    assert _cost(job_id=None, code_kind="system", stage="healthz").job_id is None
    with pytest.raises(ValidationError, match="budget"):
        _cost(cap="job")
    stop = _cost(stage="budget:role", cap="test_line", usd=0, attempt=0, request_id=None, units={})
    assert stop.cap == "test_line"
    with pytest.raises(ValidationError, match="budget line"):
        _cost(stage="budget:role", cap="job", usd=0.1, attempt=0, request_id=None)


def test_cost_jsonl_append_read_and_measured_sum(tmp_path: Path) -> None:
    path = tmp_path / "cost.jsonl"
    c.append_cost_line(_cost(usd=0.5), path)
    c.append_cost_line(_cost(usd=0.25, estimated=True), path)
    c.append_cost_line(_cost(usd=0.125), path)
    lines = list(c.read_cost_lines(path))
    assert len(lines) == 3
    assert c.measured_usd(lines) == (0.625, 0.25)
    assert list(c.read_cost_lines(tmp_path / "absent.jsonl")) == []
    with path.open("a") as handle:
        handle.write('{"bad": 1}\n')
    with pytest.raises(c.ContractError, match="line 4"):
        list(c.read_cost_lines(path))


def test_files_index_orphans_and_live_lookup() -> None:
    index = c.load(EXAMPLE / "files.json", c.FilesIndex)
    assert index.all_deleted
    assert index.live("sam_proxy.mp4") is None
    orphan = {"name": "prepared.mp4", "sha256": "d" * 64, "file_id": None, "orphan": True}
    entries = [*_raw("files.json"), orphan | {"created_at": "2026-10-27T10:05:00Z"}]
    assert not c.FilesIndex.model_validate(entries).all_deleted
    with pytest.raises(ValidationError, match="orphan"):
        c.FileEntry.model_validate(orphan | {"orphan": False, "created_at": "2026-10-27T10:05:00Z"})
    live = [_raw("files.json")[0] | {"deleted_at": None}]
    found = c.FilesIndex.model_validate(live).live("sam_proxy.mp4")
    assert found is not None
    assert found.file_id == "file-123456"


# --- cross-file checks ------------------------------------------------------


def _copy_example(tmp_path: Path) -> Path:
    target = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, target)
    return target


def _edit(path: Path, fn: Any) -> None:
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def _edit_receipt(job_dir: Path, fn: Any) -> None:
    """Mutate receipt.json and re-seal it, so only the cross-file rule under test can fail."""
    path = job_dir / "receipt.json"
    data = json.loads(path.read_text())
    data.pop("hash")
    fn(data)
    path.write_text(c.Receipt.seal(c.ReceiptBody.model_validate(data)).model_dump_json())


@pytest.mark.parametrize(
    ("name", "mutate", "message"),
    [
        ("tracks.json", lambda d: d["tracks"][0]["boxes"].update({"5": [1200, 0, 1300, 50]}), "exceeds"),
        ("tracks.json", lambda d: d["tracks"][0]["masks"]["1"].update({"size": [360, 640]}), "mask size"),
        ("tracks.json", lambda d: d.update({"crowded_frames": [12]}), "job.frames"),
        ("plan.json", lambda d: d["frames"].update({"40": []}), "job.frames"),
        ("decisions.json", lambda d: d["items"][0].update({"track_ids": ["face:99"]}), "unknown track"),
        ("audit.json", lambda d: d["leaks"][0].update({"box": [200, 200, 260, 721]}), "exceeds"),
        ("transcript.json", lambda d: d.update({"source_kind": None, "source": None}), "source_kind"),
    ],
)
def test_cross_file_checks_catch_inconsistencies(tmp_path: Path, name: str, mutate: Any, message: str) -> None:
    job_dir = _copy_example(tmp_path)
    _edit(job_dir / name, mutate)
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_no_audio_clip_rejects_turns(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    _edit(job_dir / "job.json", lambda d: d.update({"audio": False}))
    with pytest.raises(c.ContractError, match="without audio"):
        c.validate_job_dir(job_dir)


def test_unmodified_example_copy_validates(tmp_path: Path) -> None:
    assert set(c.validate_job_dir(_copy_example(tmp_path))) == set(c.JOB_FILES)


def test_job_id_must_match_the_directory_name(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    renamed = job_dir.rename(tmp_path / "j_other")
    with pytest.raises(c.ContractError, match="job directory name"):
        c.validate_job_dir(renamed)


@pytest.mark.parametrize(
    ("name", "mutate", "message"),
    [
        ("roles.json", lambda d: d["tracks"][0].update({"track_id": "face:99"}), "unknown track face:99"),
        ("roles.json", lambda d: d["tracks"][0].update({"frames": [1, 12]}), "job.frames"),
        ("roles.json", lambda d: d["tracks"][1].update({"escalation_frames": [40]}), "job.frames"),
        ("roles.json", lambda d: d["objects"][0].update({"track_id": "screen:9"}), "unknown track screen:9"),
        ("roles.json", lambda d: d["objects"][0].update({"frames": [12]}), "job.frames"),
        ("roles.json", lambda d: d["missed"][0].update({"frame": 12}), "job.frames"),
        ("roles.json", lambda d: d["missed"][0].update({"box": [1200, 500, 1300, 560]}), "exceeds"),
        ("roles.json", lambda d: d["missed"][0].update({"point": {"x": 1280, "y": 5}}), "outside"),
        ("roles.json", lambda d: d["missed"][0].update({"track_ids": ["envelope:9"]}), "unknown track envelope:9"),
        ("plan.json", lambda d: d["frames"]["5"][0].update({"item_id": "i_99"}), "unknown item i_99"),
        ("decisions.json", lambda d: d["items"][4].update({"box": [1250, 200, 1300, 280]}), "exceeds"),
        ("decisions.json", lambda d: d["items"][4].update({"first": 12, "last": 13}), "job.frames"),
        ("decisions.json", lambda d: d["items"][4].update({"last": 12}), "job.frames"),
        ("decisions.json", lambda d: d["items"][0].update({"evidence_frames": [1, 12]}), "job.frames"),
        (
            "audit.json",
            lambda d: d.update({"spots": [{"spot_id": "s1", "first": 1, "last": 2, "boxes": {"1": [0, 0, 1281, 5]}}]}),
            "exceeds",
        ),
        (
            "audit.json",
            lambda d: d.update({"spots": [{"spot_id": "s1", "first": 1, "last": 12, "boxes": {"12": [0, 0, 5, 5]}}]}),
            "job.frames",
        ),
        (
            "audit.json",
            lambda d: d.update({"spots": [{"spot_id": "s1", "first": 1, "last": 12, "boxes": {"3": [0, 0, 5, 5]}}]}),
            "job.frames",
        ),
    ],
)
def test_linked_file_checks_catch_inconsistencies(tmp_path: Path, name: str, mutate: Any, message: str) -> None:
    job_dir = _copy_example(tmp_path)
    _edit(job_dir / name, mutate)
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_roles_and_plan_links_are_skipped_when_the_other_file_is_absent(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    (job_dir / "tracks.json").unlink()
    (job_dir / "decisions.json").unlink()
    (job_dir / "receipt.json").unlink()
    assert "roles.json" in c.validate_job_dir(job_dir)


def _first_item_geometry(d: Any) -> None:
    d["items"][4]["box"] = [1250, 200, 1300, 280]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update({"job_id": "j_other"}), "receipt.json: job_id"),
        (lambda d: d["items"].pop(), r"missing \['p_1'\]"),
        (lambda d: d["items"].append(d["items"][0]), r"unexpected \['i_1'\]"),
        (lambda d: d["items"][1].update({"item_id": "i_9"}), r"missing \['i_2'\], unexpected \['i_9'\]"),
        (_first_item_geometry, "exceeds"),
        (lambda d: d["audit"].update({"leaks_found": 2}), "audit.leaks_found 2 != audit.json 1"),
        (lambda d: d["audit"].update({"frames_scanned": 11}), "audit.frames_scanned"),
        (lambda d: d["audit"].update({"passes": 3}), "audit.passes"),
        (lambda d: d["audit"].update({"unresolved": 1, "blocked_reason": "audit_failed"}), "audit.unresolved"),
    ],
)
def test_receipt_must_agree_with_the_job_files(tmp_path: Path, mutate: Any, message: str) -> None:
    job_dir = _copy_example(tmp_path)
    _edit_receipt(job_dir, mutate)
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_files_deleted_needs_every_upload_deleted(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    _edit(job_dir / "files.json", lambda d: d[0].update({"deleted_at": None}))
    with pytest.raises(c.ContractError, match="files_deleted is true"):
        c.validate_job_dir(job_dir)
    _edit_receipt(job_dir, lambda d: d["data_handling"].update({"files_deleted": False}))
    assert "receipt.json" in c.validate_job_dir(job_dir)


def test_receipt_cost_must_match_the_measured_meta_total(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    cost = job_dir / "cost.jsonl"
    cost.unlink()
    _edit_receipt(job_dir, lambda d: d.update({"cost_usd": 0.91}))
    for line in (
        _cost(job_id="j_example", usd=0.5),
        _cost(job_id="j_example", usd=0.41),
        _cost(job_id="j_example", usd=0.25, estimated=True),
        _cost(job_id="j_example", usd=7.0, provider="baseten"),
    ):
        c.append_cost_line(line, cost)
    with pytest.raises(c.ContractError, match=r"cost_usd_estimated 0\.0 != cost\.jsonl"):
        c.validate_job_dir(job_dir)
    _edit_receipt(job_dir, lambda d: d.update({"cost_usd_estimated": 0.25, "cost_usd_baseten": 7.0}))
    assert "receipt.json" in c.validate_job_dir(job_dir)
    _edit_receipt(job_dir, lambda d: d.update({"cost_usd": 0.92}))
    with pytest.raises(c.ContractError, match=r"cost_usd 0\.92 != cost\.jsonl"):
        c.validate_job_dir(job_dir)
    _edit_receipt(job_dir, lambda d: d.update({"cost_usd": 0.91 + 5e-7}))
    assert "receipt.json" in c.validate_job_dir(job_dir)


def test_example_cost_jsonl_matches_the_example_receipt() -> None:
    lines = list(c.read_cost_lines(EXAMPLE / "cost.jsonl"))
    assert lines
    assert {line.job_id for line in lines} == {"j_example"}
    receipt = c.load(EXAMPLE / "receipt.json", c.Receipt)
    assert c.measured_usd(lines) == pytest.approx((receipt.cost_usd, 0.0), abs=1e-6)
    assert c.measured_usd(lines, provider="baseten") == (0.0, 0.0)


def test_receipt_baseten_cost_must_match_the_measured_baseten_total(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    c.append_cost_line(_cost(job_id="j_example", usd=0.5, provider="baseten", stage="audit"), job_dir / "cost.jsonl")
    with pytest.raises(c.ContractError, match=r"cost_usd_baseten 0\.0 != cost\.jsonl Baseten total 0\.5"):
        c.validate_job_dir(job_dir)
    _edit_receipt(job_dir, lambda d: d.update({"cost_usd_baseten": 0.5}))
    assert "receipt.json" in c.validate_job_dir(job_dir)
    _edit_receipt(job_dir, lambda d: d.update({"cost_usd_baseten": 0.4}))
    with pytest.raises(c.ContractError, match=r"cost_usd_baseten 0\.4 != cost\.jsonl Baseten total 0\.5"):
        c.validate_job_dir(job_dir)


def test_baseten_cost_is_not_checked_without_cost_jsonl(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    (job_dir / "cost.jsonl").unlink()
    _edit_receipt(job_dir, lambda d: d.update({"cost_usd_baseten": 3.0, "cost_usd": 12.0}))
    assert "receipt.json" in c.validate_job_dir(job_dir)


def test_cost_jsonl_rejects_another_jobs_lines(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    c.append_cost_line(_cost(job_id="j_other", usd=0.5), job_dir / "cost.jsonl")
    with pytest.raises(c.ContractError, match=r"another job's line in this job's cost\.jsonl"):
        c.validate_job_dir(job_dir)


def test_cost_jsonl_rejects_system_lines(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    c.append_cost_line(
        _cost(job_id=None, code_kind="system", stage="healthz", model=None, usd=0.0, request_id=None),
        job_dir / "cost.jsonl",
    )
    with pytest.raises(c.ContractError, match=r"system line in this job's cost\.jsonl"):
        c.validate_job_dir(job_dir)


def _edit_decisions_and_receipt_item(job_dir: Path, field: str, value: Any) -> None:
    _edit_receipt(job_dir, lambda d: d["items"][2].update({field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason", "a different reason"),
        ("style", "solid"),
        ("decided_by", "creator"),
        ("locked", True),
        ("evidence_frames", [1, 2]),
        ("decision", "keep"),
    ],
)
def test_receipt_items_must_equal_decisions_item_by_item(tmp_path: Path, field: str, value: Any) -> None:
    job_dir = _copy_example(tmp_path)
    if field == "decision":
        _edit_receipt(job_dir, lambda d: d["items"][2].update({"decision": "keep", "style": None}))
    else:
        _edit_decisions_and_receipt_item(job_dir, field, value)
    with pytest.raises(c.ContractError, match=rf"receipt\.json i_3 differs from decisions\.json in .*{field}"):
        c.validate_job_dir(job_dir)


def test_receipt_item_thumbnail_may_differ_from_decisions(tmp_path: Path) -> None:
    job_dir = _copy_example(tmp_path)
    _edit_receipt(job_dir, lambda d: d["items"][2].update({"thumbnail": "thumbs/other.jpg"}))
    assert "receipt.json" in c.validate_job_dir(job_dir)
    _edit_receipt(job_dir, lambda d: d["items"][2].update({"thumbnail": None}))
    assert "receipt.json" in c.validate_job_dir(job_dir)


# --- path-like fields -------------------------------------------------------

BAD_RELATIVE_PATHS = [
    "../../../etc/passwd",
    "a/../../b.jpg",
    "thumbs/..",
    "/etc/passwd",
    "C:/Windows/x.jpg",
    "thumbs\\i_1.jpg",
    "a\x00b.jpg",
    "",
]


@pytest.mark.parametrize("bad", BAD_RELATIVE_PATHS)
def test_job_prepared_must_be_a_relative_path(bad: str) -> None:
    with pytest.raises(ValidationError):
        c.Job.model_validate(_raw("job.json") | {"prepared": bad})


@pytest.mark.parametrize("bad", BAD_RELATIVE_PATHS)
def test_roles_keyframes_must_be_relative_paths(bad: str) -> None:
    with pytest.raises(ValidationError):
        c.Roles.model_validate(_raw("roles.json") | {"keyframes": ["som/000001.jpg", bad]})


@pytest.mark.parametrize("bad", BAD_RELATIVE_PATHS)
def test_receipt_item_thumbnail_must_be_a_relative_path(bad: str) -> None:
    item = _raw("receipt.json")["items"][0]
    with pytest.raises(ValidationError):
        c.ReceiptItem.model_validate(item | {"thumbnail": bad})


def test_relative_paths_that_stay_inside_the_job_are_accepted() -> None:
    item = _raw("receipt.json")["items"][0]
    for good in ("thumbs/i_1.jpg", "./thumbs/i_1.jpg", "a..b/c.jpg", "..x/y"):
        assert c.ReceiptItem.model_validate(item | {"thumbnail": good}).thumbnail == good
    assert c.ReceiptItem.model_validate(item | {"thumbnail": None}).thumbnail is None
    assert c.Job.model_validate(_raw("job.json") | {"prepared": "clips/prepared.mp4"}).prepared == "clips/prepared.mp4"


def test_job_source_is_an_upload_name_so_only_traversal_and_nul_are_rejected() -> None:
    data = _raw("job.json")
    for bad in ("../../etc/passwd", "a/../b.mp4", "..\\..\\b.mp4", "a\x00.mp4", ""):
        with pytest.raises(ValidationError):
            c.Job.model_validate(data | {"source": bad})
    for good in ("SC-A-01.mp4", "/data/clips/SC-A-01.mp4", "https://example.com/a.mp4", "C:\\clips\\a.mp4"):
        assert c.Job.model_validate(data | {"source": good}).source == good


def test_now_utc_is_aware() -> None:
    assert c.now_utc().tzinfo is UTC
    assert c.now_utc() <= datetime.now(UTC)
