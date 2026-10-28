"""Muse Voice Transcribe: ``POST /v1/asr/transcribe`` (PRE-A §4) and the mapping to ``transcript.json``."""

from __future__ import annotations

import asyncio
import json
import wave
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from safecut import config
from safecut.contracts import Transcript, Turn
from safecut.meta import cost
from safecut.meta.client import CallSpec, MetaClient, Units
from safecut.meta.errors import MetaBadRequest, MetaIncomplete
from safecut.meta.retry import RetryPolicy

Mode = Literal["PUSH_TO_TALK", "ENDPOINTING", "DIARIZATION"]
_MODES: frozenset[str] = frozenset({"PUSH_TO_TALK", "ENDPOINTING", "DIARIZATION"})
MAX_ASR_BYTES = 32 * 1024 * 1024
MAX_ASR_SECONDS = 600


class AsrTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start_ms: int = Field(alias="startMs", ge=0)
    end_ms: int = Field(alias="endMs", ge=0)
    transcript: str = ""
    speaker: str | None = None

    @field_validator("speaker", mode="before")
    @classmethod
    def _speaker_text(cls, value: object) -> object:
        # Documented as a letter; accept a number too rather than fail a billed call on it.
        return str(value) if isinstance(value, int | float) and not isinstance(value, bool) else value


class AsrResponse(BaseModel):
    """The documented response shape; unknown fields are ignored, missing required ones are an error."""

    model_config = ConfigDict(extra="ignore")

    transcript: str = ""
    audio_duration_ms: int = Field(alias="audioDurationMs", ge=0)

    @field_validator("audio_duration_ms", mode="before")
    @classmethod
    def _whole_ms(cls, value: object) -> object:
        return int(value) if isinstance(value, float) and value >= 0 else value

    turns: list[AsrTurn] = Field(default_factory=list[AsrTurn])


def request_part(
    model: str, *, mode: str, language_bias: Sequence[str], keywords: Sequence[str] = ()
) -> dict[str, Any]:
    """The JSON ``request`` part. Mode is checked here: Meta silently ignores an unknown mode."""
    if mode not in _MODES:
        raise ValueError(f"unknown ASR mode {mode!r}; Meta would ignore it silently")
    config.ensure_standard_model(model)
    part: dict[str, Any] = {"mode": mode, "model": model, "audioEncoding": "WAV", "keywords": list(keywords)}
    if language_bias:
        part["languageBias"] = list(language_bias)
    return part


def wav_seconds(path: Path) -> float:
    """Duration of a PCM WAV file, for the pre-call estimate and the size limits."""
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("Voice Transcribe wants mono 16-bit WAV")
        return wav.getnframes() / float(wav.getframerate())


def _audio_facts(path: Path) -> tuple[int, float]:
    return path.stat().st_size, wav_seconds(path)


def _meter(response: Mapping[str, Any]) -> tuple[Units, float | None]:
    duration = response.get("audioDurationMs")
    if not isinstance(duration, int | float) or isinstance(duration, bool) or not duration > 0:
        return {}, None
    seconds = cost.asr_billed_seconds(int(duration))
    return {"audio_s": seconds}, cost.asr_usd(seconds)


async def transcribe(
    client: MetaClient,
    wav_path: str | Path,
    *,
    model: str,
    language_bias: Sequence[str],
    mode: Mode = "DIARIZATION",
    stage: str = "speech",
) -> AsrResponse:
    """One-shot transcription of a mono 16-bit WAV (≤ 10 min, ≤ 32 MB)."""
    body = await transcribe_raw(client, wav_path, model=model, language_bias=language_bias, mode=mode, stage=stage)
    return parse_response(body)


async def transcribe_raw(
    client: MetaClient,
    wav_path: str | Path,
    *,
    model: str,
    language_bias: Sequence[str],
    mode: Mode = "DIARIZATION",
    stage: str = "speech",
) -> Any:
    """:func:`transcribe`'s call, returning the response body as Meta sent it: any JSON, or ``None`` when empty
    (probe d records it raw)."""
    path = Path(wav_path)
    size, seconds = await asyncio.to_thread(_audio_facts, path)
    if size > MAX_ASR_BYTES or seconds > MAX_ASR_SECONDS:
        raise MetaBadRequest(f"audio too large for one-shot ASR ({seconds:.0f} s, {size} bytes)")
    part = json.dumps(request_part(model, mode=mode, language_bias=language_bias)).encode()
    handles: list[IO[bytes]] = []

    def body() -> dict[str, Any]:
        handle = path.open("rb")
        handles.append(handle)
        return {"request": (None, part, "application/json"), "audio": (path.name, handle, "audio/wav")}

    spec = CallSpec(
        stage=stage,
        model=model,
        estimate_usd=cost.asr_estimate(seconds),
        estimate_units={"audio_s": float(int(seconds) + 1)},
        policy=RetryPolicy.for_asr(),
        timeout=httpx.Timeout(config.ASR_TOTAL_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        total_timeout_s=config.ASR_TOTAL_TIMEOUT_S,
    )
    try:
        result = await client.request("POST", "asr/transcribe", spec, meter=_meter, files=body)
    finally:
        for handle in handles:
            handle.close()
    return result.body


def parse_response(body: Any) -> AsrResponse:
    """The documented fields of a Voice Transcribe body; unknown fields are ignored, never an error."""
    try:
        return AsrResponse.model_validate(body)
    except ValidationError as exc:
        raise MetaIncomplete(
            f"ASR response does not match the documented shape: {exc.error_count()} error(s)", eof=False
        ) from exc


def to_transcript(
    response: AsrResponse, *, source_model: str, kind: Literal["primary", "fallback"] = "primary"
) -> Transcript:
    """Map Voice Transcribe turns to ``transcript.json`` (PRE-A §4.2, decided).

    Speaker letters become ``S1``, ``S2``… in order of first appearance; a turn with no speaker gets a
    fresh ``U<n>`` that's never reused. Times move from ms to prepared-clock seconds. Turns are sorted.
    """
    labels: dict[str, str] = {}
    unknown = 0
    turns: list[Turn] = []
    for raw in sorted(response.turns, key=lambda t: (t.start_ms, t.end_ms)):
        if raw.speaker:
            label = labels.setdefault(raw.speaker, f"S{len(labels) + 1}")
        else:
            unknown += 1
            label = f"U{unknown}"
        end_ms = max(raw.end_ms, raw.start_ms)
        turns.append(Turn(speaker=label, start=raw.start_ms / 1000, end=end_ms / 1000, text=raw.transcript))
    return Transcript(status="ok", source=source_model, source_kind=kind, degraded=False, turns=turns)
