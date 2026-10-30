"""scripts/entry-check.sh never reports PASS unless every E-line reported OK exactly once, in a full run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import entry_check

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
    text = "Recall 97.5% at $0.91 per clip; κ 0.82. `sam-3.1` and muse-spark-1.3 aren't figures.\n```\n12.5%\n```"
    assert entry_check.FIGURE.findall(entry_check.prose(text)) == ["97.5%", "$0.91", "0.82"]
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
