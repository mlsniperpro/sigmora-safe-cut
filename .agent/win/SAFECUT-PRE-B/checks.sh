#!/usr/bin/env bash
# PRE-B is docs only: no code to lint, typecheck or build. These are its tests.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
python3 - <<'PY'
import re, json, pathlib
root = pathlib.Path(".")
fails = []

def test_checklist_has_no_open_items():
    open_items = [l for l in open("docs/WIN-CHECKLIST-PRE-B.md") if l.startswith("- [ ]")]
    if open_items: fails.append(f"{len(open_items)} unchecked WIN-CHECKLIST lines")

def test_relative_links_resolve():
    files = [root/f for f in ["docs/UI-SPEC.md","docs/STORYBOARD.md","docs/PILOTS.md","docs/RULES-CHECKLIST.md","docs/BLOCKED-PRE-B.md","docs/WIN-CHECKLIST-PRE-B.md","docs/HANDOFF-PRE-B.md"]] + sorted((root/"docs/labeling").glob("*.md"))
    for f in files:
        for m in re.finditer(r"\]\(([^)\s#]+)(#[^)]*)?\)", f.read_text()):
            t = m.group(1)
            if t.startswith(("http://","https://","mailto:")): continue
            if not (f.parent / t).resolve().exists(): fails.append(f"{f}: broken link -> {t}")

def test_ui_spec_json_blocks_parse():
    s = open("docs/UI-SPEC.md").read()
    for i, m in enumerate(re.finditer(r"```json\n(.*?)```", s, re.S)):
        try: json.loads(m.group(1))
        except Exception as e: fails.append(f"UI-SPEC json block {i}: {e}")

def test_outreach_word_counts():
    s = open("docs/PILOTS.md").read()
    def count(block):
        t = re.sub(r"\{[^}]*\}", "X", block).replace(">", "")
        return len(re.findall(r"[A-Za-z0-9X][\w'’.,:;()\-–/]*", t))
    dm = s[s.index("### 3.1 DM"):s.index("### 3.2 Email")].split("\n", 1)[1]
    em = s[s.index("### 3.2 Email"):]
    em = em[:em.index("\n\n", em.index("Interested?"))]
    got = (count(dm), count(em[em.index("Hi {name}"):]))
    if got != (106, 113): fails.append(f"outreach word counts {got}, stated (106, 113)")
    if max(got) >= 120: fails.append("an outreach draft is 120 words or more")

for t in [test_checklist_has_no_open_items, test_relative_links_resolve, test_ui_spec_json_blocks_parse, test_outreach_word_counts]: t()
print("\n".join(fails) if fails else "docs tests: all pass")
raise SystemExit(1 if fails else 0)
PY
