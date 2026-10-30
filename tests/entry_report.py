"""A pytest plugin for ``scripts/entry-check.sh``: which tests carry which ``entry`` keys, and how they ran.

Tests opt in with ``@pytest.mark.entry("E5:cors")`` (one key per required check, ``.agent/ENTRY-DONE.md``). With
``SAFECUT_ENTRY_REPORT=<path>`` set, every collected test with an ``entry`` key writes one JSON line there: its
node ID, keys, markers, outcome and, for hypothesis tests, the number of passing examples. ``--entry-only=E4``
deselects every test without a key on that E-line.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

_PASSING = re.compile(r"- (\d+) passing, \d+ failing")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--entry-only", default=None, help="Run only tests marked entry('<E-line>:…'), e.g. E4.")


def _keys(item: pytest.Item) -> list[str]:
    return [str(arg) for mark in item.iter_markers("entry") for arg in mark.args]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    only = config.getoption("--entry-only")
    if not only:
        return
    keep: list[pytest.Item] = []
    dropped: list[pytest.Item] = []
    for item in items:
        (keep if any(key.split(":", 1)[0] == only for key in _keys(item)) else dropped).append(item)
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = keep
    path = os.environ.get("SAFECUT_ENTRY_REPORT")
    if path:
        for item in keep:
            _write(
                path,
                {
                    "nodeid": item.nodeid,
                    "keys": _keys(item),
                    "event": "collected",
                    "markers": sorted({m.name for m in item.iter_markers()}),
                },
            )


def _write(path: str, entry: dict[str, Any]) -> None:
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    # A wrapper: makereport is a first-result hook, so a plain (even trylast) implementation never runs once
    # pytest's own has returned the report.
    report = yield
    path = os.environ.get("SAFECUT_ENTRY_REPORT")
    keys = _keys(item)
    if path and keys and call.when == "teardown":
        stats = getattr(item, "hypothesis_statistics", None)
        passing = sum(int(n) for n in _PASSING.findall(stats)) if isinstance(stats, str) else None
        _write(path, {"nodeid": item.nodeid, "keys": keys, "event": "teardown", "examples": passing})
    return report


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    path = os.environ.get("SAFECUT_ENTRY_REPORT")
    if not path or not report.keywords.get("entry"):
        return
    if report.when == "call" or report.outcome != "passed":
        _write(path, {"nodeid": report.nodeid, "event": "result", "when": report.when, "outcome": report.outcome})
