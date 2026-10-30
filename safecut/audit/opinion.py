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
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

import cv2

from safecut import open_weight
from safecut.audit import leaks as rules
from safecut.audit.redteam import with_bar
from safecut.contracts import Decisions, Job, Leak, OpenWeightSummary, RedteamHit, RedteamNone, Track
from safecut.meta.errors import BudgetExceeded
from safecut.render.draw import Frame

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
    by_track: dict[str, Track],
    *,
    grid_ok: bool,
) -> tuple[list[RedteamNone | RedteamHit], list[Leak]]:
    """The opinion's frames as ``redteam_open`` entries (the red team's own mapping and exclusion rules), and the
    leaks to patch when its grid is confirmed."""
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
            box = (0, 0, job.width, job.height) if mapped in (None, "in_bar") else mapped
            exclude = rules.excluded_by(finding.kind, box, frame.frame, decisions, by_track)
            entries.append(RedteamHit(frame=frame.frame, finding="hit", kind=finding.kind, text=finding.text,
                                      detail=finding.detail, box=box, confidence=finding.confidence,
                                      excluded_by=exclude))  # fmt: skip
            hits += 1
            if exclude is None and grid_ok:
                found.append(Leak(frame=frame.frame, box=box, kind=finding.kind, detector="redteam_open",
                                  patched_item=None))  # fmt: skip
        if not hits:
            entries.append(RedteamNone(frame=frame.frame, finding="none"))
    return entries, found


async def consult(
    ask: Ask,
    frames: Sequence[tuple[int, Frame]],
    *,
    words: str,
    job: Job,
    decisions: Decisions,
    by_track: dict[str, Track],
    grid_ok: bool,
) -> Opinion:
    """One second opinion on ``frames``; a budget stop (raised before any call) leaves it off."""
    bar = rules.bar_height(job.height)
    try:
        answer = await ask([(f, data_url(img, f, bar)) for f, img in frames], words)
    except BudgetExceeded:
        return Opinion()
    entries, found = entries_for(answer, job, decisions, by_track, grid_ok=grid_ok)
    return Opinion(summary=answer.summary(entries), entries=entries, leaks=found)
