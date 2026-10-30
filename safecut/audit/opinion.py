"""The open-weight second opinion in the audit (PRE-A §3.8, ``redteam.md`` "Second opinion"): Muse Spark Open on
Baseten, through WP0's ``open_weight.second_opinion``.

At most once in a job's life (``job.open_weight_attempted`` is set before the first call, never cleared), after
the last red-team pass, on pass 1's frame set re-read from the **final** render, and only when the switch is on,
the job is consented and its code kind is allowed. Its answers go to ``audit.redteam_open``; they stay advisory
(logged, counted, never patched) until ``SAFECUT_OPEN_WEIGHT_GRID_OK`` confirms its boxes use the §5 grid, after
which its leaks are patched like any other, within the 3-pass cap. It never blocks the job: a failed batch only
makes the opinion ``failed``, and a budget stop leaves it ``off``.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
from pydantic import TypeAdapter

from safecut import open_weight
from safecut.audit import leaks as rules
from safecut.audit.redteam import with_bar
from safecut.contracts import Decisions, Job, Leak, OpenWeightSummary, Plan, RedteamHit, RedteamNone, Track
from safecut.meta.errors import BudgetExceeded
from safecut.render.draw import Frame

log = logging.getLogger(__name__)

#: ``second_opinion`` bound to a client and settings: frames as (number, data URL), the kept-clear words.
Ask = Callable[[Sequence[tuple[int, str]], str], Awaitable[open_weight.SecondOpinion]]


@dataclass
class Opinion:
    summary: OpenWeightSummary = field(default_factory=OpenWeightSummary)
    entries: list[RedteamNone | RedteamHit] = field(default_factory=list[RedteamNone | RedteamHit])
    #: Leaks to patch (only when the grid is confirmed); empty while the opinion is advisory.
    leaks: list[Leak] = field(default_factory=list[Leak])


def data_url(frame: Frame, number: int, bar: int) -> str:
    ok, buf = cv2.imencode(".jpg", with_bar(frame, number, bar), [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("couldn't encode a frame for the second opinion")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def entries_for(
    answer: open_weight.SecondOpinion,
    job: Job,
    decisions: Decisions,
    plan: Plan,
    by_track: dict[str, Track],
    *,
    grid_ok: bool,
) -> tuple[list[RedteamNone | RedteamHit], list[Leak]]:
    """The opinion's frames as ``redteam_open`` entries (the red team's own mapping, exclusion and read-through
    rules), and the leaks to patch when its grid is confirmed."""
    bar = rules.bar_height(job.height)
    entries: list[RedteamNone | RedteamHit] = []
    found: list[Leak] = []
    for frame in answer.frames:
        hits = 0
        for finding in frame.findings:
            mapped = (
                rules.grid_box(list(finding.box), width=job.width, height=job.height, bar=bar)
                if finding.box is not None
                else None
            )
            if mapped == "in_bar" and finding.kind == "text" and rules.is_frame_label(finding.text):
                continue
            placed = mapped not in (None, "in_bar")
            box = mapped if isinstance(mapped, tuple) else (0, 0, job.width, job.height)
            # A whole-frame box stands for a finding we couldn't place (fail closed): nothing kept excuses it.
            exclude = rules.excluded_by(finding.kind, box, frame.frame, decisions, by_track) if placed else None
            entries.append(RedteamHit(frame=frame.frame, finding="hit", kind=finding.kind, text=finding.text,
                                      detail=finding.detail, box=box, confidence=finding.confidence,
                                      excluded_by=exclude))  # fmt: skip
            hits += 1
            if exclude is None and grid_ok:
                through = (
                    rules.through_item(box, frame.frame, decisions, plan)
                    if finding.kind in ("text", "screen", "plate")
                    else None
                )
                found.append(Leak(frame=frame.frame, box=box, kind=finding.kind, detector="redteam_open",
                                  patched_item=None, flag="redaction_too_weak" if through else None,
                                  through_item=through))  # fmt: skip
        if not hits:
            entries.append(RedteamNone(frame=frame.frame, finding="none"))
    return entries, found


async def consult(
    ask: Ask,
    frames: Sequence[tuple[int, str]],
    *,
    model: str,
    words: str,
    job: Job,
    decisions: Decisions,
    plan: Plan,
    by_track: dict[str, Track],
    grid_ok: bool,
) -> Opinion:
    """One second opinion on ``frames`` (number, data URL). It never blocks the job: a budget stop (raised before
    any call) leaves it off; any other failure leaves it failed, with nothing to add."""
    try:
        answer = await ask(frames, words)
    except BudgetExceeded:
        return Opinion()
    except Exception as exc:  # an optional second look: any failure is recorded, never raised into the audit
        log.warning("open-weight second opinion failed (%s); the audit continues without it", type(exc).__name__)
        return Opinion(summary=OpenWeightSummary(model=model, status="failed"))
    entries, found = entries_for(answer, job, decisions, plan, by_track, grid_ok=grid_ok)
    return Opinion(summary=answer.summary(entries), entries=entries, leaks=found)


#: The opinion as it came back, saved at once: it runs once per job, so a later crash must not lose it.
RECORD = Path("raw/audit/opinion.json")
#: Written before the first call, beside ``job.open_weight_attempted``: a stage that rewrites ``job.json`` from the
#: source (a re-run of prepare) can't make the job eligible again.
ATTEMPTED = Path("raw/audit/opinion_attempted")


def attempted(job_dir: Path, job: Job) -> bool:
    return job.open_weight_attempted or (job_dir / ATTEMPTED).exists()


def mark_attempted(job_dir: Path) -> None:
    path = job_dir / ATTEMPTED
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("open-weight second opinion attempted\n", encoding="utf-8")


def save(job_dir: Path, opinion: Opinion) -> None:
    path = job_dir / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"summary": opinion.summary.model_dump(mode="json"), "entries": [e.model_dump(mode="json")
                                                                             for e in opinion.entries]}  # fmt: skip
    path.write_text(json.dumps(data))


def recorded(job_dir: Path) -> Opinion | None:
    """The saved opinion of an earlier run (its leaks were patched then; nothing to patch again)."""
    path = job_dir / RECORD
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = TypeAdapter(list[RedteamNone | RedteamHit]).validate_python(data["entries"])
    return Opinion(summary=OpenWeightSummary.model_validate(data["summary"]), entries=entries)
