"""receipt: the job's files → ``receipt.json`` + ``receipt.html`` (WP4 step 3).

``run(job_dir)`` seals the receipt. When the job already has one (a re-render after review), the new receipt
chains from it (``prev_hash``) and the old one is kept as ``receipts/<hash>.json``, so the job's history verifies
end to end with :func:`verify_chain`. ``python -m safecut.receipt verify <receipt.json>…`` checks a chain. No API
call: ``replay`` changes nothing.
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


def run(job_dir: Path, *, replay: bool = False, settings: Settings | None = None) -> Path:
    """Write ``receipt.json`` and ``receipt.html``; return the JSON's path."""
    del replay  # no API call in this stage
    settings = settings or load_settings()
    previous = load(job_dir / RECEIPT, Receipt) if (job_dir / RECEIPT).exists() else None
    if previous is not None:
        dump(previous, job_dir / HISTORY / f"{previous.hash}.json")
    receipt = build(job_dir, settings, prev_hash=previous.hash if previous is not None else None)
    path = dump(receipt, job_dir / RECEIPT)
    (job_dir / RECEIPT_HTML).write_text(render_html(receipt, job_dir), encoding="utf-8")
    return path


def history(job_dir: Path) -> list[Receipt]:
    """The job's receipts, oldest first (the archived ones by their chain, then the current one)."""
    current = load(job_dir / RECEIPT, Receipt)
    archived = {r.hash: r for r in (load(p, Receipt) for p in sorted((job_dir / HISTORY).glob("*.json")))}
    chain = [current]
    while chain[0].prev_hash is not None and chain[0].prev_hash in archived:
        chain.insert(0, archived[chain[0].prev_hash])
    return chain


__all__ = ["RECEIPT", "RECEIPT_HTML", "ReceiptError", "build", "history", "run", "verify_chain"]
