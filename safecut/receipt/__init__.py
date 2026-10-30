"""receipt: the job's files → ``receipt.json`` + ``receipt.html`` (WP4 step 3).

``run(job_dir)`` seals the receipt. When the job already has one (a re-render after review), the new receipt chains
from it (``prev_hash``) and the old one is kept as ``receipts/<hash>.json``, so the job's history verifies end to
end with :func:`verify_chain`. The render stage retires the old receipt first (:func:`retire`), so a job whose
re-render or re-audit fails never shows the previous video's verdict. ``python -m safecut.receipt verify
<receipt.json>…`` checks a chain. No API call: ``replay`` changes nothing.
"""

from __future__ import annotations

from pathlib import Path

from safecut.config import Settings, load_settings
from safecut.contracts import Receipt, dump, load
from safecut.receipt.build import ReceiptError, build, verify_chain
from safecut.receipt.html import render_html

RECEIPT = "receipt.json"
RECEIPT_HTML = "receipt.html"
HISTORY = "receipts"
#: The hash of the last receipt :func:`retire` archived (``receipts/HEAD``), which the next receipt chains from.
HEAD = "HEAD"


def run(job_dir: Path, *, replay: bool = False, settings: Settings | None = None) -> Path:
    """Write ``receipt.json`` and ``receipt.html``; return the JSON's path."""
    del replay  # no API call in this stage
    settings = settings or load_settings()
    previous = retire(job_dir) or _retired(job_dir)
    receipt = build(job_dir, settings, prev_hash=previous.hash if previous is not None else None)
    path = dump(receipt, job_dir / RECEIPT)
    (job_dir / RECEIPT_HTML).write_text(render_html(receipt, job_dir), encoding="utf-8")
    return path


def retire(job_dir: Path) -> Receipt | None:
    """Archive the current receipt as ``receipts/<hash>.json`` and take it (and its page) out of the job, so a new
    render never sits beside the old video's sealed verdict; the next receipt chains from it. A tampered receipt
    raises (``ContractError``), never archived."""
    path = job_dir / RECEIPT
    if not path.exists():
        return None
    previous = load(path, Receipt)
    dump(previous, job_dir / HISTORY / f"{previous.hash}.json")
    (job_dir / HISTORY / HEAD).write_text(previous.hash, encoding="utf-8")
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
