"""``receipt.html``: the receipt as one self-contained page (inline CSS, thumbnails embedded), for the creator to keep
or show if a privacy complaint arrives (DESIGN §2.9). It renders only what ``receipt.json`` holds, escaped; the
red-team's private text never reaches the receipt (``redteam.md`` "Private text")."""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

from safecut.contracts import Receipt, ReceiptItem

_STYLE = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1c2028;--muted:#5d6470;--line:#e2e4e8;--ok:#1d7a46;--warn:#a4570c;--bad:#b42318;
--chip:#eef0f3}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--card:#1a1d24;--ink:#e8eaee;--muted:#a1a8b3;--line:#2c313b;
--ok:#4cc38a;--warn:#f0a95a;--bad:#ff7b6b;--chip:#252a33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,
"Segoe UI",Roboto,sans-serif}main{max-width:980px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.verdict{display:flex;gap:12px;align-items:center;margin:16px 0}.badge{font-weight:600;padding:4px 10px;
border-radius:999px;background:var(--chip)}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}.stat b{display:block;
font-size:22px}.items{display:grid;gap:10px}.item{display:grid;grid-template-columns:120px 1fr;gap:14px}
.item img{width:120px;height:90px;object-fit:cover;border-radius:8px;background:var(--chip)}.noimg{width:120px;
height:90px;border-radius:8px;background:var(--chip)}.chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0}
.chip{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--chip)}table{width:100%;
border-collapse:collapse}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);
vertical-align:top}code{font:12px/1.4 ui-monospace,Menlo,monospace;word-break:break-all}
@media (max-width:560px){.item{grid-template-columns:1fr}.item img,.noimg{width:100%;height:160px}}
"""

_DECISION = {"hide": "Hidden", "keep": "Kept clear", "needs_you": "Hidden (creator to decide)"}
_STYLE_NAMES = {"solid": "solid block", "pixelate": "coarse mosaic (≤ 6 blocks, locked grid)",
                "person_solid": "whole-person block"}  # fmt: skip
_BY = {"policy": "the policy", "model": "Muse Spark's checks", "creator": "the creator"}


def _thumb(job_dir: Path, item: ReceiptItem) -> str:
    if item.thumbnail is None or not (job_dir / item.thumbnail).is_file():
        return '<div class="noimg" aria-hidden="true"></div>'
    data = base64.b64encode((job_dir / item.thumbnail).read_bytes()).decode("ascii")
    return (
        f'<img alt="{escape(item.item_id)} as it appears in the published video" src="data:image/jpeg;base64,{data}">'
    )


def _item(job_dir: Path, item: ReceiptItem) -> str:
    label = item.audit_label or item.item_id
    chips = [_DECISION[item.decision], item.kind]
    if item.style is not None:
        chips.append(_STYLE_NAMES[item.style])
    if item.locked:
        chips.append("locked")
    if item.removed_by_creator:
        chips.append("removed at the creator's request")
    frames = ", ".join(str(f) for f in item.evidence_frames[:12]) or "—"
    tracks = ", ".join(item.track_ids) or "audit patch"
    chip_html = "".join(f'<span class="chip">{escape(c)}</span>' for c in chips)
    return (
        f'<div class="card item">{_thumb(job_dir, item)}<div><b>{escape(label)}</b>'
        f'<div class="chips">{chip_html}</div><div>{escape(item.reason)}</div>'
        f'<div class="muted">Decided by {escape(_BY[item.decided_by])} · evidence frames {escape(frames)} · '
        f"tracks {escape(tracks)}</div></div></div>"
    )


def render_html(receipt: Receipt, job_dir: Path) -> str:
    a, d = receipt.audit, receipt.data_handling
    publishable = a.unresolved == 0
    verdict = (
        '<span class="badge ok">Audit passed</span>'
        "<span>Every output frame was checked; nothing is left exposed.</span>"
        if publishable
        else f'<span class="badge bad">Publishing blocked</span><span>{a.unresolved} unresolved'
        f" ({escape(a.blocked_reason or 'unresolved')}).</span>"
    )
    hidden = sum(i.decision != "keep" for i in receipt.items)
    kept = sum(i.decision == "keep" for i in receipt.items)
    stats = [
        ("hidden", hidden), ("kept clear", kept), ("frames audited", a.frames_scanned),
        ("leaks found", a.leaks_found), ("leaks patched", a.leaks_patched), ("audit passes", a.passes),
    ]  # fmt: skip
    stat_html = "".join(
        f'<div class="card stat"><b>{v}</b><span class="muted">{escape(k)}</span></div>' for k, v in stats
    )
    models = "".join(f"<tr><td>{escape(stage)}</td><td><code>{escape(m)}</code></td></tr>"
                     for stage, m in sorted(receipt.models.items()))  # fmt: skip
    stores = "".join(f"<tr><td><code>{escape(m)}</code></td><td>store: {str(v).lower()}</td></tr>"
                     for m, v in sorted(d.store_by_model.items()))  # fmt: skip
    stores += "".join(f"<tr><td><code>{escape(m)}</code></td><td>takes no store parameter</td></tr>"
                      for m in d.no_store_param)  # fmt: skip
    notes = "".join(f"<li>{escape(n)}</li>" for n in d.notes)
    items = "".join(_item(job_dir, item) for item in receipt.items)
    cost = f"${receipt.cost_usd:.4f}"
    if receipt.cost_usd_estimated:
        cost += f" (+ up to ${receipt.cost_usd_estimated:.4f} unconfirmed)"
    if receipt.cost_usd_baseten:
        cost += f"; Baseten ${receipt.cost_usd_baseten:.4f}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy receipt · {escape(receipt.job_id)}</title><style>{_STYLE}</style></head>
<body><main>
<h1>Privacy receipt</h1>
<div class="muted">Sigmora Safe Cut · job <code>{escape(receipt.job_id)}</code> · approved by the creator at
{escape(receipt.approved_at.isoformat())}</div>
<div class="verdict">{verdict}</div>
<div class="stats">{stat_html}</div>
<h2>What was hidden, what was kept, and why</h2>
<div class="items">{items}</div>
<h2>The audit</h2>
<div class="card">Auditor <code>{escape(a.auditor)}</code> scanned {a.frames_scanned} frames of the rendered video,
and a red team was asked to read or identify anything on sampled frames. {a.leaks_found} leak(s) found,
{a.leaks_patched} patched, {a.unresolved} unresolved, in {a.passes} pass(es).</div>
<h2>Models</h2>
<div class="card"><table><tbody>{models}</tbody></table></div>
<h2>Data handling</h2>
<div class="card"><table><tbody><tr><td>Mode</td><td>{escape(d.mode)} (never Contributor)</td></tr>{stores}
<tr><td>Uploaded files</td><td>{"deleted" if d.files_deleted else "not all deleted yet"}</td></tr>
<tr><td>SAM responses</td><td>deletion requested for {d.responses_delete_requested},
pending {d.responses_delete_pending}</td></tr>
<tr><td>Cost</td><td>{escape(cost)}</td></tr></tbody></table>{f"<ul>{notes}</ul>" if notes else ""}</div>
<h2>Seal</h2>
<div class="card"><div>hash <code>{escape(receipt.hash)}</code></div>
<div>previous <code>{escape(receipt.prev_hash or "none (first in its chain)")}</code></div>
<p class="muted">hash = sha256(previous hash + canonical JSON of receipt.json without its hash). Changing any
field breaks it: <code>uv run python -m safecut.receipt verify receipt.json</code></p></div>
</main></body></html>
"""
