"""receipt: the job's files → ``receipt.json`` + ``receipt.html`` (WP4 step 3).

``run(job_dir)`` seals the receipt. When the job already has one (a re-render after review), the new receipt chains
from it (``prev_hash``) and the old one is kept as ``receipts/<hash>.json``, so the job's history verifies end to
end with :func:`verify_chain`. The render stage retires the old receipt first (:func:`retire`), so a job whose
re-render or re-audit fails never shows the previous video's verdict. ``python -m safecut.receipt verify
<receipt.json>…`` checks a chain. No API call: ``replay`` changes nothing.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from safecut.config import Settings, load_settings
from safecut.contracts import ContractError, Receipt, dump, load, validate_job_dir
from safecut.receipt.build import ReceiptError, build, verify_chain
from safecut.receipt.html import render_html
from safecut.render import write_atomic

RECEIPT = "receipt.json"
RECEIPT_HTML = "receipt.html"
HISTORY = "receipts"
#: The hash of the last receipt :func:`retire` archived (``receipts/HEAD``), which the next receipt chains from.
HEAD = "HEAD"


def run(job_dir: Path, *, replay: bool = False, settings: Settings | None = None) -> Path:
    """Write ``receipt.json`` and ``receipt.html``; return the JSON's path."""
    del replay  # no API call in this stage
    settings = settings or load_settings()
    current = load(job_dir / RECEIPT, Receipt) if (job_dir / RECEIPT).exists() else None  # tampered: raises
    previous = current or _retired(job_dir)
    receipt = build(job_dir, settings, prev_hash=previous.hash if previous is not None else None)
    try:
        # The executable contract gates publishing (ARCHITECTURE §3): a receipt only stands on a job directory that
        # validates as a whole. It is checked before it is put in place, so no reader ever sees one that fails.
        _validate_with(job_dir, receipt)
    except ContractError as exc:
        raise ReceiptError(f"the job directory doesn't validate, so no receipt: {exc}") from exc
    retire(job_dir)
    path = dump(receipt, job_dir / RECEIPT)
    (job_dir / RECEIPT_HTML).write_text(render_html(receipt, job_dir), encoding="utf-8")
    return path


def _validate_with(job_dir: Path, receipt: Receipt) -> None:
    """``validate_job_dir`` on the job as it would be with ``receipt`` in place: a shadow directory of the same name
    whose entries link to the job's, plus the new receipt."""
    with tempfile.TemporaryDirectory() as tmp:
        shadow = Path(tmp) / Path(os.path.abspath(job_dir)).name  # "." has no name of its own
        shadow.mkdir()
        for entry in job_dir.iterdir():
            if entry.name not in (RECEIPT, RECEIPT_HTML):
                (shadow / entry.name).symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
        dump(receipt, shadow / RECEIPT)
        validate_job_dir(shadow)


def retire(job_dir: Path) -> Receipt | None:
    """Archive the current receipt as ``receipts/<hash>.json`` and take it (and its page) out of the job, so a new
    render never sits beside the old video's sealed verdict; the next receipt chains from it. A tampered receipt
    raises (``ContractError``), never archived."""
    path = job_dir / RECEIPT
    if not path.exists():
        return None
    previous = load(path, Receipt)
    dump(previous, job_dir / HISTORY / f"{previous.hash}.json")
    write_atomic(job_dir / HISTORY / HEAD, previous.hash)
    path.unlink()
    (job_dir / RECEIPT_HTML).unlink(missing_ok=True)
    return previous


def _retired(job_dir: Path) -> Receipt | None:
    """The last receipt :func:`retire` archived, if the job has none in place."""
    head = job_dir / HISTORY / HEAD
    if not head.exists():
        return None
    return load(job_dir / HISTORY / f"{head.read_text(encoding='utf-8').strip()}.json", Receipt)


def history(job_dir: Path) -> list[Receipt]:
    """The job's receipts, oldest first (the archived ones by their chain, then the current one)."""
    current = load(job_dir / RECEIPT, Receipt)
    archived = {r.hash: r for r in (load(p, Receipt) for p in sorted((job_dir / HISTORY).glob("*.json")))}
    chain = [current]
    while chain[0].prev_hash is not None and chain[0].prev_hash in archived:
        chain.insert(0, archived[chain[0].prev_hash])
    return chain


__all__ = ["RECEIPT", "RECEIPT_HTML", "ReceiptError", "build", "history", "retire", "run", "verify_chain"]
