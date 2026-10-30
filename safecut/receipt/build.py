"""``receipt.json`` (ARCHITECTURE §3.9, DESIGN §2.9): what was hidden and why, who approved it, what the audit
proved, which models ran and how the data was handled, sealed in a hash chain.

Everything is read back from the job's own files, so the receipt can only say what they record: the models are
the ones the scene, roles, transcript and audit files name (plus every Meta model ``cost.jsonl`` billed), the store
settings are what the client sends (``store: false`` on every Responses call; SAM without it only when
``responses.json`` shows it), the costs are ``cost.jsonl``'s measured totals, and ``files_deleted`` is
``files.json``'s. A synthetic job says so in ``data_handling.notes``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from safecut.config import Settings
from safecut.contracts import (
    Approval,
    Audit,
    DataHandling,
    Decisions,
    FilesIndex,
    Job,
    Receipt,
    ReceiptAudit,
    ReceiptBody,
    ReceiptItem,
    ResponsesIndex,
    Roles,
    Scene,
    Tracks,
    Transcript,
    load,
    measured_usd,
    read_cost_lines,
    receipt_hash,
)

RUN = Path("raw/audit/run.json")
APPROVAL = "approval.json"
#: A synthetic job says so: a ``synthetic.json`` marker (SENSE's synthetic demo job) or the red-team oracle's truth.
SYNTHETIC_MARKER = "synthetic.json"
SYNTHETIC_TRUTH = Path("raw/redteam/synthetic_truth.json")
SYNTHETIC_NOTE = "Synthetic job: every model answer was replayed from synthetic data; no model was called."
BASETEN_NOTE = (
    "Sampled output frames (already redacted) went to Muse Spark Open on Baseten for a second opinion: this job was"
    " consented, and Baseten's terms, not Meta's store setting, govern that copy."
)
YUNET_NOTE = "Audited with YuNet (faces only): EgoBlur weights weren't installed; the red team checked plates."
AUTO_APPROVE_NOTE = "Approved without review: the policy's decisions were accepted as they stood (auto-approve)."
AUDIO_NOTE = "The audio is kept as recorded: Safe Cut redacts the picture only, so anything said aloud stays audible."


def is_synthetic(job_dir: Path) -> bool:
    """A job replayed from synthetic answers: SENSE's demo recording (``raw/manifest.json`` ``synthetic: true``), a
    ``synthetic.json`` marker, or the red-team oracle's truth file."""
    manifest = job_dir / "raw" / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")).get("synthetic") is True:
        return True
    return (job_dir / SYNTHETIC_MARKER).exists() or (job_dir / SYNTHETIC_TRUTH).exists()


class ReceiptError(ValueError):
    """The job can't be receipted yet (no audit, no decisions)."""


def models_ran(job_dir: Path, settings: Settings, audit: Audit) -> dict[str, str]:
    """The model behind each stage that ran, from the files that recorded it (AGENTS rule 9)."""
    out: dict[str, str] = {}
    scene = load(job_dir / "scene.json", Scene) if (job_dir / "scene.json").exists() else None
    roles = load(job_dir / "roles.json", Roles) if (job_dir / "roles.json").exists() else None
    transcript = load(job_dir / "transcript.json", Transcript) if (job_dir / "transcript.json").exists() else None
    tracks = load(job_dir / "tracks.json", Tracks) if (job_dir / "tracks.json").exists() else None
    if scene is not None and scene.model is not None:
        out["scene"] = scene.model
    if roles is not None and roles.model is not None:
        out["roles"] = roles.model
        if roles.status == "ok" and any(t.escalated for t in roles.tracks):
            out["escalate"] = settings.escalate_model
    if tracks is not None and any(t.source for t in tracks.tracks):
        out["sam"] = next(t.source for t in tracks.tracks if t.source)
    if transcript is not None and transcript.source is not None:
        out["speech_fallback" if transcript.source_kind == "fallback" else "asr"] = transcript.source
    run = job_dir / RUN
    redteam = json.loads(run.read_text(encoding="utf-8")).get("redteam_model") if run.exists() else None
    if isinstance(redteam, str):
        out["redteam"] = redteam
    if audit.open_weight.status != "off" and audit.open_weight.model is not None:
        out["open_weight"] = audit.open_weight.model
    out["auditor"] = audit.egoblur.model
    cost = job_dir / "cost.jsonl"
    if cost.exists():
        named = set(out.values())
        for line in read_cost_lines(cost):
            model = line.model
            if model is None or model in named or line.provider != "meta" or line.stage.startswith("budget:"):
                continue
            if line.usd > 0 or line.estimated:  # billed (a call refused before processing ran nothing)
                out[line.stage] = model
                named.add(model)
    return out


def data_handling(job_dir: Path, models: dict[str, str], audit: Audit) -> DataHandling:
    """Standard mode; ``store: false`` on every Responses model; Voice Transcribe takes no store parameter; SAM is
    sent ``store: false`` unless ``responses.json`` shows it couldn't be (then its deletion is requested)."""
    responses = load(job_dir / "responses.json", ResponsesIndex) if (job_dir / "responses.json").exists() else None
    files = load(job_dir / "files.json", FilesIndex) if (job_dir / "files.json").exists() else None
    unstored_sam = responses is not None and bool(responses.root)
    asr, sam = models.get("asr"), models.get("sam")
    opinion = models.get("open_weight")
    no_store = sorted({m for m in (asr, opinion, sam if unstored_sam else None) if m is not None})
    store_by_model = {m: False for stage, m in models.items() if stage != "auditor" and m not in no_store}
    notes: list[str] = []
    billed = (job_dir / "cost.jsonl").exists() and any(
        line.usd > 0 or line.estimated for line in read_cost_lines(job_dir / "cost.jsonl")
    )
    if is_synthetic(job_dir) and not billed:  # a job any model was paid for isn't "no model was called"
        notes.append(SYNTHETIC_NOTE)
    if opinion is not None:
        notes.append(BASETEN_NOTE)
    if audit.egoblur.model == "yunet-face":
        notes.append(YUNET_NOTE)
    approval = job_dir / APPROVAL
    if approval.exists() and load(approval, Approval).how == "auto_policy":
        notes.append(AUTO_APPROVE_NOTE)
    if load(job_dir / "job.json", Job).audio:
        notes.append(AUDIO_NOTE)
    if responses is not None and responses.pending:
        notes.append(f"{len(responses.pending)} SAM response(s) still awaiting deletion at Meta.")
    return DataHandling(
        mode="standard",
        store=any(store_by_model.values()),
        store_by_model=store_by_model,
        no_store_param=no_store,
        files_deleted=files.all_deleted if files is not None else True,
        responses_delete_requested=responses.requested if responses is not None else 0,
        responses_delete_pending=len(responses.pending) if responses is not None else 0,
        notes=notes,
    )


def build(
    job_dir: Path, settings: Settings, *, prev_hash: str | None = None, approved_at: datetime | None = None
) -> Receipt:
    """Seal the receipt for ``job_dir``."""
    if not (job_dir / "audit.json").exists() or not (job_dir / "decisions.json").exists():
        raise ReceiptError("a receipt needs decisions.json and audit.json (run decide … audit first)")
    job = load(job_dir / "job.json", Job)
    decisions = load(job_dir / "decisions.json", Decisions)
    audit = load(job_dir / "audit.json", Audit)
    items = [
        ReceiptItem.model_validate(
            {**item.model_dump(), "thumbnail": f"thumbs/{item.item_id}.jpg"}
            if (job_dir / "thumbs" / f"{item.item_id}.jpg").exists()
            else item.model_dump()
        )
        for item in decisions.items
    ]
    models = models_ran(job_dir, settings, audit)
    lines = list(read_cost_lines(job_dir / "cost.jsonl")) if (job_dir / "cost.jsonl").exists() else []
    meta, meta_estimated = measured_usd(lines, provider="meta")
    baseten, _ = measured_usd(lines, provider="baseten")
    if approved_at is None:
        # The receipt says the creator approved: only an approval on record (the pipeline's approval.json) says so.
        if not (job_dir / APPROVAL).exists():
            raise ReceiptError("no approval.json: the creator hasn't approved this plan (review it, or auto-approve)")
        approved_at = datetime.fromisoformat(json.loads((job_dir / APPROVAL).read_text())["approved_at"])
    body = ReceiptBody(
        job_id=job.job_id,
        items=items,
        audit=ReceiptAudit(
            auditor=audit.egoblur.model,
            frames_scanned=audit.frames_scanned,
            leaks_found=len(audit.leaks),
            leaks_patched=sum(leak.patched_item is not None for leak in audit.leaks),
            unresolved=audit.unresolved,
            passes=audit.passes,
            blocked_reason=audit.blocked_reason,
        ),
        models=models,
        data_handling=data_handling(job_dir, models, audit),
        approved_by="creator",
        approved_at=approved_at,
        cost_usd=meta,
        cost_usd_estimated=meta_estimated,
        cost_usd_baseten=baseten,
        prev_hash=prev_hash,
    )
    return Receipt.seal(body)


def verify_chain(receipts: Sequence[Receipt]) -> bool:
    """Every receipt's hash is ``sha256(prev_hash + canonical_json(body))`` and each links to the one before it
    (the first may start anywhere: a project's chain can begin before this job)."""
    for i, receipt in enumerate(receipts):
        if receipt.hash != receipt_hash(receipt):
            return False
        if i and receipt.prev_hash != receipts[i - 1].hash:
            return False
    return True
