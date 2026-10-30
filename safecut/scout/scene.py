"""``scene``: one Muse call on the whole prepared clip plus its transcript → ``scene.json`` (``scene-pass.md``).

Context only: it can never create a keep, and its times aren't trusted. The stage always writes ``scene.json``
(``failed`` or ``skipped`` with no participants when the call can't answer), because WP3's children gate reads
its ``status``. Post-processing nulls any speaker label the transcript doesn't have and any introduction that
isn't really in the turn it names (vectors P7, P11b, P11c).
"""

from __future__ import annotations

import asyncio
import string
from pathlib import Path

from safecut import config
from safecut.config import Settings
from safecut.contracts import CandidateObject, Job, Participant, Scene, SceneChild, Transcript, dump, load
from safecut.meta import replay
from safecut.meta.client import MetaClient
from safecut.meta.files import FileStore
from safecut.meta.session import job_client
from safecut.scout import calls, prompts
from safecut.scout.schemas import SCENE, SceneOut, SceneParticipant

JOB = "job.json"
TRANSCRIPT = "transcript.json"
SCENE_FILE = "scene.json"
STAGE = "scene"
KEY = "scene"
CREATOR_NOTE = "none"  # v1 has no upload note (PRE-A §4.3); the slot stays for a later version
_DELETE = str.maketrans("", "", string.punctuation + "‘’“”–—…")


def normalise(text: str) -> str:
    """Lowercase, punctuation deleted, spaces collapsed: how quotes are compared with turns."""
    return " ".join(text.lower().translate(_DELETE).split())


def load_transcript(job_dir: Path) -> Transcript | None:
    path = job_dir / TRANSCRIPT
    return load(path, Transcript) if path.exists() else None


def usable(transcript: Transcript | None) -> bool:
    return transcript is not None and transcript.status == "ok" and not transcript.degraded


def transcript_text(job: Job, transcript: Transcript | None) -> str:
    """``[#0 S1 0.4–3.1 s] Hi, I'm Amina…`` per turn, with the 0-based turn numbers introductions cite."""
    if not job.audio:
        return "none (the clip has no audio)"
    if not usable(transcript) or transcript is None:
        return "speech unavailable"
    if not transcript.turns:
        return "none (no speech was recognised)"
    return "\n".join(f"[#{i} {t.speaker} {t.start:.1f}–{t.end:.1f} s] {t.text}" for i, t in enumerate(transcript.turns))


def check_participant(p: SceneParticipant, transcript: Transcript | None) -> Participant:
    """Keep a speaker only if the transcript has it; keep an introduction only if its quote (≥ 2 words after
    normalising) is in the turn it names. Otherwise null both introduction fields (API-NOTES §12)."""
    turns = transcript.turns if usable(transcript) and transcript is not None else []
    speakers = {t.speaker for t in turns}
    speaker = p.speaker if p.speaker in speakers else None
    turn, quote = p.introduced_in_turn, p.introduction_quote
    keep_intro = (
        turn is not None
        and quote is not None
        and 0 <= turn < len(turns)
        and len(normalise(quote).split()) >= 2
        and normalise(quote) in normalise(turns[turn].text)
    )
    return Participant(
        description=p.description,
        evidence=p.evidence,
        speaker=speaker,
        is_creator=p.is_creator,
        introduced_in_turn=turn if keep_intro else None,
        introduction_quote=quote if keep_intro else None,
    )


def to_scene(answer: SceneOut, model: str, transcript: Transcript | None) -> Scene:
    return Scene(
        status="ok",
        model=model,
        summary=answer.summary,
        participants=[check_participant(p, transcript) for p in answer.participants],
        candidate_objects=[CandidateObject(what=o.what, approx_time=o.approx_time) for o in answer.candidate_objects],
        children=[SceneChild(description=c.description) for c in answer.children],
        others_present=answer.others_present,
    )


def no_scene(status: str, reason: str) -> Scene:
    verb = "skipped" if status == "skipped" else "failed"
    return Scene(status="skipped" if status == "skipped" else "failed", model=None,
                 summary=f"scene pass {verb}: {reason}", participants=[], candidate_objects=[])  # fmt: skip


async def scene(ctx: calls.Context) -> Scene:
    transcript = load_transcript(ctx.job_dir)
    context = prompts.render("scene.transcript", transcript_text=transcript_text(ctx.job, transcript),
                             creator_note=CREATOR_NOTE)  # fmt: skip

    def messages(file_id: str | None) -> list[calls.Message]:
        if file_id is None:
            raise ValueError("the scene pass is a video call")
        ask = calls.text_part(prompts.text("scene.user"))
        return [calls.system(prompts.text("scene.system")),
                calls.user(ask, calls.video_part(file_id), calls.text_part(context))]  # fmt: skip

    model = ctx.settings.scene_model
    outcome = await calls.call_json(ctx, stage=STAGE, key=KEY, model=model, effort=ctx.settings.scene_effort,
                                    messages=messages, schema=SCENE, schema_name="scene_pass", out=SceneOut,
                                    video=True)  # fmt: skip
    if outcome.status != "ok" or outcome.value is None:
        return no_scene(outcome.status, outcome.reason)
    return to_scene(outcome.value, model, transcript)


async def run_async(
    job_dir: Path,
    *,
    replay_mode: bool = False,
    settings: Settings | None = None,
    client: MetaClient | None = None,
    responder: replay.Responder | None = None,
) -> Path:
    settings = settings or config.load_settings()
    job = load(job_dir / JOB, Job)
    ctx = calls.Context(job_dir=job_dir, job=job, settings=settings, replay=replay_mode or settings.replay,
                        responder=responder)  # fmt: skip
    if ctx.replay or ctx.responder is not None:
        return dump(await scene(ctx), job_dir / SCENE_FILE)
    if client is None:
        async with job_client(job_dir, settings) as own:
            return await run_async(job_dir, replay_mode=False, settings=settings, client=own)
    ctx.client, ctx.store = client, FileStore(client, job_dir)
    try:
        return dump(await scene(ctx), job_dir / SCENE_FILE)
    finally:
        await ctx.store.delete_all()


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The ``scene`` stage entry point: writes and returns ``scene.json``."""
    return asyncio.run(run_async(job_dir, replay_mode=replay))
