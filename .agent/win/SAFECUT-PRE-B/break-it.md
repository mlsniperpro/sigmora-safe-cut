# Break-it record (SAFECUT-PRE-B, docs only)

PRE-B ships Markdown only: there is no code to fuzz, soak, inject failures into or run end to end, and no README run applies. What was done instead:
- Adversarial audits by fresh agents (reaudit.md), which recomputed every number by script: VO word rates, cut arithmetic, time-zone conversions, LABEL-FORMAT test vectors (M2 also run through ffmpeg), schedule hours, PILOTS word counts, mock invariants and JSON parsing.
- `checks.sh` turns the repeatable parts into tests (open checklist items, relative links, UI-SPEC JSON blocks, outreach word counts); result on this head: "docs tests: all pass".

TESTED_COMMIT: 389a572
