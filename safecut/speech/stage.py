"""``transcribe``: the prepared clip's soundtrack → ``transcript.json`` (ARCHITECTURE §3.3, PRE-A §4, §12).

Primary: Muse Voice Transcribe in ``DIARIZATION`` mode on a mono 16-bit 24 kHz WAV extracted from
``prepared.mp4``, so turn times are on the prepared clock. Fallback (``SAFECUT_SPEECH_SOURCE=spark-1.2``, or
Voice Transcribe failing after its retries): Muse Spark 1.2 hears the MP4's soundtrack (``speech-fallback.md``).
The stage always writes ``transcript.json`` when the clip has audio: ``failed`` after both paths fail,
``skipped`` on a budget stop, each with no turns and ``degraded: true`` (the policy then holds participants).
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, cast

from safecut import config
from safecut.config import Settings
from safecut.contracts import Job, Transcript, Turn, dump, load
from safecut.meta import asr, replay
from safecut.meta.client import MetaClient
from safecut.meta.errors import BudgetExceeded, MetaError
from safecut.meta.files import FileStore
from safecut.meta.session import job_client
from safecut.scout import calls, prompts
from safecut.scout.schemas import SPEECH, SpeechOut
from safecut.track import media

log = logging.getLogger(__name__)

JOB = "job.json"
TRANSCRIPT = "transcript.json"
WAV = "speech.wav"
ASR_STAGE = "asr"
ASR_KEY = "transcribe"
FALLBACK_STAGE = "speech"
FALLBACK_KEY = "fallback"
_SPEAKER = re.compile(r"^[SU][1-9][0-9]*$")
#: A fallback answer with fewer input tokens than this per second of clip didn't ingest the media at all (cookbook
#: issue #59 counted only the prompt text). It can't tell a dropped soundtrack under an ingested video (≈ 2,200
#: tokens/s); WP0's probe e measures that floor once the key exists.
MIN_TOKENS_PER_SECOND = 10


def no_speech(status: str, reason: str) -> Transcript:
    log.warning("no transcript", extra={"status": status, "reason": reason})
    return Transcript(status="failed" if status == "failed" else "skipped", source=None, source_kind=None,
                      degraded=True, turns=[])  # fmt: skip


def extract_wav(job_dir: Path, job: Job) -> Path:
    out = job_dir / WAV
    media.run(["-y", "-i", str(job_dir / job.prepared), "-vn", "-ac", "1", "-ar", "24000", "-sample_fmt", "s16",
               "-c:a", "pcm_s16le", str(out)])  # fmt: skip
    return out


def clamp_turns(turns: list[Turn], seconds: float) -> list[Turn]:
    """Clamp to the clip, drop reversed turns, sort by start (``speech-fallback.md`` post-processing)."""
    out: list[Turn] = []
    for t in turns:
        start, end = min(max(t.start, 0.0), seconds), min(max(t.end, 0.0), seconds)
        if end >= start:
            out.append(t.model_copy(update={"start": start, "end": end}))
    return sorted(out, key=lambda t: (t.start, t.end))


def fallback_turns(answer: SpeechOut, seconds: float) -> list[Turn]:
    """The fallback's turns on the contract's labels. ``has_speech: false`` means none. A label that isn't
    ``S<n>``/``U<n>``, or a ``U`` label used twice (an uncertain voice is never reused), gets a fresh ``U``."""
    if not answer.has_speech:
        return []
    used_u = [int(t.speaker[1:]) for t in answer.turns if _SPEAKER.fullmatch(t.speaker) and t.speaker[0] == "U"]
    next_u = max(used_u, default=0) + 1
    seen_u: set[str] = set()
    turns: list[Turn] = []
    for t in answer.turns:
        speaker = t.speaker
        if not _SPEAKER.fullmatch(speaker) or speaker in seen_u:
            speaker, next_u = f"U{next_u}", next_u + 1
        if speaker.startswith("U"):
            seen_u.add(speaker)
        if t.end < t.start:
            continue
        turns.append(Turn(speaker=speaker, start=max(t.start, 0.0), end=max(t.end, 0.0), text=t.text))
    return clamp_turns(turns, seconds)


async def primary(ctx: calls.Context) -> tuple[str, Any]:
    """Voice Transcribe: ``("ok", body)``, ``("failed", reason)`` or ``("skipped", reason)``; recorded either way."""
    settings = ctx.settings
    if ctx.responder is not None:
        replay.save(ctx.job_dir, ASR_STAGE, ASR_KEY, ctx.responder(ASR_STAGE, ASR_KEY, {}))
    if ctx.replay or ctx.responder is not None:
        raw = replay.load_call(ctx.job_dir, ASR_STAGE, ASR_KEY)
        failure = raw.failure()
        if failure is not None:
            return ("skipped" if failure[0] == "budget" else "failed", failure[1])
        return "ok", raw.response
    if ctx.client is None:
        raise ValueError("a live transcribe needs the job's client")
    request = {"mode": "DIARIZATION", "language_bias": list(settings.asr_language_bias)}

    def record(**fields: Any) -> None:
        call = replay.RawCall(synthetic=False, stage="speech", model=settings.asr_model, request=request, **fields)
        replay.save(ctx.job_dir, ASR_STAGE, ASR_KEY, call)

    try:
        wav = await asyncio.to_thread(extract_wav, ctx.job_dir, ctx.job)
    except media.MediaError as exc:
        record(response={"failed": "MediaError", "reason": str(exc)[:300]})
        return "failed", "MediaError"
    try:
        body = await asr.transcribe_raw(ctx.client, wav, model=settings.asr_model,
                                        language_bias=settings.asr_language_bias)  # fmt: skip
        asr.parse_response(body)  # an undocumented shape fails here, before it's trusted
    except BudgetExceeded as exc:
        record(response={"failed": "budget", "reason": str(exc)})
        return "skipped", f"budget: {exc.cap}"
    except MetaError as exc:
        record(response={"failed": type(exc).__name__, "reason": str(exc)[:300]})
        return "failed", type(exc).__name__
    finally:
        wav.unlink(missing_ok=True)
    record(response=body)
    return "ok", body


async def fallback(ctx: calls.Context) -> Transcript:
    settings = ctx.settings
    names = "none"

    def messages(file_id: str | None) -> list[calls.Message]:
        if file_id is None:
            raise ValueError("the speech fallback is a video call")
        ask = calls.text_part(prompts.render("speech.user", names=names))
        return [calls.system(prompts.text("speech.system")), calls.user(calls.video_part(file_id), ask)]

    outcome = await calls.call_json(
        ctx, stage=FALLBACK_STAGE, key=FALLBACK_KEY, model=settings.speech_fallback_model,
        effort=settings.speech_fallback_effort, messages=messages, schema=SPEECH, schema_name="speech_fallback",
        out=SpeechOut, video=True,
    )  # fmt: skip
    if outcome.status != "ok" or outcome.value is None:
        return no_speech(outcome.status, outcome.reason)
    usage: Any = (outcome.response or {}).get("usage")
    tokens = cast(dict[str, Any], usage).get("input_tokens") if isinstance(usage, dict) else None
    dropped = isinstance(tokens, int) and tokens < MIN_TOKENS_PER_SECOND * ctx.seconds
    turns = [] if dropped else fallback_turns(outcome.value, ctx.seconds)
    return Transcript(status="ok", source=settings.speech_fallback_model, source_kind="fallback", degraded=dropped,
                      turns=turns)  # fmt: skip


async def transcribe(ctx: calls.Context) -> Transcript:
    if not ctx.job.audio:
        return Transcript(status="ok", source=None, source_kind=None, degraded=False, turns=[])
    if ctx.settings.speech_source == "asr":
        status, body = await primary(ctx)
        if status == "ok":
            response = asr.parse_response(body)
            transcript = asr.to_transcript(response, source_model=ctx.settings.asr_model)
            return transcript.model_copy(update={"turns": clamp_turns(transcript.turns, ctx.seconds)})
        if status == "skipped":
            return no_speech("skipped", str(body))
        log.warning("Voice Transcribe failed; trying the speech fallback", extra={"reason": body})
    return await fallback(ctx)


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
    if ctx.replay or ctx.responder is not None or not job.audio:
        return dump(await transcribe(ctx), job_dir / TRANSCRIPT)
    if client is None:
        async with job_client(job_dir, settings) as own:
            return await run_async(job_dir, replay_mode=False, settings=settings, client=own)
    ctx.client, ctx.store = client, FileStore(client, job_dir)
    try:
        return dump(await transcribe(ctx), job_dir / TRANSCRIPT)
    finally:
        await ctx.store.delete_all()


def run(job_dir: Path, *, replay: bool = False) -> Path:
    return asyncio.run(run_async(job_dir, replay_mode=replay))
