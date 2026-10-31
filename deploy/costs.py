"""The deployed service's Modal cost, idle and per job, as **estimates** from ``modal billing rates`` and the sizes
in ``deploy/modal_app.py`` (``python -m deploy.costs`` prints the table that ``docs/DEPLOY-COSTS.md`` and
``docs/SUBMISSION.md`` carry; ``tests/test_deploy.py`` keeps them in step). Nothing here is a measured bill: the
run times below are assumptions, named as such, until a deployed run's receipts and Modal's usage page replace them.
"""

from __future__ import annotations

from dataclasses import dataclass

from safecut.config import Settings

#: ``modal billing rates`` (https://modal.com/pricing, read 2026-10-31): per hour.
CPU_CORE_HOUR = 0.0473
GIB_HOUR = 0.008
GPU_HOUR = {"L4": 0.80, "T4": 0.59}

#: Container sizes (deploy/modal_app.py; tests/test_deploy.py checks they match).
API_CPU, API_GIB, API_SCALEDOWN_S = 1.0, 2.0, 300
CRON_CPU, CRON_GIB, CRON_SCALEDOWN_S = 0.125, 0.125, 2
GPU_CPU, GPU_GIB, GPU_SCALEDOWN_S = 2.0, 6.0, 30
#: What the API container cost before this lane: always on, 2 cores and 4 GiB.
OLD_API_CPU, OLD_API_GIB = 2.0, 4.0

#: Assumptions, not measurements: one cron run's billed seconds (start, sweep, exit); one 60 s clip's time in the
#: API container (analyse, review, publish; a judge's pauses between them are the scaledown tail); and its GPU
#: seconds (a cold start, ~3,600 detector passes at ~20 ms on an L4, decoding, re-checks).
CRON_RUN_S = 12
JOB_API_S = 300
JOB_GPU_S = 210
RUNS_PER_DAY = 24 * 4
#: The worst case the ledger reserves for one job's GPU audit (safecut/api/access.py): 3 passes at their timeout.
JOB_GPU_WORST_S = 3 * 300 + GPU_SCALEDOWN_S


def hourly(cpu: float, gib: float, gpu: str | None = None) -> float:
    return cpu * CPU_CORE_HOUR + gib * GIB_HOUR + (GPU_HOUR[gpu] if gpu else 0.0)


def usd(seconds: float, per_hour: float) -> float:
    return seconds * per_hour / 3600


@dataclass(frozen=True)
class Row:
    what: str
    runs: str
    usd: float
    per: str


def rows() -> list[Row]:
    api, cron, l4 = hourly(API_CPU, API_GIB), hourly(CRON_CPU, CRON_GIB), hourly(GPU_CPU, GPU_GIB, "L4")
    return [
        Row(
            "Idle, before (always on)",
            "API, 2 cores + 4 GiB, all day",
            usd(86400, hourly(OLD_API_CPU, OLD_API_GIB)),
            "day",
        ),
        Row(
            "Idle, now (scaled to zero)",
            f"cleanup cron only, {RUNS_PER_DAY} runs of ~{CRON_RUN_S + CRON_SCALEDOWN_S} s",
            usd(RUNS_PER_DAY * (CRON_RUN_S + CRON_SCALEDOWN_S), cron),
            "day",
        ),
        Row(
            "A visit's quiet tail",
            f"API stays up {API_SCALEDOWN_S} s after the last request",
            usd(API_SCALEDOWN_S, api),
            "visit",
        ),
        Row("One 60 s clip, API", f"~{JOB_API_S} s of the API container", usd(JOB_API_S, api), "clip"),
        Row(
            "One 60 s clip, GPU audit",
            f"~{JOB_GPU_S} s on an L4, plus its {GPU_SCALEDOWN_S} s tail",
            usd(JOB_GPU_S + GPU_SCALEDOWN_S, l4),
            "clip",
        ),
        Row(
            "One clip, GPU worst case",
            f"what the estimate reserves: {JOB_GPU_WORST_S} s",
            usd(JOB_GPU_WORST_S, Settings().audit_gpu_usd_per_hour),
            "clip",
        ),
    ]


def table() -> str:
    """The cost table, as fixed-width text (it sits in a ``text`` block in the docs: estimates, not results)."""
    lines = [f"{'Modal cost (estimate)':<28} {'What runs':<52} {'USD':>8}  per"]
    lines += [f"{r.what:<28} {r.runs:<52} {r.usd:>8.4f}  {r.per}" for r in rows()]
    return "\n".join(lines)


if __name__ == "__main__":
    print(table())
