"""Break-it run against a real replay API (uvicorn, a fresh jobs dir).

1. soak: W concurrent clients each run the judge's full flow N times (create, upload, start, poll, random review
   edits incl. undo/merge/remove, render, result, every media URL, delete).
2. fuzz: random and malformed requests on every route; any 5xx or a hang is a failure.
3. failure injection: kill -9 the API mid-analysis, restart on the same jobs dir, the job must finish.
Prints a summary line per part and exits non-zero on any failure.
"""

import json
import os
import random
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

REPO = Path(sys.argv[1]).resolve()
W, N = int(os.environ.get("W", "4")), int(os.environ.get("N", "5"))
CODE = "breakit-code"
MANIFEST = json.loads((REPO / "fixtures/jobs/demo/raw/manifest.json").read_text())
CLIP = (REPO / MANIFEST["source"]).read_bytes()
failures: list[str] = []
lock = threading.Lock()


def fail(msg: str) -> None:
    with lock:
        failures.append(msg)
    print("FAIL", msg, flush=True)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_api(jobs: Path, port: int) -> subprocess.Popen[bytes]:
    env = os.environ | {
        "SAFECUT_REPLAY": "1",
        "SAFECUT_JOBS_DIR": str(jobs),
        "SAFECUT_PUBLIC_URL": f"http://127.0.0.1:{port}",
        "SAFECUT_URL_SECRET": "breakit-secret",
        "SAFECUT_ACCESS_CODES": json.dumps([{"code": CODE, "kind": "judge"}]),
        "SAFECUT_CODE_WINDOWS": json.dumps({"judge": [None, None]}),
        "SAFECUT_RATE_LIMIT_PER_MIN": "100000",
        "SAFECUT_PAID_ACTIONS_PER_HOUR": "100000",
    }
    proc = subprocess.Popen(
        ["uv", "run", "--no-sync", "uvicorn", "--factory", "safecut.api.app:create_app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning", "--no-proxy-headers"],
        cwd=REPO, env=env, start_new_session=True,  # its own process group: a kill reaches uvicorn, not just uv
    )
    until = time.time() + 300
    while time.time() < until:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/v1/demo/demo", timeout=5).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit("API didn't come up")


def wait_status(c: httpx.Client, jid: str, want: set[str], ms: float = 300) -> dict:
    until = time.time() + ms
    while time.time() < until:
        r = c.get(f"/v1/jobs/{jid}")
        if r.status_code >= 500:
            fail(f"GET job {r.status_code}")
        body = r.json()
        if body["status"] in want:
            return body
        if body["status"] == "failed":
            raise RuntimeError(f"job failed: {body.get('failure')}")
        time.sleep(0.3)
    raise RuntimeError(f"timeout waiting for {want}")


def create_and_upload(c: httpx.Client) -> str:
    r = c.post("/v1/jobs", json={"code": CODE, "file_name": "clip.mp4", "size_bytes": len(CLIP),
                                 "content_type": "video/mp4"})
    assert r.status_code == 201, r.text
    body = r.json()
    url = body["upload_url"]
    r = httpx.put(url, content=CLIP, headers={"content-type": "video/mp4"}, timeout=60)
    assert r.status_code == 200, r.text
    return body["job_id"]


def flow(c: httpx.Client, rng: random.Random, tag: str) -> None:
    jid = create_and_upload(c)
    r = c.post(f"/v1/jobs/{jid}/start")
    assert r.status_code == 202, r.text
    body = wait_status(c, jid, {"review"})
    items = [i["item_id"] for i in body.get("items", [])]
    done_edits: list[str] = []
    for k in range(rng.randint(2, 8)):
        kind = rng.choice(["keep", "hide", "merge", "remove_person", "undo"])
        eid = f"{tag}-{k}"
        if kind == "undo":
            if not done_edits:
                continue
            edit = {"type": "undo", "edit_id": eid, "reverts": rng.choice(done_edits)}
        elif kind == "merge":
            a, b = rng.sample(items, 2)
            edit = {"type": "merge", "edit_id": eid, "item_id": a, "into": b}
        else:
            edit = {"type": kind, "edit_id": eid, "item_id": rng.choice(items)}
        r = c.post(f"/v1/jobs/{jid}/review", json=edit)
        if r.status_code >= 500:
            fail(f"review {edit} -> {r.status_code} {r.text[:200]}")
        elif r.status_code == 200:
            done_edits.append(eid)
            # the same edit again is idempotent
            r2 = c.post(f"/v1/jobs/{jid}/review", json=edit)
            if r2.status_code != 200:
                fail(f"replayed edit not idempotent: {r2.status_code}")
    r = c.post(f"/v1/jobs/{jid}/render")
    assert r.status_code == 202, r.text
    body = wait_status(c, jid, {"done", "needs_you"})
    if body["status"] == "done":
        res = c.get(f"/v1/jobs/{jid}/result")
        assert res.status_code == 200, res.text
        for name, url in res.json().items():
            if not (name.endswith("_url") and url):
                continue
            m = httpx.get(url, timeout=60)
            if m.status_code != 200:
                fail(f"media {name} -> {m.status_code}")
    r = c.delete(f"/v1/jobs/{jid}")
    assert r.status_code == 204, r.text
    if c.get(f"/v1/jobs/{jid}").status_code != 404:
        fail("deleted job still readable")


def soak(api: str) -> None:
    def worker(w: int) -> None:
        rng = random.Random(w)
        with httpx.Client(base_url=api, timeout=120) as c:
            for n in range(N):
                try:
                    flow(c, rng, f"w{w}n{n}")
                except Exception as e:  # noqa: BLE001 -- every flow error is a soak failure, recorded
                    fail(f"soak w{w} n{n}: {type(e).__name__}: {e}")
    t0 = time.time()
    threads = [threading.Thread(target=worker, args=(w,)) for w in range(W)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"soak: {W}x{N} full flows in {time.time() - t0:.0f}s, failures so far {len(failures)}", flush=True)


def fuzz(api: str, rounds: int = 1500) -> None:
    rng = random.Random(7)
    junk: list[object] = [None, "", "x" * 5000, -1, 0, 1e308, [], {}, {"type": "keep"}, "\u0000", "../../etc/passwd",
                          {"type": "merge", "edit_id": "e", "item_id": "i_1", "into": "i_1"},
                          {"type": "undo", "edit_id": "e", "reverts": "nope"}, {"type": "cover_spot", "edit_id": "e",
                                                                              "spot_id": "s999"}]
    with httpx.Client(base_url=api, timeout=30) as c:
        jid = create_and_upload(c)
        c.post(f"/v1/jobs/{jid}/start")
        wait_status(c, jid, {"review"})
        ids = [jid, "demo", "nope", "../x", "%2e%2e", "j_" + "0" * 40, "", "a" * 300]
        statuses: dict[int, int] = {}
        for _ in range(rounds):
            j = rng.choice(ids)
            route = rng.choice(["codes", "create", "start", "review", "render", "audit", "result", "delete",
                                "media", "upload", "demo", "get"])
            try:
                if route == "codes":
                    r = c.post("/v1/codes/check", json=rng.choice([{"code": rng.choice(junk)}, rng.choice(junk)]))
                elif route == "create":
                    r = c.post("/v1/jobs", json={"code": rng.choice([CODE, rng.choice(junk)]),
                                                 "file_name": rng.choice(["a.mp4", rng.choice(junk)]),
                                                 "size_bytes": rng.choice([1, 10**12, rng.choice(junk)]),
                                                 "content_type": rng.choice(["video/mp4", "text/html", None])})
                elif route == "review":
                    r = c.post(f"/v1/jobs/{j}/review", json=rng.choice(junk + [
                        {"type": rng.choice(["keep", "hide", "remove_person"]), "edit_id": f"f{rng.random()}",
                         "item_id": rng.choice(["i_1", "i_999", "p_1", "i_x"])}]))
                elif route in ("start", "render", "audit"):
                    r = c.post(f"/v1/jobs/{j}/{route}")
                elif route == "result":
                    r = c.get(f"/v1/jobs/{j}/result")
                elif route == "delete":
                    r = c.delete(f"/v1/jobs/{rng.choice(['demo', 'nope', '../x'])}")
                elif route == "media":
                    r = c.get(f"/v1/jobs/{j}/media/{rng.choice(['redacted.mp4', '../intake.json', 'x'])}",
                              params={"exp": rng.choice(["1", "9999999999", "x"]), "sig": "deadbeef"})
                elif route == "upload":
                    r = c.put(f"/v1/uploads/{j}", content=os.urandom(rng.randint(0, 2048)),
                              params={"exp": "9999999999", "sig": "00"}, headers={"content-type": "video/mp4"})
                elif route == "demo":
                    r = c.get(f"/v1/demo/{rng.choice(['demo', 'nope', '..', 'x' * 200])}")
                else:
                    r = c.get(f"/v1/jobs/{j}")
            except httpx.HTTPError as e:
                fail(f"fuzz {route} {j}: transport {e}")
                continue
            statuses[r.status_code] = statuses.get(r.status_code, 0) + 1
            if r.status_code >= 500:
                fail(f"fuzz {route} {j!r} -> {r.status_code} {r.text[:200]}")
        # the fuzzed job and the demo are still intact
        if c.get(f"/v1/jobs/{jid}").status_code not in (200,):
            fail("fuzzed job lost")
        if c.get("/v1/demo/demo").status_code != 200:
            fail("demo lost after fuzz")
    print(f"fuzz: {rounds} requests, statuses {dict(sorted(statuses.items()))}", flush=True)


def kill_restart() -> None:
    jobs = Path(tempfile.mkdtemp(prefix="breakit-kill-"))
    port = free_port()
    api = f"http://127.0.0.1:{port}"
    proc = start_api(jobs, port)
    with httpx.Client(base_url=api, timeout=60) as c:
        jid = create_and_upload(c)
        assert c.post(f"/v1/jobs/{jid}/start").status_code == 202
        time.sleep(1.0)
        stage = c.get(f"/v1/jobs/{jid}").json()["stage"]
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()
    proc = start_api(jobs, port)
    try:
        with httpx.Client(base_url=api, timeout=60) as c:
            wait_status(c, jid, {"review"})
            assert c.post(f"/v1/jobs/{jid}/render").status_code == 202
            time.sleep(0.5)
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        proc = start_api(jobs, port)
        with httpx.Client(base_url=api, timeout=60) as c:
            body = wait_status(c, jid, {"done", "needs_you"})
            print(f"kill -9 twice (in analysis at stage {stage!r}, then in render): job ended {body['status']}",
                  flush=True)
    except Exception as e:  # noqa: BLE001 -- recorded as a failure
        fail(f"kill/restart: {type(e).__name__}: {e}")
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait()


def main() -> None:
    if os.environ.get("BREAKIT_ONLY") == "kill":
        kill_restart()
        print(f"BREAKIT: {'PASS' if not failures else 'FAIL'} ({len(failures)} failures)")
        sys.exit(1 if failures else 0)
    jobs = Path(tempfile.mkdtemp(prefix="breakit-"))
    port = free_port()
    proc = start_api(jobs, port)
    try:
        soak(f"http://127.0.0.1:{port}")
        fuzz(f"http://127.0.0.1:{port}")
        alive = proc.poll() is None
        print(f"api alive after soak+fuzz: {alive}", flush=True)
        if not alive:
            fail("API died")
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait()
    kill_restart()
    print(f"BREAKIT: {'PASS' if not failures else 'FAIL'} ({len(failures)} failures)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
