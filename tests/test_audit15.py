"""Tests for audit #15: a copy left by a fast 5xx, or one that lands after the first listing, is still found and
deleted before ``files_deleted`` can be true."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

from safecut.meta.errors import MetaUnavailable
from safecut.meta.files import FileStore
from tests.conftest import Harness


def _copy(file_id: str) -> dict[str, object]:
    return {"id": file_id, "filename": "j_test-sam_proxy.mp4", "bytes": 300, "created_at": time.time()}


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 300)
    return path


async def test_a_copy_left_by_a_fast_5xx_is_deleted(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    # Each attempt stores a copy, then the server answers 503 at once (not "accepted": no billing doubt).
    mock_api.post("/files").mock(return_value=httpx.Response(503))
    stored = [_copy(f"file-{n}") for n in range(1, 5)]
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": stored}))
    deletes = mock_api.delete(url__regex=r".*/files/file-\d").mock(return_value=httpx.Response(200, json={}))
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(MetaUnavailable):
        await store.upload(clip, "sam_proxy.mp4")
    assert deletes.call_count == 4
    assert await store.delete_all() is True


async def test_a_copy_that_lands_after_the_listing_is_found_at_the_end(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(side_effect=httpx.ReadTimeout("slow"))
    listings = iter([[], [_copy("file-9")]])  # empty right after the timeout; the copy lands later
    mock_api.get("/files").mock(side_effect=lambda _: httpx.Response(200, json={"data": next(listings)}))
    late = mock_api.delete("/files/file-9").mock(return_value=httpx.Response(200, json={}))
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(MetaUnavailable):
        await store.upload(clip, "sam_proxy.mp4")
    assert not store.index().all_deleted  # never claimed while a copy may still land
    assert await store.delete_all() is True
    assert late.call_count == 1
