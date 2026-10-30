"""Fuzz properties: hostile or garbage input fails in a typed, expected way and never crashes."""

from __future__ import annotations

import contextlib
import math
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from safecut import contracts as c
from safecut.meta import cost
from safecut.meta.errors import MetaError, classify
from safecut.meta.retry import parse_retry_after
from safecut.meta.sse import SSEDecodeError, iter_sse

_json = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=12),
    lambda kids: st.lists(kids, max_size=4) | st.dictionaries(st.text(max_size=10), kids, max_size=4),
    max_leaves=20,
)


@given(st.lists(st.text(max_size=60), max_size=30))
def test_sse_never_crashes(lines: list[str]) -> None:
    try:
        for event in iter_sse(lines):
            assert isinstance(event, dict)
    except SSEDecodeError:
        pass


@given(st.integers(100, 599), _json)
def test_classify_total(status: int, body: Any) -> None:
    err = classify(status, body)
    assert isinstance(err, MetaError)
    assert err.status == status
    if status in (429, 500, 502, 503):
        assert err.retryable
    if 400 <= status < 429 or (status >= 500 and status not in (500, 502, 503)):
        assert not err.retryable


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.binary(max_size=400), st.sampled_from(sorted(c.JOB_FILES)))
def test_contract_loaders_fail_typed(tmp_path: Path, raw: bytes, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(raw)
    with contextlib.suppress(c.ContractError):
        c.load(path, c.JOB_FILES[name])


@given(_json, st.sampled_from(sorted(c.JOB_FILES)))
def test_contract_models_reject_random_json(data: Any, name: str) -> None:
    with contextlib.suppress(ValidationError):
        c.JOB_FILES[name].model_validate(data)


@given(_json)
def test_cost_meters_total(data: Any) -> None:
    units = cost.usage_units(data if isinstance(data, dict) else None)
    assert cost.responses_usd_from_units("muse-spark-1.3", units) >= 0


@given(st.text(max_size=80))
def test_retry_after_total(value: str) -> None:
    seconds = parse_retry_after(value)
    assert seconds is None or (seconds >= 0 and not math.isnan(seconds))


@pytest.mark.parametrize("status", [401, 402, 403, 404, 413, 422])
def test_client_errors_are_final(status: int) -> None:
    assert not classify(status, None).retryable
