"""WP0 D1 probes a–h: real Meta Model API calls whose raw responses become fixtures for every WP.

Each probe saves its raw responses under ``fixtures/probes/<name>/`` and a ``summary.json`` with the
numbers ``docs/API-NOTES.md`` quotes. Spend is logged to ``fixtures/probes/cost.jsonl`` and capped at
$6 in total (the WP0 budget) by the same ledger the pipeline uses. Only synthetic clips (or consented
hero clips) are ever sent (AGENTS rules 4-5), and every upload is deleted afterwards (rule 6).

Usage: ``uv run python -m scripts.probes.probes a b c`` (or ``all``). Needs ``MODEL_API_KEY``;
probe ``h`` needs ``BASETEN_API_KEY``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import httpx
import imageio_ffmpeg
import numpy as np
from meta_sam_parser import (
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    parse_responses_stream,
    video_segmentation_format,
)
from pydantic import BaseModel

from safecut import open_weight
from safecut.config import OpenWeightPrice, Settings, load_settings
from safecut.meta import asr, responses, sam
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import MetaError
from safecut.meta.files import FileStore
from safecut.meta.retry import RetryPolicy
from safecut.meta.status import fetch_status

ROOT = Path(__file__).resolve().parents[2]
CLIP = ROOT / "fixtures" / "clips" / "counter_30fps_audio.mp4"
TRUTH = ROOT / "fixtures" / "clips" / "truth.json"
PROBE_BUDGET_USD = 6.00
SAM_CONCEPTS = ("red square", "blue square", "face", "license plate")
#: ARCHITECTURE §3.2's base sweep concepts, used when a consented hero clip is given with ``--clip``.
HERO_CONCEPTS = ("face", "person", "license plate", "screen")

Summary = dict[str, Any]


@dataclass
class Probe:
    """Where one probe writes, and the clients it uses."""

    name: str
    out: Path
    settings: Settings
    meta: MetaClient
    files: FileStore
    clip: Path = CLIP
    keyframes: Path | None = None

    @property
    def synthetic(self) -> bool:
        return self.clip == CLIP

    def save(self, filename: str, data: Any) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / filename).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def truth() -> Mapping[str, Any]:
    return cast(Mapping[str, Any], json.loads(TRUTH.read_text())["counter_30fps_audio.mp4"])


def _frame_when_red_crosses_centre() -> int:
    """First frame whose red box centre is at or right of the frame centre (x = 160)."""
    t = truth()
    for key, boxes in sorted(t["boxes_half_open"].items(), key=lambda kv: int(kv[0])):
        x1, _, x2, _ = boxes["red"]
        if (x1 + x2) / 2 >= t["size"][0] / 2:
            return int(key)
    raise ValueError("the red box never crosses the centre")


def _iou(a: list[float], b: list[float]) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


async def _events(events: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for event in events:
        yield event


def _user_video(text: str, file_id: str) -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": [{"type": "input_text", "text": text}, {"type": "input_video", "file_id": file_id}]}
    ]


# -- a: models and status --------------------------------------------------------


async def probe_a(p: Probe) -> Summary:
    async with httpx.AsyncClient() as http:
        status = await fetch_status(http, p.settings.meta_base_url)
    spec = CallSpec(
        stage="probe_a",
        model=None,
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy(attempts=4),
        timeout=httpx.Timeout(30.0),
    )
    models = await p.meta.request("GET", "models", spec, meter=lambda _: ({}, 0.0))
    p.save("models.json", models.body)
    p.save("status.json", status.model_dump())
    raw: Any = models.body
    data: Any = cast(Mapping[str, Any], raw).get("data", []) if isinstance(raw, Mapping) else []
    items: list[Any] = cast(list[Any], data) if isinstance(data, list) else []
    ids = sorted(str(cast(Mapping[str, Any], m).get("id")) for m in items if isinstance(m, Mapping))
    wanted = [
        p.settings.sam_model,
        p.settings.role_model,
        "muse-wonder-1.0",
        p.settings.asr_model,
        p.settings.speech_fallback_model,
    ]
    return {
        "service_status": status.service_status,
        "model_ids": ids,
        "missing": [m for m in wanted if m not in ids],
        "contributor_ids_listed": [m for m in ids if m.endswith("-contributor")],
    }


# -- b: SAM 3.1 video -------------------------------------------------------------


async def _sam_once(p: Probe, file_id: str, concept: str, frames: int) -> Summary:
    body = sam.video_body(p.settings, file_id=file_id, text=concept)
    started = time.monotonic()
    result = await sam.segment_video(p.meta, body, sam_frames=frames, stage="probe_b")
    latency = time.monotonic() - started
    p.save(f"sam-{concept.replace(' ', '_')}.events.json", result.events)
    async with parse_responses_stream(_events(result.events), video_segmentation_format()) as parsed:
        final = await parsed.final_result()
    boxes = [r for r in final.records if isinstance(r, SegmentationBoxRecord)]
    masks = [r for r in final.records if isinstance(r, SegmentationMaskRecord)]
    frame_order = [b.frame.frame_index for b in boxes if b.frame is not None]
    summary: Summary = {
        "latency_s": round(latency, 2),
        "records": len(boxes),
        "objects": sorted({b.object_id for b in boxes}),
        "frames_with_detections": len(set(frame_order)),
        "frames_in_order": frame_order == sorted(frame_order),
        "confidence_present": any(b.confidence is not None for b in boxes),
        "mask_encodings": sorted({str(m.mask.encoding) for m in masks}),
        "mask_matches_box_size": all(
            (m.mask.width, m.mask.height) == (b.right - b.left, b.bottom - b.top)
            for m, b in zip(masks, boxes, strict=False)
        ),
        "frames_billed": result.response.get("usage", {}).get("video_frames_processed"),
        "usd": result.usd,
        "diagnostics": [str(d) for d in final.diagnostics][:10],
    }
    colour = concept.split(maxsplit=1)[0]
    if p.synthetic and colour in ("red", "blue"):
        gt = truth()["boxes_half_open"]
        ious = [
            _iou([b.left, b.top, b.right, b.bottom], gt[str(b.frame.frame_index)][colour])
            for b in boxes
            if b.frame is not None and str(b.frame.frame_index) in gt
        ]
        summary["mean_iou_vs_truth"] = round(sum(ious) / len(ious), 3) if ious else None
    return summary


def count_frames(clip: Path) -> int:
    """Video frames as the bundled ffmpeg's ``framemd5`` counts them (PRE-A §5b: never duration × fps)."""
    argv = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(clip), "-map", "0:v:0", "-c", "copy",
            "-f", "framemd5", "-"]  # fmt: skip
    out = subprocess.run(argv, check=True, capture_output=True, text=True).stdout  # noqa: S603 -- fixed argv
    return sum(1 for line in out.splitlines() if line and not line.startswith("#"))


async def probe_b(p: Probe) -> Summary:
    frames = await asyncio.to_thread(count_frames, p.clip)
    file_id = await p.files.upload(p.clip, "sam_proxy.mp4")
    concepts = SAM_CONCEPTS if p.synthetic else HERO_CONCEPTS
    out: Summary = {"clip": p.clip.name, "synthetic": p.synthetic, "frames": frames, "concepts": {}}
    for concept in concepts:
        try:
            out["concepts"][concept] = await _sam_once(p, file_id, concept, frames)
        except MetaError as exc:
            out["concepts"][concept] = {"error": f"{type(exc).__name__}: {exc}"}
    if not p.synthetic:
        return out
    # Does SAM accept an fps hint on the video part? (undocumented; PRE-A §1.6)
    body = sam.video_body(p.settings, file_id=file_id, text="red square")
    body["input"][0]["content"][1]["fps"] = 8
    try:
        hinted = await sam.segment_video(p.meta, body, sam_frames=frames, stage="probe_b")
        out["input_video_fps_8"] = {
            "accepted": True,
            "frames_billed": hinted.response.get("usage", {}).get("video_frames_processed"),
        }
    except MetaError as exc:
        out["input_video_fps_8"] = {"accepted": False, "error": f"{type(exc).__name__}: {exc}"}
    return out


# -- c, e, f: video questions --------------------------------------------------------

VIDEO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["frame_red_centre_crosses_middle", "beep_heard", "beep_first_frame", "beep_last_frame", "summary"],
    "properties": {
        "frame_red_centre_crosses_middle": {"type": ["integer", "null"]},
        "beep_heard": {"type": "boolean"},
        "beep_first_frame": {"type": ["integer", "null"]},
        "beep_last_frame": {"type": ["integer", "null"]},
        "summary": {"type": "string"},
    },
}

VIDEO_QUESTION = (
    "This short synthetic clip shows a red square moving right and a blue square moving down. A black bar at the "
    "top shows the frame number as 'F 000042'. Answer from what you see and hear: (1) the frame number visible in "
    "the bar on the first frame where the centre of the red square is at or right of the middle of the picture; "
    "(2) whether a beep is audible, and the frame numbers visible when it starts and stops. Use null when unsure."
)


async def _video_question(p: Probe, *, model: str, effort: str, stage: str, file_id: str) -> Summary:
    body = responses.build_body(
        model, _user_video(VIDEO_QUESTION, file_id), effort=effort, schema=VIDEO_SCHEMA, schema_name="frame_probe"
    )
    started = time.monotonic()
    try:
        result = await responses.create(p.meta, body, stage=stage, effort=effort, video_seconds=3.0)
    except MetaError as exc:
        return {"model": model, "effort": effort, "error": f"{type(exc).__name__}: {exc}"}
    latency = time.monotonic() - started
    p.save(f"{stage}-{model}-{effort}.response.json", result.response)
    try:
        answer = json.loads(responses.output_text(result.response))
    except (MetaError, json.JSONDecodeError) as exc:
        return {"model": model, "effort": effort, "error": f"{type(exc).__name__}: {exc}", "usd": result.usd}
    usage = result.response.get("usage", {})
    truth_frame = _frame_when_red_crosses_centre()
    got = answer.get("frame_red_centre_crosses_middle")
    return {
        "model": model,
        "effort": effort,
        "latency_s": round(latency, 2),
        "usd": result.usd,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "answer": answer,
        "truth": {"frame_red_centre_crosses_middle": truth_frame, "beep_frames": truth()["beep_frames"]},
        "frame_error": None if got is None else abs(int(got) - truth_frame),
    }


async def probe_c(p: Probe) -> Summary:
    file_id = await p.files.upload(CLIP, "prepared.mp4")
    return await _video_question(p, model=p.settings.scene_model, effort="medium", stage="probe_c", file_id=file_id)


async def probe_e(p: Probe) -> Summary:
    file_id = await p.files.upload(CLIP, "prepared.mp4")
    return await _video_question(
        p,
        model=p.settings.speech_fallback_model,
        effort=p.settings.speech_fallback_effort,
        stage="probe_e",
        file_id=file_id,
    )


async def probe_f(p: Probe) -> Summary:
    file_id = await p.files.upload(CLIP, "prepared.mp4")
    out: Summary = {}
    for model, effort in (("muse-spark-1.3", "max"), ("muse-wonder-1.0", "max"), ("muse-wonder-1.0", "medium")):
        out[f"{model}@{effort}"] = await _video_question(
            p, model=model, effort=effort, stage="probe_f", file_id=file_id
        )
    if p.keyframes is not None:
        out["role_calls"] = await _role_calls(p, p.keyframes)
    return out


ROLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["role", "evidence"],
    "properties": {
        "role": {"type": "string", "enum": ["participant", "bystander", "child", "unsure"]},
        "evidence": {"type": "string"},
    },
}


class RoleCall(BaseModel):
    """One hard role call: a consented Set-of-Mark keyframe, the label to judge, and the right answer."""

    image: str
    label: str
    context: str = ""
    expected: str


class _RoleAnswer(BaseModel):
    role: str
    evidence: str


async def _role_calls(p: Probe, keyframes: Path) -> Summary:
    """WP0.md probe f's role calls: Spark 1.3 vs Wonder 1.0, both at ``max``, on consented keyframes.

    ``keyframes/role_calls.json`` lists :class:`RoleCall` entries; images sit next to it. The boxes may be
    hand-drawn (WP0.md). Only consented hero keyframes may be used (AGENTS rule 5).
    """
    calls = [RoleCall.model_validate(c) for c in json.loads((keyframes / "role_calls.json").read_text())]
    out: Summary = {}
    for model in ("muse-spark-1.3", "muse-wonder-1.0"):
        rows: list[Summary] = []
        for call in calls:
            data = base64.b64encode((keyframes / call.image).read_bytes()).decode()
            prompt = (
                f"Decide the role of the person marked {call.label} in this frame of a creator's video: participant "
                "(part of the story), bystander, child, or unsure. Context: " + (call.context or "none")
            )
            content = [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{data}"},
            ]
            body = responses.build_body(
                model, [{"role": "user", "content": content}], effort="max", schema=ROLE_SCHEMA, schema_name="role_call"
            )
            started = time.monotonic()
            try:
                answer, result = await responses.create_json(p.meta, _RoleAnswer, body, stage="probe_f", effort="max")
            except MetaError as exc:
                rows.append({"image": call.image, "error": f"{type(exc).__name__}: {exc}"})
                continue
            rows.append(
                {
                    "image": call.image,
                    "expected": call.expected,
                    "got": answer.role,
                    "correct": answer.role == call.expected,
                    "usd": result.usd,
                    "latency_s": round(time.monotonic() - started, 2),
                }
            )
        answered = [r for r in rows if "correct" in r]
        out[model] = {
            "calls": rows,
            "correct": sum(1 for r in answered if r["correct"]),
            "answered": len(answered),
            "usd": round(sum(float(r["usd"]) for r in answered), 6),
        }
    return out


# -- d: Voice Transcribe -------------------------------------------------------------


def _extract_wav(clip: Path, wav: Path) -> None:
    """Mono 16-bit 24 kHz WAV, the engine-native Voice Transcribe format (PRE-A §4.1)."""
    argv = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-i", str(clip), "-ac", "1", "-ar", "24000",
            "-sample_fmt", "s16", str(wav)]  # fmt: skip
    subprocess.run(argv, check=True)  # noqa: S603 -- fixed argv, bundled ffmpeg


async def probe_d(p: Probe) -> Summary:
    wav = p.out / "audio.wav"
    p.out.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_extract_wav, p.clip, wav)
    started = time.monotonic()
    try:
        raw = await asr.transcribe(p.meta, wav, model=p.settings.asr_model, language_bias=p.settings.asr_language_bias)
    finally:
        wav.unlink(missing_ok=True)  # never leave a (possibly hero) voice track on disk
    latency = time.monotonic() - started
    p.save("asr.response.json", raw.model_dump(by_alias=True))
    transcript = asr.to_transcript(raw, source_model=p.settings.asr_model)
    return {
        "latency_s": round(latency, 2),
        "audio_duration_ms": raw.audio_duration_ms,
        "turns": len(transcript.turns),
        "transcript": raw.transcript,
        "clip": p.clip.name,
        "speakers": sorted({t.speaker for t in transcript.turns}),
        "turn_times": [[t.speaker, t.start, t.end] for t in transcript.turns][:50],
        "note": "synthetic tone: no speech expected" if p.synthetic else "consented hero clip",
    }


# -- g, h: image points -------------------------------------------------------------

IMG_W, IMG_H, BAR_H = 1280, 720, 40
DOT = (937, 211)  # frame pixels


def dot_image() -> str:
    """A 1280x760 image: a 40 px black bar above a grey 1280x720 frame with one red dot at ``DOT``."""
    img = np.full((IMG_H + BAR_H, IMG_W, 3), 128, dtype=np.uint8)
    img[:BAR_H] = 0
    cv2.putText(img, "F 000090", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.circle(img, (DOT[0], DOT[1] + BAR_H), 9, (0, 0, 255), thickness=-1)
    ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode()


POINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["x", "y"],
    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
}
POINT_QUESTION = (
    "Point at the centre of the red dot. Give x and y on a 0-1000 grid over the whole image you received, "
    "where (0, 0) is the top-left corner and (1000, 1000) the bottom-right corner."
)


def grid_to_frame(vx: int, vy: int) -> tuple[int, int]:
    """PRE-A §5: clamp to [0, 1000], round half up to sent-image pixels, then drop the bar."""

    def half_up(z: float) -> int:
        return math.floor(z + 0.5)

    vx, vy = min(max(vx, 0), 1000), min(max(vy, 0), 1000)
    x = min(half_up(vx * IMG_W / 1000), IMG_W - 1)
    y = min(half_up(vy * (IMG_H + BAR_H) / 1000), IMG_H + BAR_H - 1) - BAR_H
    return x, y


def _point_summary(answer: Mapping[str, Any], usd: float, latency: float) -> Summary:
    x, y = grid_to_frame(int(answer["x"]), int(answer["y"]))
    return {
        "answer_grid": dict(answer),
        "mapped_frame_px": [x, y],
        "truth_frame_px": list(DOT),
        "error_px": round(math.dist((x, y), DOT), 1),
        "raw_out_of_range": not (0 <= int(answer["x"]) <= 1000 and 0 <= int(answer["y"]) <= 1000),
        "usd": usd,
        "latency_s": round(latency, 2),
    }


class _Point(BaseModel):
    x: int
    y: int


async def probe_g(p: Probe) -> Summary:
    image = dot_image()
    messages = [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": POINT_QUESTION}, {"type": "input_image", "image_url": image}],
        }
    ]
    body = responses.build_body(
        p.settings.role_model, messages, effort="medium", schema=POINT_SCHEMA, schema_name="point"
    )
    started = time.monotonic()
    answer, result = await responses.create_json(p.meta, _Point, body, stage="probe_g", effort="medium")
    p.save("point.response.json", result.response)
    return _point_summary(answer.model_dump(), result.usd, time.monotonic() - started)


# -- h: the open-weight second opinion (PRE-A §3.8) ------------------------------------------

#: Baseten's published Muse Spark Open price (baseten.co/library/muse-spark-open, read 2026-10-26), used
#: only to reserve probe h's own calls when SAFECUT_OPEN_WEIGHT_PRICE isn't set yet; probe h records it.
BASETEN_PUBLISHED_PRICE = OpenWeightPrice.model_validate({"in": 1.25, "out": 4.25})
NAME_TEXT = "AMINA K."


def synthetic_frame(index: int, *, name: bool) -> tuple[str, tuple[int, int, int, int] | None]:
    """A 1280x760 JPEG (bar + frame). With ``name``, "AMINA K." is drawn; returns its half-open frame box."""
    img = np.full((IMG_H + BAR_H, IMG_W, 3), 96 + 20 * index, dtype=np.uint8)
    img[:BAR_H] = 0
    cv2.putText(img, f"F {index * 30:06d}", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.rectangle(img, (100 + 40 * index, 500), (260 + 40 * index, 640), (40, 160, 40), thickness=-1)
    box: tuple[int, int, int, int] | None = None
    if name:
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 2.0, 4
        (w, h), base = cv2.getTextSize(NAME_TEXT, font, scale, thick)
        x, y = 420, 360  # baseline origin in frame pixels
        cv2.putText(img, NAME_TEXT, (x, y + BAR_H), font, scale, (255, 255, 255), thick, cv2.LINE_AA)
        box = (x, y - h, x + w, y + base)
    ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode(), box


def grid_box_to_frame(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """PRE-A §5 for boxes: clamp, normalise corners, map to sent-image pixels, drop the bar, clamp to the frame."""
    vx1, vy1, vx2, vy2 = (min(max(v, 0), 1000) for v in box)
    vx1, vx2 = sorted((vx1, vx2))
    vy1, vy2 = sorted((vy1, vy2))

    def half_up(z: float) -> int:
        return math.floor(z + 0.5)

    x1, x2 = half_up(vx1 * IMG_W / 1000), half_up(vx2 * IMG_W / 1000)
    y1 = half_up(vy1 * (IMG_H + BAR_H) / 1000) - BAR_H
    y2 = half_up(vy2 * (IMG_H + BAR_H) / 1000) - BAR_H
    return (min(max(x1, 0), IMG_W), min(max(y1, 0), IMG_H), min(max(x2, 0), IMG_W), min(max(y2, 0), IMG_H))


async def _open_call(
    settings: Settings,
    client: MetaClient,
    frames: list[tuple[int, str]],
    *,
    effort: str,
    price: OpenWeightPrice,
    raw: list[Summary],
    max_images: int = open_weight.MAX_IMAGES,
) -> Summary:
    """One redteam.md call (the same prompt and schema WP4 uses), checked for every frame being answered."""
    messages = open_weight.redteam_messages(frames, max_images=max_images)
    body = open_weight.chat_body(settings, messages, effort=effort, max_images=max_images)
    started = time.monotonic()
    try:
        result = await open_weight.create(client, body, stage="probe_h", price=price)
    except MetaError as exc:
        return {"effort": effort, "error": f"{type(exc).__name__}: {exc}"}
    answer = cast(Mapping[str, Any], result.body)
    raw.append({"effort": effort, "frames": [n for n, _ in frames], "answer": dict(answer)})
    usage = open_weight.chat_units(answer.get("usage")) or {}
    row: Summary = {
        "effort": effort,
        "latency_s": round(time.monotonic() - started, 2),
        "finish_reason": answer.get("finish_reason"),
        "reasoning_tokens": usage.get("reasoning"),
        "output_tokens": usage.get("output"),
        "usd": result.usd,
    }
    try:
        parsed = open_weight.complete_answer(answer, [n for n, _ in frames])
    except MetaError as exc:
        row["invalid"] = str(exc)
    else:
        row["findings"] = [f.model_dump(mode="json") | {"frame": fr.frame} for fr in parsed.frames for f in fr.findings]
    return row


def _limit_holds(eight: Summary, nine: Summary) -> bool | None:
    if "error" not in nine:
        return False  # Baseten took 9 images: the documented limit doesn't hold (or was raised)
    if "error" in eight or "MetaBadRequest" not in str(nine["error"]):
        return None  # not measured: the 8-image call failed too, or 9 failed for another reason
    return True


async def probe_h(settings: Settings, client: MetaClient, out: Path) -> Summary:
    """PRE-A §3.8 probe h, on synthetic frames only:
    1. one request on 4 frames;
    2. one 8-image call and one 9-image call, to confirm Baseten's "Max images per request 8" and its error;
    3. 3 tries of the "AMINA K." grid check (passes at IoU ≥ 0.3 in 2 of 3), at SAFECUT_OPEN_WEIGHT_EFFORT;
    4. one ``omit`` (xhigh) call to compare latency and reasoning tokens.

    ``grid_ok`` is ``None`` (not measured) unless all 3 tries answered. ``image_limit_holds`` is ``True``
    when 8 images were answered and 9 were refused, ``False`` when 9 were answered, else ``None``.
    """
    price = settings.open_weight_price or BASETEN_PUBLISHED_PRICE
    four = [(i * 30, synthetic_frame(i, name=i == 2)[0]) for i in range(4)]
    name_image, true_box = synthetic_frame(2, name=True)
    if true_box is None:
        raise RuntimeError("the name frame has no text box")
    raw: list[Summary] = []
    first = await _open_call(settings, client, four, effort=settings.open_weight_effort, price=price, raw=raw)
    many = [(i * 30, synthetic_frame(i % 4, name=False)[0]) for i in range(open_weight.MAX_IMAGES + 1)]
    eight = await _open_call(
        settings, client, many[: open_weight.MAX_IMAGES], effort=settings.open_weight_effort, price=price, raw=raw
    )
    nine = await _open_call(
        settings, client, many, effort=settings.open_weight_effort, price=price, raw=raw, max_images=len(many)
    )
    tries: list[Summary] = []
    for _ in range(3):
        row = await _open_call(
            settings, client, [(60, name_image)], effort=settings.open_weight_effort, price=price, raw=raw
        )
        boxes = [f["box"] for f in row.get("findings", []) if f.get("kind") == "text" and len(f["box"]) == 4]
        best = max((_iou(list(grid_box_to_frame(tuple(b))), list(true_box)) for b in boxes), default=0.0)
        tries.append(row | {"best_iou": round(best, 3), "hit": best >= 0.3})
    omit = await _open_call(settings, client, [(60, name_image)], effort="omit", price=price, raw=raw)
    answered = [t for t in tries if "findings" in t]
    summary: Summary = {
        "model": settings.open_weight_model,
        "price_per_m": {"in": price.input, "out": price.output},
        "price_source": "SAFECUT_OPEN_WEIGHT_PRICE" if settings.open_weight_price else "baseten.co library page",
        "four_frames": first,
        "eight_images": eight,
        "nine_images": nine,
        "image_limit_holds": _limit_holds(eight, nine),
        "grid_tries": tries,
        "grid_ok": (sum(1 for t in tries if t["hit"]) >= 2) if len(answered) == 3 else None,
        "omit_effort": omit,
        "true_box": list(true_box),
    }
    if len(answered) < 3:
        summary["error"] = f"grid check not measured: {3 - len(answered)} of 3 tries failed or were invalid"
    out.mkdir(parents=True, exist_ok=True)
    (out / "baseten.answers.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n")
    return summary


# -- runner -------------------------------------------------------------------------

PROBES: dict[str, Callable[[Probe], Awaitable[Summary]]] = {
    "a": probe_a,
    "b": probe_b,
    "c": probe_c,
    "d": probe_d,
    "e": probe_e,
    "f": probe_f,
    "g": probe_g,
}


async def run(
    names: list[str],
    *,
    settings: Settings,
    out_root: Path,
    ledger: LocalLedger,
    http: httpx.AsyncClient | None = None,
    clip: Path = CLIP,
    keyframes: Path | None = None,
) -> dict[str, Summary]:
    """Run the named probes in order; a failing probe is recorded and the rest still run.

    ``clip`` (a consented hero clip) replaces the synthetic clip for the SAM (b) and speech (d) probes;
    the frame-number probes (c, e, f) always use the synthetic clip, whose burned-in counter is the truth.
    """
    caller = Caller(code_kind="owner", code_id=None, limits=(CapLimit("code", "wp0-probes", PROBE_BUDGET_USD),))
    cost_path = out_root / "cost.jsonl"
    results: dict[str, Summary] = {}
    for name in names:
        job_id = f"probe_{name}"
        out = out_root / name
        if name == "h":
            # A fresh job per run: the $0.50 baseten_job cap is per run, not accumulated across re-runs.
            run_id = f"probe_h_{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
            results[name] = await _run_h(settings, job_id=run_id, out=out, ledger=ledger, cost_path=cost_path)
            continue
        try:
            meta = MetaClient(settings, job_id=job_id, caller=caller, ledger=ledger, cost_path=cost_path, http=http)
        except Exception as exc:
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary.json").write_text(json.dumps(results[name], indent=1) + "\n")
            continue
        files = FileStore(meta, out / "job")
        probe_clip = clip if name in ("b", "d") else CLIP
        probe = Probe(
            name=name, out=out, settings=settings, meta=meta, files=files, clip=probe_clip, keyframes=keyframes
        )
        try:
            results[name] = await PROBES[name](probe)
        except Exception as exc:
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                results.setdefault(name, {})["uploads_deleted"] = await files.delete_all()
            except MetaError as exc:
                results.setdefault(name, {})["uploads_deleted"] = f"failed: {exc}"
            await meta.aclose()
        probe.save("summary.json", results[name])
    return results


async def _run_h(settings: Settings, *, job_id: str, out: Path, ledger: LocalLedger, cost_path: Path) -> Summary:
    """Probe h needs only BASETEN_API_KEY (no Meta key) and writes provider: "baseten" cost lines."""
    try:
        client = open_weight.open_weight_client(
            settings, job_id=job_id, caller=Caller(code_kind="owner"), ledger=ledger, cost_path=cost_path
        )
    except Exception as exc:
        result: Summary = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        try:
            result = await probe_h(settings, client, out)
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            await client.aclose()
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return result


def main(argv: list[str]) -> int:
    clips = [a.removeprefix("--clip=") for a in argv if a.startswith("--clip=")]
    frames = [a.removeprefix("--keyframes=") for a in argv if a.startswith("--keyframes=")]
    args = [a for a in argv if not a.startswith(("--clip=", "--keyframes="))]
    names = sorted([*PROBES, "h"]) if args in ([], ["all"]) else args
    unknown = [n for n in names if n not in PROBES and n != "h"]
    if unknown or len(clips) > 1 or len(frames) > 1:
        print("usage: probes.py [a-h ...|all] [--clip=<consented clip.mp4>] [--keyframes=<dir>]", file=sys.stderr)
        return 2
    clip = Path(clips[0]).resolve() if clips else CLIP
    if not clip.is_file():
        print(f"no such clip: {clip}", file=sys.stderr)
        return 2
    keyframes = Path(frames[0]).resolve() if frames else None
    if keyframes is not None and not (keyframes / "role_calls.json").is_file():
        print(f"no role_calls.json in {keyframes}", file=sys.stderr)
        return 2
    settings = load_settings()
    ledger_path = ROOT / "jobs" / "probes-ledger.sqlite"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    out_root = ROOT / "fixtures" / "probes" if clip == CLIP else ROOT / "jobs" / "probes-hero"
    ledger = LocalLedger(ledger_path)
    results = asyncio.run(
        run(names, settings=settings, out_root=out_root, ledger=ledger, clip=clip, keyframes=keyframes)
    )
    print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
