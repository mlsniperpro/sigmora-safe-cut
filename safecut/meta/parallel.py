"""CPU-bound work across a small process pool (Meta's SAM mask codec is pure Python).

Workers are spawned, never forked from a threaded event loop. Where a pool can't start (a sandbox without
``fork``/``spawn``, an interpreter fed from stdin), the same work runs in this process, logged: the result is
identical, only slower.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

log = logging.getLogger(__name__)

MAX_WORKERS = 8


def workers() -> int:
    return max(1, min(MAX_WORKERS, os.cpu_count() or 1))


_ONE_POOL = threading.Lock()


def map_in_pool[T, R](fn: Callable[[T], R], items: Sequence[T], *, parallel: bool = True) -> list[R]:
    """``[fn(x) for x in items]``, in a spawned pool when ``parallel`` and it's worth it. ``fn`` must be a
    module-level function (picklable)."""
    if not parallel or len(items) < 2 or workers() < 2:
        return [fn(x) for x in items]
    try:
        context = multiprocessing.get_context("spawn")
        # One pool at a time per process: concurrent SAM streams each parse in a thread, and a pool apiece would
        # start workers() interpreters per stream (7 sweeps × 8 on a busy clip). Each pool already uses every core.
        with _ONE_POOL, ProcessPoolExecutor(max_workers=min(workers(), len(items)), mp_context=context) as pool:
            return list(pool.map(fn, items))
    except (BrokenProcessPool, OSError) as exc:
        log.warning("process pool unavailable; running in-process", extra={"error": type(exc).__name__})
        return [fn(x) for x in items]
