"""WP5 step 2: the API, end to end in replay with stand-in stages, plus auth, limits, caps, CORS, deletion, health.

The stand-in stages copy the contract files of ``fixtures/contracts/j_example`` (a cross-checked job) into the job,
so these tests exercise the API, the pipeline, the real WP3 review fold and the store, not the model stages
(``tests/test_e2e*.py`` covers the real stages once they are merged).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from safecut import pipeline
from safecut.api.access import RateLimiter
from safecut.api.app import Service, create_app, hero_job_id, safe_name
from safecut.api.store import JobStore
from safecut.config import AccessCode, CodeWindow, ServiceKey, Settings
from safecut.contracts import CostLine, Job, append_cost_line, load
from safecut.meta.budget import CapLimit
from safecut.stages import REDACTED, Stage
from tests.fake_stages import CLIP
from tests.fake_stages import fake_runner as _fake_runner

ROOT = Path(__file__).resolve().parent.parent
JUDGE = "judge-code-1234"
PILOT = "pilot-code-5678"
SERVICE_KEY = "sigmora-service-key-0123456789"
OPEN = CodeWindow(start=None, until=None)
WEB = "https://safecut.sigmora.org"


@pytest.fixture(autouse=True)
def fake_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Stage, "runner", _fake_runner)
    monkeypatch.setattr("safecut.api.app.auditor_available", lambda settings: True)
    # The stand-ins copy files from different example jobs, which don't cross-check; the gate itself is tested
    # below (test_a_job_whose_files_disagree_never_ends_done) and on the real stages (test_flow_on_the_real_stages).
    monkeypatch.setattr("safecut.api.worker.validate_job_dir", lambda job_dir: {})


def settings_for(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "jobs_dir": str(tmp_path / "jobs"),
        "replay": True,
        "access_codes": (
            AccessCode(code=SecretStr(JUDGE), kind="judge"),
            AccessCode(code=SecretStr(PILOT), kind="pilot", cap_usd=6.0),
        ),
        "service_keys": (ServiceKey(key=SecretStr(SERVICE_KEY), name="sigmora"),),
        "code_windows": {"judge": OPEN, "service": OPEN, "pilot": OPEN},
        "url_secret": SecretStr("test-url-secret"),
        "cors_origins": (WEB,),
    }
    values.update(overrides)
    return Settings(**values)


def recordings(tmp_path: Path) -> Path:
    root = tmp_path / "fixtures" / "jobs"
    raw = root / "demo" / "raw"
    raw.mkdir(parents=True)
    (raw / "manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": pipeline.sha256_file(CLIP),
                "source": "fixtures/clips/counter_24fps.mp4",
                "synthetic": True,
                "demo": True,
            }
        )
    )
    return root


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[..., tuple[TestClient, Service]]]:
    made: list[TestClient] = []

    def make(**overrides: Any) -> tuple[TestClient, Service]:
        svc = Service(
            settings_for(tmp_path, **overrides),
            fixtures=recordings(tmp_path) if not made else tmp_path / "fixtures" / "jobs",
        )
        client = TestClient(create_app(service=svc, background=False))
        client.__enter__()
        made.append(client)
        return client, svc

    yield make
    for client in made:
        client.__exit__(None, None, None)


def upload_clip(client: TestClient, *, code: str | None = JUDGE, headers: dict[str, str] | None = None) -> str:
    body: dict[str, Any] = {"size_bytes": CLIP.stat().st_size, "content_type": "video/mp4", "file_name": "My clip.mp4"}
    if code is not None:
        body["code"] = code
    created = client.post("/v1/jobs", json=body, headers=headers or {})
    assert created.status_code == 201, created.text
    data = created.json()
    put = client.put(data["upload_url"], content=CLIP.read_bytes(), headers={"Content-Type": "video/mp4"})
    assert put.status_code == 200, put.text
    return data["job_id"]


def run_to(client: TestClient, svc: Service, job_id: str, path: str, status: str) -> dict[str, Any]:
    response = client.post(f"/v1/jobs/{job_id}/{path}")
    assert response.status_code == 202, response.text
    svc.worker.wait(job_id)
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["status"] == status, job.get("failure")
    return job


# ---------------------------------------------------------------------------
# The flow
# ---------------------------------------------------------------------------


@pytest.mark.entry("E5:flow")
def test_full_flow_in_replay(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client()
    job_id = upload_clip(client)
    assert client.get(f"/v1/jobs/{job_id}").json()["status"] == "created"
    job = run_to(client, svc, job_id, "start", "review")
    assert job["mode"] == "replay"
    assert job["synthetic"] is True  # the recording's manifest says so, and every response carries it
    assert job["stage"] == "review"
    assert job["progress"] == 1.0
    assert job["job"]["frames"] == 12
    assert job["job"]["prepared_url"].startswith("/v1/jobs/")
    assert {"items", "tracks", "roles", "plan", "transcript", "scene"} <= job.keys()
    assert job["models"]["sam"] == "sam-3.1"
    item = next(i for i in job["items"] if i["decision"] == "needs_you")
    edit = {"type": "hide", "edit_id": "e-1", "item_id": item["item_id"]}
    acked = client.post(f"/v1/jobs/{job_id}/review", json=edit)
    assert acked.status_code == 200, acked.text
    body = acked.json()
    assert body["status"] == "review"
    assert body["edit_id"] == "e-1"
    assert next(i for i in body["items"] if i["item_id"] == item["item_id"])["decision"] == "hide"
    assert "frames" in body["plan"]
    again = client.post(f"/v1/jobs/{job_id}/review", json=edit)  # same edit_id: applied once
    assert again.json()["items"] == body["items"]
    assert len(json.loads((svc.store.path(job_id) / "review.json").read_text())) == 1
    done = run_to(client, svc, job_id, "render", "done")
    assert done["has_render"] is True
    assert set(done["result"]) == {"video_url", "receipt_html_url", "receipt_json_url"}
    result = client.get(f"/v1/jobs/{job_id}/result")
    assert result.status_code == 200
    urls = result.json()
    assert urls["mode"] == "replay"
    assert urls["audit"]["unresolved"] == 0
    video = client.get(urls["video_url"])
    assert video.status_code == 200
    assert video.content == CLIP.read_bytes()
    ranged = client.get(urls["video_url"], headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206
    assert len(ranged.content) == 100
    assert client.get(urls["receipt_html_url"]).headers["content-security-policy"].startswith("default-src 'none'")
    assert client.get(urls["captions_url"]).text.startswith("WEBVTT")
    assert client.delete(f"/v1/jobs/{job_id}").status_code == 204
    assert not svc.store.path(job_id).exists()
    assert client.get(f"/v1/jobs/{job_id}").status_code == 404
    assert client.delete(f"/v1/jobs/{job_id}").status_code == 404


def test_edits_after_done_move_back_to_review_and_needs_a_new_render(
    make_client: Callable[..., tuple[TestClient, Service]],
) -> None:
    client, svc = make_client()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    job = run_to(client, svc, job_id, "render", "done")
    item = next(i for i in job["items"] if i["decision"] == "needs_you")
    ack = client.post(f"/v1/jobs/{job_id}/review", json={"type": "hide", "edit_id": "late", "item_id": item["item_id"]})
    assert ack.json()["status"] == "review"
    assert ack.json()["has_render"] is True
    run_to(client, svc, job_id, "render", "done")


def test_review_refusals(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client()
    job_id = upload_clip(client)
    assert (
        client.post(f"/v1/jobs/{job_id}/review", json={"type": "hide", "edit_id": "x", "item_id": "i_1"}).json()[
            "error"
        ]["code"]
        == "not_reviewable"
    )
    run_to(client, svc, job_id, "start", "review")
    bad = client.post(f"/v1/jobs/{job_id}/review", json={"type": "explode", "edit_id": "x"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "bad_request"
    locked = client.post(f"/v1/jobs/{job_id}/review", json={"type": "keep", "edit_id": "k", "item_id": "i_99"})
    assert locked.status_code == 409
    with svc.store.update(job_id) as state:
        state.status = "needs_you"
    read_only = client.post(f"/v1/jobs/{job_id}/review", json={"type": "hide", "edit_id": "y", "item_id": "i_1"})
    assert read_only.json()["error"]["code"] == "read_only"


def test_start_and_render_refuse_out_of_order(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client()
    created = client.post(
        "/v1/jobs", json={"code": JUDGE, "size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"}
    ).json()
    start = client.post(f"/v1/jobs/{created['job_id']}/start")
    assert start.status_code == 409
    assert start.json()["error"]["code"] == "upload_incomplete"
    job_id = upload_clip(client)
    assert client.post(f"/v1/jobs/{job_id}/render").json()["error"]["code"] == "not_reviewable"
    run_to(client, svc, job_id, "start", "review")
    assert client.post(f"/v1/jobs/{job_id}/start").json()["error"]["code"] == "already_started"
    assert client.post(f"/v1/jobs/{job_id}/audit").json()["error"]["code"] == "not_needed"
    assert client.get(f"/v1/jobs/{job_id}/result").json()["error"]["code"] == "not_ready"


def test_replay_refuses_a_clip_with_no_recording(
    make_client: Callable[..., tuple[TestClient, Service]], tmp_path: Path
) -> None:
    client, _ = make_client()
    other = ROOT / "fixtures" / "clips" / "counter_30fps_audio.mp4"
    created = client.post(
        "/v1/jobs",
        json={"code": JUDGE, "size_bytes": other.stat().st_size, "content_type": "video/mp4", "file_name": "b.mp4"},
    ).json()
    client.put(created["upload_url"], content=other.read_bytes(), headers={"Content-Type": "video/mp4"})
    refused = client.post(f"/v1/jobs/{created['job_id']}/start")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "no_recording"


def test_a_failed_stage_reports_its_reason(
    make_client: Callable[..., tuple[TestClient, Service]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from safecut.api.worker import MediaRejected  # noqa: PLC0415 -- the error the stage would raise

    def runner(stage: Stage) -> Callable[..., Path]:
        if stage.name == "prepare":

            def reject(job_dir: Path, *, replay: bool = False) -> Path:
                raise MediaRejected("too_long", "61.2 s", duration_s=61.2)

            return reject
        return _fake_runner(stage)

    monkeypatch.setattr(Stage, "runner", runner)
    client, svc = make_client()
    job_id = upload_clip(client)
    job = run_to(client, svc, job_id, "start", "failed")
    assert job["failure"] == {"stage": "prepare", "reason": "too_long", "duration_s": 61.2}


def test_a_transient_failure_retries_once_later(
    make_client: Callable[..., tuple[TestClient, Service]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from safecut.meta.errors import MetaUnavailable  # noqa: PLC0415

    def runner(stage: Stage) -> Callable[..., Path]:
        if stage.name == "track":

            def busy(job_dir: Path, *, replay: bool = False) -> Path:
                raise MetaUnavailable("503 from Meta", status=503)

            return busy
        return _fake_runner(stage)

    monkeypatch.setattr(Stage, "runner", runner)
    client, svc = make_client()
    job_id = upload_clip(client)
    job = run_to(client, svc, job_id, "start", "retry_later")
    assert job["retry_at"] is not None
    svc.worker.cancel(job_id)
    svc.worker._run(job_id, "analyse")  # pyright: ignore[reportPrivateUsage] -- the re-queue, without the 5 min wait
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["failure"]["reason"] == "upstream"
    assert job["failure"]["stage"] == "track"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.entry("E5:auth_access_code")
def test_access_codes(make_client: Callable[..., tuple[TestClient, Service]], tmp_path: Path) -> None:
    client, _ = make_client(code_windows={"pilot": OPEN, "service": OPEN})  # judge keeps its Nov 5 window
    assert client.post("/v1/codes/check", json={"code": "nope-nope"}).status_code == 401
    check = client.post("/v1/codes/check", json={"code": f" {PILOT} "})
    assert check.status_code == 200
    assert check.json() == {"kind": "pilot", "valid_from": None, "valid_until": None, "open_weight": False}
    early = client.post("/v1/codes/check", json={"code": JUDGE})
    assert early.status_code == 401
    assert early.json()["error"] | {"message": ""} == {
        "code": "code_not_active",
        "message": "",
        "valid_from": "2026-11-05T00:00:00Z",
        "valid_until": "2026-11-10T23:59:59Z",
    }
    refused = client.post(
        "/v1/jobs", json={"code": JUDGE, "size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"}
    )
    assert refused.json()["error"]["code"] == "code_not_active"
    assert (
        client.post("/v1/jobs", json={"size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"}).status_code
        == 401
    )


def test_a_revoked_code_stops_paid_work_but_not_reading_or_deleting(
    make_client: Callable[..., tuple[TestClient, Service]],
    tmp_path: Path,
) -> None:
    client, svc = make_client()
    job_id = upload_clip(client)
    svc.access.settings = svc.settings.model_copy(update={"access_codes": ()})
    refused = client.post(f"/v1/jobs/{job_id}/start")
    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "unauthorized"
    assert client.get(f"/v1/jobs/{job_id}").status_code == 200
    assert client.delete(f"/v1/jobs/{job_id}").status_code == 204


@pytest.mark.entry("E5:auth_service_key")
def test_service_keys(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client()
    job_id = upload_clip(client, code=None, headers={"Authorization": f"Bearer {SERVICE_KEY}"})
    state = svc.store.get(job_id)
    assert state.service == "sigmora"
    assert state.code_kind == "service"
    run_to(client, svc, job_id, "start", "review")
    for bad in ("Bearer wrong-key-wrong-key-wrong", "Basic abc", "Bearer "):
        response = client.post(
            "/v1/jobs",
            json={"size_bytes": 10, "content_type": "video/mp4", "file_name": "a"},
            headers={"Authorization": bad},
        )
        assert response.status_code == 401
    closed, _ = make_client(code_windows={"judge": OPEN, "pilot": OPEN})  # service keys keep the judge window
    outside = closed.post(
        "/v1/jobs",
        json={"size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"},
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    )
    assert outside.json()["error"]["code"] == "code_not_active"


# ---------------------------------------------------------------------------
# Limits and caps
# ---------------------------------------------------------------------------


@pytest.mark.entry("E5:rate_limit")
def test_rate_limit_per_ip(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, _ = make_client(rate_limit_per_min=3, trust_proxy=True)
    for _ in range(3):
        assert (
            client.post(
                "/v1/codes/check", json={"code": PILOT}, headers={"X-Forwarded-For": "1.1.1.1, 9.9.9.9"}
            ).status_code
            == 200
        )
    limited = client.post("/v1/codes/check", json={"code": PILOT}, headers={"X-Forwarded-For": "9.9.9.9"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    other = client.post("/v1/codes/check", json={"code": PILOT}, headers={"X-Forwarded-For": "9.9.9.9, 8.8.8.8"})
    assert other.status_code == 200
    assert client.get("/healthz").status_code == 200  # health checks are never limited


def test_paid_actions_have_their_own_hourly_limit(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, _ = make_client(paid_actions_per_hour=2)
    body = {"code": JUDGE, "size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"}
    assert client.post("/v1/jobs", json=body).status_code == 201
    assert client.post("/v1/jobs", json=body).status_code == 201
    assert client.post("/v1/jobs", json=body).json()["error"]["code"] == "rate_limited"


def test_rate_limiter_window_slides() -> None:
    class Clock:
        now = 0.0

        @classmethod
        def monotonic(cls) -> float:
            return cls.now

    limiter = RateLimiter(monotonic=Clock.monotonic)
    limiter.hit("api", "ip", limit=1, window_s=60)
    Clock.now = 59.0
    with pytest.raises(Exception, match="Too many"):
        limiter.hit("api", "ip", limit=1, window_s=60)
    Clock.now = 60.5
    limiter.hit("api", "ip", limit=1, window_s=60)


def _spend(svc: Service, key: str, usd: float, kind: str = "daily") -> None:
    svc.ledger.reserve(f"call-{key}-{usd}", None, usd, [CapLimit(kind, key, 1000.0)])  # type: ignore[arg-type] -- kind is a CapKind
    svc.ledger.settle(f"call-{key}-{usd}", usd)


@pytest.mark.entry("E5:daily_cap")
def test_daily_cap_refuses_start_until_midnight(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client(replay=False, model_api_key=SecretStr("sk-test"), daily_usd_cap=3.0)
    job_id = upload_clip(client)
    _spend(svc, f"daily:{datetime.now(UTC).date().isoformat()}", 2.5)
    refused = client.post(f"/v1/jobs/{job_id}/start")
    assert refused.status_code == 429
    error = refused.json()["error"]
    assert error["code"] == "daily_cap"
    retry_at = datetime.fromisoformat(error["retry_at"].replace("Z", "+00:00"))
    assert retry_at.hour == retry_at.minute == 0
    assert retry_at > datetime.now(UTC)
    assert int(refused.headers["Retry-After"]) > 0
    assert svc.store.get(job_id).status == "created"


def test_job_and_code_caps(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, _ = make_client(replay=False, model_api_key=SecretStr("sk-test"), job_usd_cap=1.0)
    job_id = upload_clip(client)
    too_dear = client.post(f"/v1/jobs/{job_id}/start")
    assert too_dear.status_code == 422
    assert too_dear.json()["error"]["code"] == "job_cap"
    client2, svc2 = make_client(replay=False, model_api_key=SecretStr("sk-test"))
    from safecut.pipeline import code_id  # noqa: PLC0415

    _spend(svc2, f"code:{code_id(PILOT)}", 5.5, "code")
    refused = client2.post(
        "/v1/jobs", json={"code": PILOT, "size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"}
    )
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "code_cap"


def test_live_start_needs_the_auditor(
    make_client: Callable[..., tuple[TestClient, Service]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("safecut.api.app.auditor_available", lambda settings: False)
    client, _ = make_client(replay=False, model_api_key=SecretStr("sk-test"))
    job_id = upload_clip(client)
    refused = client.post(f"/v1/jobs/{job_id}/start")
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "auditor_unavailable"


def test_auditor_available_follows_the_audit_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys  # noqa: PLC0415
    import types  # noqa: PLC0415

    from safecut.api import app as app_module  # noqa: PLC0415

    monkeypatch.undo()
    audit = types.ModuleType("safecut.audit")
    monkeypatch.setitem(sys.modules, "safecut.audit", audit)
    assert app_module.auditor_available(Settings()) is True
    audit.auditor_available = lambda settings: False  # type: ignore[attr-defined] -- a stand-in audit stage
    assert app_module.auditor_available(Settings()) is False


def test_live_start_needs_the_meta_key(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, _ = make_client(replay=False)
    job_id = upload_clip(client)
    refused = client.post(f"/v1/jobs/{job_id}/start")
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "config"


@pytest.mark.entry("E5:upload_limits")
def test_upload_limits(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, _ = make_client()
    big = client.post(
        "/v1/jobs", json={"code": JUDGE, "size_bytes": 157_286_401, "content_type": "video/mp4", "file_name": "a.mp4"}
    )
    assert big.status_code == 413
    assert big.json()["error"] == {"code": "too_large", "message": "The limit is 150 MB.", "size_bytes": 157_286_401}
    assert (
        client.post(
            "/v1/jobs",
            json={"code": JUDGE, "size_bytes": 157_286_400, "content_type": "video/mp4", "file_name": "a.mp4"},
        ).status_code
        == 201
    )
    wrong_type = client.post(
        "/v1/jobs", json={"code": JUDGE, "size_bytes": 10, "content_type": "image/png", "file_name": "a.png"}
    )
    assert wrong_type.status_code == 415
    created = client.post(
        "/v1/jobs", json={"code": JUDGE, "size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"}
    ).json()
    url = created["upload_url"]
    assert client.put(url, content=b"x" * 11, headers={"Content-Type": "video/mp4"}).status_code == 403
    assert client.put(url, content=b"x" * 10, headers={"Content-Type": "video/quicktime"}).status_code == 403
    assert (
        client.put(url.replace("sig=", "sig=0"), content=b"x" * 10, headers={"Content-Type": "video/mp4"}).status_code
        == 403
    )
    assert client.put(url, content=b"x" * 10, headers={"Content-Type": "video/mp4"}).status_code == 200
    assert client.put(url, content=b"x" * 10, headers={"Content-Type": "video/mp4"}).status_code == 409
    expires = datetime.fromisoformat(created["upload_expires_at"].replace("Z", "+00:00"))
    assert timedelta(minutes=14) < expires - datetime.now(UTC) <= timedelta(minutes=15)


def test_the_duration_limit_is_prepares(monkeypatch: pytest.MonkeyPatch) -> None:
    from safecut.api import access  # noqa: PLC0415

    assert access.MAX_DURATION_S == 60.05
    assert access.estimate_usd(None) == 1.12
    assert access.estimate_usd(60) == pytest.approx(2.24)


@pytest.mark.parametrize(
    ("name", "ctype", "expected"),
    [
        ("My clip.mp4", "video/mp4", "My_clip.mp4"),
        ("../../etc/passwd", "video/mp4", "passwd.mp4"),
        ("a\\b\\c.MOV", "video/quicktime", "c.mov"),
        ("...", "video/mp4", "clip.mp4"),
        ("x" * 300, "video/mp4", "x" * 100 + ".mp4"),
    ],
)
def test_upload_names_are_made_safe(name: str, ctype: str, expected: str) -> None:
    assert safe_name(name, ctype) == expected


@pytest.mark.entry("E5:cors")
def test_cors_only_for_the_web_origin(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, _ = make_client()
    preflight = client.options(
        "/v1/jobs",
        headers={
            "Origin": WEB,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == WEB
    evil = client.options(
        "/v1/jobs", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in evil.headers
    simple = client.post("/v1/codes/check", json={"code": PILOT}, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers
    ok = client.post("/v1/codes/check", json={"code": PILOT}, headers={"Origin": WEB})
    assert ok.headers["access-control-allow-origin"] == WEB
    assert "Retry-After" in ok.headers.get("access-control-expose-headers", "")


# ---------------------------------------------------------------------------
# Deletion, media, demo, health
# ---------------------------------------------------------------------------


@pytest.mark.entry("E5:deletion_job")
def test_the_24h_deletion_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs", ttl=timedelta(hours=24), cleanup_every=timedelta(minutes=15))
    now = datetime(2026, 11, 5, 12, tzinfo=UTC)
    old = store.create(mode="live", now=now - timedelta(hours=25))
    fresh = store.create(mode="live", now=now - timedelta(hours=23))
    pinned = store.create(mode="replay", now=now - timedelta(days=9), pinned=True)
    (store.path(old.job_id) / "redacted.mp4").write_bytes(b"x")
    broken = store.path("j_" + "b" * 22)
    broken.mkdir()
    (broken / "state.json").write_text("{not json")
    assert fresh.deletes_at == fresh.created_at + timedelta(hours=24, minutes=15)
    removed = store.sweep(now=now)
    assert sorted(removed) == sorted([old.job_id, broken.name])
    assert not store.path(old.job_id).exists()
    assert store.path(fresh.job_id).exists()
    assert store.path(pinned.job_id).exists()
    later = now + timedelta(hours=1, minutes=16)
    with pytest.raises(LookupError):
        store.get(fresh.job_id, now=later)  # past deletes_at: deleted on sight, even before the sweep
    assert not store.path(fresh.job_id).exists()


def test_an_expired_job_answers_expired(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client()
    job_id = upload_clip(client)
    with svc.store.update(job_id) as state:
        state.deletes_at = datetime.now(UTC) - timedelta(seconds=1)
    gone = client.get(f"/v1/jobs/{job_id}")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "expired"
    assert client.get("/v1/jobs/j_0000000000000000000000").json()["error"]["code"] == "not_found"
    assert client.get("/v1/jobs/..%2Fstate.json").status_code == 404


def test_media_needs_a_valid_signature_and_an_allowed_name(
    make_client: Callable[..., tuple[TestClient, Service]],
) -> None:
    client, svc = make_client()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    for name in ("state.json", "cost.jsonl", "raw/manifest.json", "../other/x", "intake.json"):
        url = svc.signer.sign(f"/v1/jobs/{job_id}/media/{name}")
        assert client.get(url).status_code in (403, 404), name
    good = svc.views.media_url(job_id, "prepared.mp4")
    assert client.get(good).status_code == 200
    assert client.get(good.replace("sig=", "sig=f")).status_code == 403
    assert client.get(good.split("?")[0]).status_code == 403


def test_demo_serves_only_a_finished_pinned_hero(
    make_client: Callable[..., tuple[TestClient, Service]], tmp_path: Path
) -> None:
    client, svc = make_client()
    assert client.get("/v1/demo/demo").status_code == 404
    job_id = hero_job_id("demo")
    svc.store.create(mode="replay", job_id=job_id, pinned=True)
    job_dir = svc.store.path(job_id)
    pipeline.create_job(CLIP, job_dir, mode="replay")
    pipeline.analyse(job_dir, replay=True)
    pipeline.approve(job_dir, how="auto_policy")
    pipeline.publish(job_dir, replay=True)
    assert client.get("/v1/demo/demo").status_code == 404  # not marked done yet
    with svc.store.update(job_id) as state:
        state.status = "done"
    demo = client.get("/v1/demo/demo")
    assert demo.status_code == 200
    body = demo.json()
    assert body["mode"] == "replay"
    assert body["job"]["frames"] == load(job_dir / "job.json", Job).frames
    assert client.get(body["video_url"]).status_code == 200
    assert client.get("/v1/demo/..").status_code == 404


@pytest.mark.entry("E5:healthz")
def test_healthz(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, _ = make_client()
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["mode"] == "replay"
    assert health.json()["meta"] == "replay"
    calls: list[int] = []

    async def probe() -> str:
        calls.append(1)
        return "ok"

    live, svc = make_client(replay=False)
    svc.status_probe = probe
    assert live.get("/healthz").json()["meta"] == "ok"
    assert live.get("/healthz").json()["meta"] == "ok"
    assert len(calls) == 1  # at most once per interval


def test_cost_lines_count_against_the_job_cap(tmp_path: Path) -> None:
    job = tmp_path / "j"
    job.mkdir()
    append_cost_line(
        CostLine(
            ts=datetime.now(UTC),
            provider="meta",
            job_id="j",
            stage="track",
            model="sam-3.1",
            attempt=1,
            units={"frames": 1.0},
            usd=0.5,
            estimated=False,
            request_id=None,
            cap=None,
            code_kind="judge",
            code_id=None,
        ),
        job / "cost.jsonl",
    )
    assert pipeline.job_spend(job) == pytest.approx(0.5)


def test_redacted_name_is_the_render_output() -> None:
    assert REDACTED == "redacted.mp4"


def test_a_job_whose_files_disagree_never_ends_done(
    make_client: Callable[..., tuple[TestClient, Service]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from safecut.contracts import validate_job_dir  # noqa: PLC0415 -- the real gate, unstubbed

    monkeypatch.setattr("safecut.api.worker.validate_job_dir", validate_job_dir)
    client, svc = make_client()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    job = run_to(client, svc, job_id, "render", "failed")  # the stand-ins' receipt doesn't match this job
    assert job["failure"]["stage"] == "receipt"
    assert job["failure"]["reason"] == "internal"


@pytest.mark.entry("E5:flow")
def test_flow_on_the_real_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole flow on the real stages and the recorded (synthetic) demo job, replayed."""
    monkeypatch.undo()
    from safecut.contracts import Receipt  # noqa: PLC0415

    demo = ROOT / "fixtures" / "jobs" / "demo"
    clip = ROOT / json.loads((demo / "raw" / "manifest.json").read_text())["source"]
    svc = Service(settings_for(tmp_path), fixtures=ROOT / "fixtures" / "jobs")
    with TestClient(create_app(service=svc, background=False)) as client:
        created = client.post(
            "/v1/jobs",
            json={
                "code": JUDGE,
                "size_bytes": clip.stat().st_size,
                "content_type": "video/mp4",
                "file_name": clip.name,
            },
        ).json()
        assert (
            client.put(
                created["upload_url"], content=clip.read_bytes(), headers={"Content-Type": "video/mp4"}
            ).status_code
            == 200
        )
        job_id = created["job_id"]
        job = run_to(client, svc, job_id, "start", "review")
        assert job["synthetic"] is True
        child = next(i for i in job["items"] if i["kind"] == "child")
        refused = client.post(
            f"/v1/jobs/{job_id}/review", json={"type": "keep", "edit_id": "k", "item_id": child["item_id"]}
        )
        assert refused.status_code == 409  # a child is never kept, whatever the creator asks
        needs = next(i for i in job["items"] if i["decision"] == "needs_you")
        assert (
            client.post(
                f"/v1/jobs/{job_id}/review", json={"type": "hide", "edit_id": "h", "item_id": needs["item_id"]}
            ).status_code
            == 200
        )
        done = run_to(client, svc, job_id, "render", "done")
        assert done["audit"]["unresolved"] == 0
        receipt = client.get(client.get(f"/v1/jobs/{job_id}/result").json()["receipt_json_url"]).json()
        assert Receipt.model_validate(receipt).job_id == job_id


def test_the_demo_job_is_read_only(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client()
    job_id = hero_job_id("demo")
    svc.store.create(mode="replay", job_id=job_id, pinned=True)
    with svc.store.update(job_id) as state:
        state.status = "done"
    for method, path, body in (
        ("DELETE", "", None),
        ("POST", "/review", {"type": "hide", "edit_id": "x", "item_id": "i_1"}),
        ("POST", "/start", None),
        ("POST", "/render", None),
        ("POST", "/audit", None),
    ):
        response = client.request(method, f"/v1/jobs/{job_id}{path}", json=body)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "demo_read_only"
    assert svc.store.path(job_id).is_dir()


def test_two_concurrent_starts_run_the_analysis_once(
    make_client: Callable[..., tuple[TestClient, Service]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading  # noqa: PLC0415

    client, svc = make_client()
    job_id = upload_clip(client)
    submitted: list[str] = []
    real_submit = svc.worker.submit
    monkeypatch.setattr(
        svc.worker, "submit", lambda jid, action: (submitted.append(action), real_submit(jid, action))[1]
    )
    barrier = threading.Barrier(2)
    codes: list[int] = []

    def go() -> None:
        barrier.wait()
        codes.append(client.post(f"/v1/jobs/{job_id}/start").status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [202, 409]
    assert submitted == ["analyse"]
    svc.worker.wait(job_id)


def test_a_restart_requeues_interrupted_jobs(make_client: Callable[..., tuple[TestClient, Service]]) -> None:
    client, svc = make_client()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    with svc.store.update(job_id) as state:  # as a crash mid-render would leave it
        state.status, state.stage = "rendering", "render"
    pipeline.approve(svc.store.path(job_id), how="review")
    assert svc.recover() == [job_id]
    svc.worker.wait(job_id)
    assert client.get(f"/v1/jobs/{job_id}").json()["status"] == "done"
    assert svc.recover() == []


@pytest.mark.parametrize(
    ("reason", "message", "expected"),
    [
        ("unreadable", "transcode failed", ("bad_media", None, None)),
        ("no_video", "no video", ("bad_media", None, None)),
        ("too_long", "61.20 s is over the 60 s limit", ("too_long", 61.2, None)),
        ("too_large", "157286401 bytes is over the limit", ("too_large", None, 157286401)),
        ("no_source", "source/ is empty", ("internal", None, None)),
    ],
)
def test_prepare_rejections_map_to_the_ui_reasons(
    reason: str, message: str, expected: tuple[str, float | None, int | None]
) -> None:
    from safecut.api.worker import failure_for  # noqa: PLC0415
    from safecut.prepare import PrepareError  # noqa: PLC0415

    failure, transient = failure_for(PrepareError(reason, message), "prepare")  # type: ignore[arg-type] -- a Reason
    assert (failure.reason, failure.duration_s, failure.size_bytes) == expected
    assert transient is False


@pytest.mark.entry("E5:upload_limits")
def test_a_clip_over_60_s_fails_in_prepare_with_its_duration(
    make_client: Callable[..., tuple[TestClient, Service]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 60 s rule (> 60.05 s, UI-SPEC §10.2) is applied by the real prepare stage, after the upload."""
    import subprocess  # noqa: PLC0415

    from imageio_ffmpeg import get_ffmpeg_exe  # noqa: PLC0415

    from safecut.prepare import run as real_prepare  # noqa: PLC0415 -- the real stage, not the stand-in

    def runner(stage: Stage) -> Callable[..., Path]:
        return real_prepare if stage.name == "prepare" else _fake_runner(stage)

    monkeypatch.setattr(Stage, "runner", runner)
    long_clip = tmp_path / "long.mp4"
    subprocess.run(  # noqa: S603 -- our bundled ffmpeg, a fixed argv
        [
            get_ffmpeg_exe(),
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:s=64x64:r=2:d=61",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(long_clip),
        ],
        check=True,
        timeout=60,
    )
    client, svc = make_client(replay=False, model_api_key=SecretStr("sk-test"))
    created = client.post(
        "/v1/jobs",
        json={
            "code": JUDGE,
            "size_bytes": long_clip.stat().st_size,
            "content_type": "video/mp4",
            "file_name": "long.mp4",
        },
    ).json()
    client.put(created["upload_url"], content=long_clip.read_bytes(), headers={"Content-Type": "video/mp4"})
    job = run_to(client, svc, created["job_id"], "start", "failed")
    assert job["failure"]["stage"] == "prepare"
    assert job["failure"]["reason"] == "too_long"
    assert job["failure"]["duration_s"] == pytest.approx(61, abs=0.1)
