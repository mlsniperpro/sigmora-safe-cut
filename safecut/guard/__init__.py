"""guard: ``decisions.json`` + ``tracks.json`` → ``plan.json`` (the leak guard, WP3 step 5).

``run(job_dir)`` reads ``job.json``, ``tracks.json`` and ``decisions.json`` (and ``audit.json`` when an earlier audit
flagged an item it read through, which then renders solid), and writes ``plan.json``. No API call: ``replay``
changes nothing.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from safecut.contracts import Audit, Decisions, Job, Tracks, dump, load
from safecut.guard.plan import RegionCache, plan, read_through

PLAN = "plan.json"

#: Region caches of the last few jobs this process planned, each scoped to the exact ``job.json`` and ``tracks.json``
#: it was built from (path, size and modification time), so a review edit re-plans only from cached regions.
_CACHES: OrderedDict[tuple[object, ...], RegionCache] = OrderedDict()
_KEEP = 4


def _cache_for(job_dir: Path) -> RegionCache:
    stats = [(job_dir / name).stat() for name in ("job.json", "tracks.json")]
    key = (str(job_dir.resolve()), *((s.st_size, s.st_mtime_ns, s.st_ino) for s in stats))
    found = _CACHES.pop(key, None)
    if found is not None:
        cache = found
    else:
        for stale in [k for k in _CACHES if k[0] == key[0]]:
            del _CACHES[stale]
        cache: RegionCache = {}
    _CACHES[key] = cache
    while len(_CACHES) > _KEEP:
        _CACHES.popitem(last=False)
    return cache


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """Write ``plan.json`` and return its path."""
    del replay  # no API call in this stage
    audit_path = job_dir / "audit.json"
    flagged = load(audit_path, Audit).leaks if audit_path.exists() else []
    built = plan(
        load(job_dir / "job.json", Job),
        load(job_dir / "tracks.json", Tracks),
        load(job_dir / "decisions.json", Decisions),
        solid=read_through(flagged),
        cache=_cache_for(job_dir),
    )
    return dump(built, job_dir / PLAN)


__all__ = ["PLAN", "plan", "run"]
