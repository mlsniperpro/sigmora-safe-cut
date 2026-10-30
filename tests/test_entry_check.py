"""scripts/entry-check.sh never reports PASS unless every E-line reported OK exactly once, in a full run."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import types
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts import entry_check
from tests.fake_stages import EXAMPLE

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "scripts" / "entry_check_lib.sh"
LINES = [f"E{n}" for n in range(1, 13)]
BASH = shutil.which("bash") or "/bin/bash"


def verdict(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv
        [BASH, "-c", f". {LIB}\n{script}\nentry_verdict"], capture_output=True, text=True, check=False
    )


def record_all(status: dict[str, str] | None = None) -> str:
    status = status or {}
    return "\n".join(f"entry_record {line} {status.get(line, 'OK')} 'why'" for line in LINES)


def test_all_ok_passes() -> None:
    proc = verdict(record_all())
    assert proc.returncode == 0
    assert proc.stdout.splitlines()[-1] == "ENTRY: PASS"
    assert proc.stdout.splitlines()[:12] == [f"{line}: OK" for line in LINES]


@pytest.mark.parametrize("failing", LINES)
def test_any_failure_refuses_pass(failing: str) -> None:
    proc = verdict(record_all({failing: "FAIL"}))
    assert proc.returncode == 1
    assert f"{failing}: FAIL why" in proc.stdout
    assert proc.stdout.splitlines()[-1] == "ENTRY: FAIL (1)"
    assert "ENTRY: PASS" not in proc.stdout


def test_a_line_that_never_reported_fails() -> None:
    script = "\n".join(f"entry_record {line} OK" for line in LINES if line != "E7")
    proc = verdict(script)
    assert proc.returncode == 1
    assert "E7: FAIL never reported" in proc.stdout
    assert proc.stdout.splitlines()[-1] == "ENTRY: FAIL (1)"


def test_a_line_reported_twice_fails_even_if_ok() -> None:
    proc = verdict(record_all() + "\nentry_record E3 OK")
    assert proc.returncode == 1
    assert "E3: FAIL reported twice" in proc.stdout
    assert proc.stdout.splitlines()[-1].startswith("ENTRY: FAIL (")


def test_unknown_status_counts_as_failure() -> None:
    proc = verdict(record_all({"E5": "MAYBE"}))
    assert proc.returncode == 1
    assert "E5: FAIL" in proc.stdout


def test_a_partial_run_never_passes() -> None:
    proc = subprocess.run(  # noqa: S603 -- fixed argv
        [BASH, "-c", f". {LIB}\n{record_all()}\nentry_verdict '--only E1'"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert proc.stdout.splitlines()[-1].startswith("ENTRY: FAIL (0): partial run")


def test_the_script_rejects_unknown_arguments() -> None:
    proc = subprocess.run(  # noqa: S603 -- fixed argv
        [BASH, str(ROOT / "scripts" / "entry-check.sh"), "--everything"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "usage" in proc.stderr


def test_figures_in_prose_are_found_and_code_is_ignored() -> None:
    text = "Recall 97.5% at $0.91 per clip; κ 0.82. `sam-3.1` and muse-spark-1.3 aren't figures.\n```bash\n12.5%\n```"
    assert entry_check.FIGURE.findall(entry_check.prose(text)) == ["97.5%", "$0.91", "0.82"]
    # A results table can't hide in an untagged fence: only command and data fences are skipped.
    assert entry_check.FIGURE.findall(entry_check.prose("```\n| full | 12.5% |\n```")) == ["12.5%"]
    assert entry_check.FIGURE.findall(entry_check.prose("Oct 26, 60 s, 150 MB, v1.2.3, 1/3")) == []
    assert entry_check.FIGURE.findall(entry_check.prose("see [run](eval/results/r1.2/x) <!-- 5.5% -->")) == []


@pytest.mark.parametrize(
    ("name", "is_test"),
    [
        ("web/src/lib/api.test.ts", True),
        ("web/src/test/mock-backend.ts", True),
        ("web/src/lib/client.ts", False),
        ("web/src/lib/__fixtures__/a.json", True),
        ("web/src/lib/mock-backend.ts", False),
    ],
)
def test_test_file_pattern(name: str, is_test: bool) -> None:
    assert bool(entry_check.TEST_FILE.search(name)) is is_test


def test_keys_present_names_missing_keys() -> None:
    lines = [{"event": "collected", "nodeid": "t::a", "keys": ["E5:cors"]}]
    assert entry_check.keys_present(lines, "E5", ["cors"]) == {"E5:cors": ["t::a"]}
    with pytest.raises(entry_check.CheckFailed, match="for: healthz"):
        entry_check.keys_present(lines, "E5", ["cors", "healthz"])


def test_secret_pattern_catches_assigned_keys_but_not_the_fake_one() -> None:
    assert entry_check.SECRET.search("MODEL_API_KEY=abcdefghijklmnopqrstuvwxyz012345")
    assert not entry_check.SECRET.search('FAKE_KEY = "sk-test-not-a-real-key"')
    assert not entry_check.SECRET.search("MODEL_API_KEY=")


def test_unknown_check_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert entry_check.main(["E99"]) == 2
    assert "usage" in capsys.readouterr().err


def test_figures_in_inline_code_are_checked_and_matched_whole() -> None:
    assert entry_check.FIGURE.findall(entry_check.prose("cap `$3.00`, recall `97.5%`")) == ["$3.00", "97.5%"]
    results = "recall 85.0% and $13.00"
    for figure, present in (("85.0%", True), ("5.0%", False), ("$3.00", False), ("$13.00", True)):
        found = bool(re.search(rf"(?<![\w.]){re.escape(figure)}(?![\w%]|\.\d)", results))
        assert found is present, figure


def test_require_passed_refuses_skipped_or_missing_outcomes() -> None:
    collected = [{"event": "collected", "nodeid": "t::a", "keys": ["E5:x"]}]
    entry_check.require_passed(
        [*collected, {"event": "result", "nodeid": "t::a", "when": "call", "outcome": "passed"}], "E5"
    )
    with pytest.raises(entry_check.CheckFailed, match="didn't pass"):
        entry_check.require_passed(
            [*collected, {"event": "result", "nodeid": "t::a", "when": "setup", "outcome": "skipped"}], "E5"
        )
    with pytest.raises(entry_check.CheckFailed, match="didn't pass"):
        entry_check.require_passed(collected, "E5")


MARK = "pytest." + "mark."


@pytest.mark.parametrize(
    ("line", "allowed"),
    [
        # Spelt in pieces, so E11's own scan of tests/ never meets a skip in this file.
        (f'tests/test_live_sense.py:30:    {MARK}skipif(not os.environ.get("MODEL_API_KEY"), reason="x"),', True),
        (f'tests/test_api.py:9:@{MARK}skipif(not os.environ.get("MODEL_API_KEY"), reason="x")', False),
        (f'tests/test_live_x.py:3:@{MARK}skip(reason="deliver later")', False),
        (f'tests/test_x.py:3:    pytest.{"importor" + "skip"}("modal")', False),
    ],
)
def test_only_key_gated_live_skips_are_allowed(line: str, allowed: bool) -> None:
    assert bool(entry_check.LIVE_SKIP.match(line)) is allowed


def test_secret_pattern_catches_the_json_form() -> None:
    assert entry_check.SECRET.search('{"MODEL_API_KEY": "abcdefghijklmnopqrstuvwxyz012345"}')  # gate-allow: test data


def test_counts_reported_as_results_are_checked_too() -> None:
    seen = entry_check.prose("We fixed 47 leaks on 20 clips with 3 bursts; the clip runs 60 s at 30 fps.")
    assert entry_check.COUNT.findall(seen) == ["47", "20", "3"]


def test_owner_inputs_need_their_real_lines_not_a_bare_word() -> None:
    patterns = {k: re.compile(v) for k, v in entry_check.OWNER_INPUTS.items()}
    assert not patterns["making the repo public"].search("the public split, CC BY 4.0")
    assert patterns["making the repo public"].search("**Make `mlsniperpro/sigmora-safe-cut` public** before")
    assert not patterns["EgoBlur weights"].search("the audit runs YuNet until EgoBlur is installed")
    assert patterns["EgoBlur weights"].search("**EgoBlur Gen 2 weights** (a gated download)")


def test_e3_never_passes_on_a_truth_file_with_nothing_to_check(tmp_path: Path) -> None:
    """A truth file with no visible should-hide entity (or no one to keep) can't vouch for anything."""
    truth = tmp_path / "t.json"
    truth.write_text(
        json.dumps(
            {
                "clip": "a.mp4",
                "fps": 30,
                "frames": 12,
                "width": 1280,
                "height": 720,
                "split": "dev",
                "entities": [
                    {
                        "id": "e1",
                        "category": "participant",
                        "should_hide": False,
                        "frames": {"first": 0, "last": 0},
                        "boxes": {"0": [1200, 650, 1210, 660]},
                    }
                ],
            }
        )
    )
    job = tmp_path / "job"
    shutil.copytree(EXAMPLE, job)
    with pytest.raises(entry_check.CheckFailed, match="no visible entity that should be hidden"):
        entry_check.score_against_truth(job, truth)


def test_e3_checks_the_rendered_pixels_not_only_the_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plan that hides everything must not pass E3 with a renderer that draws nothing, tints the frame, or covers
    only a sliver of the box; a real cover passes, and a kept entity must come through unaltered."""
    import numpy as np  # noqa: PLC0415 -- only this test needs it

    from safecut.render import video  # noqa: PLC0415

    meta = types.SimpleNamespace(width=40, height=20, prepared="prepared.mp4")
    monkeypatch.setattr("safecut.contracts.load", lambda path, model=None: meta)
    hide = types.SimpleNamespace(id="e1", should_hide=True, dense={0: (0, 0, 10, 10), 1: (0, 0, 10, 10)})
    keep = types.SimpleNamespace(id="e2", should_hide=False, dense={0: (20, 0, 30, 10), 1: (20, 0, 30, 10)})
    labels = types.SimpleNamespace(width=40, height=20, entities=[hide, keep])
    source = []
    for _ in range(2):
        frame = np.full((20, 40, 3), 120, np.uint8)
        frame[2:8, 2:5] = 220  # the hidden entity's features
        frame[2:8, 22:25] = 30  # the kept entity's
        source.append(frame)

    def rendered(edit: Callable[[np.ndarray], None]) -> list[str]:
        frames = []
        for f in source:
            out = f.copy()
            edit(out)
            frames.append(out)
        monkeypatch.setattr(
            video, "read_frames", lambda path, job: iter(source if path.name == "prepared.mp4" else frames)
        )
        return entry_check.render_hides(Path("job"), labels)

    def cover(f: np.ndarray) -> None:
        f[0:10, 0:10] = 0

    def tint(f: np.ndarray) -> None:
        f[:] = np.clip(f.astype(int) + 10, 0, 255).astype(np.uint8)

    def sliver(f: np.ndarray) -> None:
        f[0:10, 0:1] = 0

    def nothing(f: np.ndarray) -> None:
        return None

    def dim(f: np.ndarray) -> None:
        f[0:10, 0:10] = (f[0:10, 0:10] * 0.2).astype(np.uint8)  # a contrast stretch would bring it back

    assert rendered(cover) == []
    assert rendered(nothing) == ["e1: still legible in redacted.mp4 on 2/2 visible frames"]
    assert rendered(sliver) == ["e1: still legible in redacted.mp4 on 2/2 visible frames"]
    assert rendered(dim) == ["e1: still legible in redacted.mp4 on 2/2 visible frames"]
    assert rendered(tint) == [
        "e1: still legible in redacted.mp4 on 2/2 visible frames",
        "e2 (keep): altered in redacted.mp4 on 2/2 visible frames",
    ]


def test_secret_pattern_knows_this_projects_own_secrets() -> None:
    # Key-shaped test data: the scanner's own tests are the one place allowed to hold it.
    assert entry_check.SECRET.search("HF_TOKEN=hf_abcdefghijklmnopqrstuvwxyzABCDEFGH12")
    assert entry_check.SECRET.search("SAFECUT_URL_SECRET=Zx81kdJq0LmnB7Yt5ExP2rVw9sAc")
    assert entry_check.SECRET.search('[{"code": "Q7mz2LpX9vRt4KsW8nBy3HcD", "kind": "judge"}]')
    # Any 12+ character code or key is a real one (BLOCKED's minimum), whatever it looks like…
    assert entry_check.secret_hit('"code": "k3J9xQ2mP7vL4tR8"')
    assert entry_check.secret_hit('"code": "mango-tiger-lamp-river-4821"')
    assert entry_check.secret_hit('"code": "correcthorsebattery"')
    assert entry_check.secret_hit('SAFECUT_ACCESS_CODES=\'[{"code": "k3J9xQ2mP7vL4tR8"}]\'')
    # …except the tests' exact named stand-ins and the API's error codes.
    assert not entry_check.secret_hit('"key": "sigmora-service-key-0123456789"')
    assert not entry_check.secret_hit('"code": "code_not_active"')
    assert not entry_check.secret_hit('"code": "unauthorized"')
    assert not entry_check.secret_hit('SAFECUT_URL_SECRET: "e2e-url-secret"')


def test_history_scan_attributes_lines_to_their_files() -> None:
    """The scanner's own files may hold key shapes (its patterns, its test data); any other file may not, whatever
    the line says, including what a merge commit introduced (``--cc``)."""
    key = "k3J9xQ2" + "mP7vL4tR8"  # spelt in pieces: this file is exempt anyway, but the point is the attribution
    log = "\n".join(
        [
            "commit 1",
            "diff --git a/tests/test_entry_check.py b/tests/test_entry_check.py",
            "--- a/tests/test_entry_check.py",
            "+++ b/tests/test_entry_check.py",
            "@@ -1,0 +1,1 @@",
            f'+    assert entry_check.secret_hit(\'"code": "{key}"\')',
            "commit 2",
            "diff --cc web/e2e/api-e2e.mjs",
            "--- a/web/e2e/api-e2e.mjs",
            "+++ b/web/e2e/api-e2e.mjs",
            "@@@ -1,1 -1,1 +1,2 @@@",
            f' +  const codes = [{{"code": "{key}"}}];',
            "commit 3",
            "diff --git a/notes.txt b/notes.txt",
            "--- /dev/null",
            "+++ b/notes.txt",
            "@@ -0,0 +1,3 @@",
            "+++ b/tests/test_entry_check.py",  # content that looks like a header can't redirect the attribution
            f'+{{"key": "{key}"}}',
            f"+++ MODEL_API_{'KEY'}={key}{key}",  # an added line starting with "++" shows as "+++ …": still scanned
        ]
    )
    hits = entry_check.history_hits(log)
    assert [h.split(": ", 1)[0] for h in hits] == ["web/e2e/api-e2e.mjs", "notes.txt", "notes.txt"]


def test_e11_history_scan_passes_on_this_repo() -> None:
    """The real history, as E11 reads it: the scanner's own test data must never make ENTRY: PASS impossible."""
    log = subprocess.run(
        ["git", "log", "-p", "--cc", "--text", "--all", "--no-color", "--format=commit %H"],  # noqa: S607 -- git from PATH
        cwd=entry_check.ROOT,
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    ).stdout
    assert entry_check.history_hits(log) == []
