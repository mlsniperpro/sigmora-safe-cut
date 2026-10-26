# HANDOFF (PRE-B), updated 2026-10-26 16:57 UTC

**State:** branch `pre-b-product`, PR #2 (the only PRE-B PR). Lease `.agent/win/SAFECUT-PRE-B/LEASE`: active, `session_01Tjy33tfkpth8jMhhnhhcYL` (RESUME 2026-10-26). Full hand-off: `.agent/win/SAFECUT-PRE-B/HANDOFF.md` (same facts, more detail).

**Audit position:** rounds 24–45 done (three parallel fresh auditors each; from round 39 on Sonnet/high); every finding fixed; WIN-CHECKLIST covers #1–#563 with 0 unchecked lines. Round 38 found 9 (#355–#363), round 39 found 22 (#364–#385), round 40 found 21 (#388–#408), round 41 found 34 (#416–#449), round 42 found 24 (#453–#476), round 43 found 17 (#480–#496), round 44 found 30 (#504–#533, incl. PRE-A @ 8dd5a0d), round 45 found 30 (#534–#563). **No clean round yet. Next is round 46; log findings as #564+.** The goal needs two consecutive rounds that find nothing new.

**Reconciled** with PRE-A @ `8dd5a0d` (#504–#514 incl. its open-weight decision §3.8 and audit-#43 requests); earlier `9ab5bd9` (#477–#479 its audit-#42 requests); (#409–#415 vs `02c605e`; #450–#451 vs PRE-A's audit-#36 requests at PR #2 `c944a4f`; its other open items were already fixed in #444–#446). Re-check `origin/pre-a-research` every round.

**Official guide** (owner, 2026-10-26): committed verbatim as `docs/OFFICIAL-GUIDE.md`; reconciled in RULES-CHECKLIST §0, WIN-CHECKLIST §1, BLOCKED-PRE-B and STORYBOARD 8.1/9.1 (#497–#503). Repo stays private until the owner OKs it (BLOCKED).

**Requests for other WPs (in the PR #2 body):** MAXXING (owner): §1 "Judging / finals Nov 4–8 / Nov 9" → Nov 5–8 / Nov 9; §4 "Keep the demo live to Nov 9" → live to Nov 10 23:59 UTC, demo-only from Nov 11; O7 "public at kickoff" → public before submitting, after the owner's OK (PRE-A request, OFFICIAL-GUIDE). PRE-A: its §3.8 Config bullet says probe g, while its next bullet names the Baseten probe h.

**Next:** round 46 → fix → repeat; then post the final status comment (the PR #2 body was refreshed this session; update its finding counts if more land). Remove `.agent/` before merge (#257).

**Owner rule (keep across hand-offs):** every Agent-tool subagent uses `model: "sonnet"`, `effort: "high"`; the main session verifies each finding before fixing it and keeps integration, self-review and the gate.

**Owner push rule (2026-10-25, replaces the 45-minute spacing everywhere):** push when a substantial task is complete and green (a set of audit findings fixed and checked, the gate run); never wait for a timer. Each push is a meaningful, squashed commit set (no empty, format-only or wip commits); exactly one PR. Never sit idle or end a turn to wait: while subagents run, work on the next HANDOFF item. Stop only for the API usage limit or a met /goal.
