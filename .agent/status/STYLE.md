# Lane STYLE status (2026-11-04)

- **Commits on main:** `5706839` feat(guard): hide identity, not the shot; bounded holds; kept faces stay clear (the squashed lane commit), then `cfe11d1` fix(render): face mosaic keeps no facial structure; 4 cells across. That is two commits, not one: the fresh-clone entry check on `5706839` failed E3 (below), and main's history isn't rewritten.
- **Deploy runs:** `5706839`: https://github.com/mlsniperpro/sigmora-safe-cut/actions/runs/41864783672 green on every step (release checks, image smoke, deploy, the replay job end to end on the deployed app with EgoBlur on the GPU, live URL check), 20m55s. `cfe11d1`: https://github.com/mlsniperpro/sigmora-safe-cut/actions/runs/41873513453 green on every step (release checks, image smoke, deploy, the replay job end to end with EgoBlur on the GPU, live URL check, including the cold-start check). `/healthz` after it: `status: ok`, `uptime_s: 97.7` at 17:32Z.
- **Live:** `GET https://aladroslab--safecut-api.modal.run/healthz` at 16:38Z → `status: ok`, `uptime_s: 24.7` (the fresh deploy; healthz carries no commit field). https://safecut.sigmora.org → HTTP 200.
- **Eval:** six dev-split replay runs at `7f81aa9` (the metrics score plan geometry, which `cfe11d1` doesn't change) (this change before the squash, kept on `lane/style-wip`); figures unchanged; `eval/report.py --check` green; RESULTS.md has a Changes note.

## What changed

1. **Identity-only covers (DESIGN §2.7).** A hidden, held or Needs-you person and every child get the coarse locked-grid mosaic over the face only. Where no face is planned, the body track draws a head estimate (top of the body box, full width × min(0.22·h, 0.9·w), face-padded), in the item's grid or solid with no face track. `person_solid` is only the creator's Remove person. `PROMINENT_HEIGHT` and the close-up rule are gone. Children stay locked hidden.
2. **Bounded held covers (DESIGN §2.6, addenda 1+2).** No motion sweep. The back-fill is half a second (`ceil(0.5 × fps)`), with the first box held still and grown ≤ 10 %. Extend and gap holds grow ≤ 25 %, and a gap holds the interpolated box. A held cover stays under 4× its edge box's padded area (hypothesis test).
3. **Kept faces stay clear.** `PlanEntry.keep_clear` lists the kept participants' padded faces that an entry overlaps; render, `hidden_mask`, eval coverage and the web preview subtract them. Never on a child's cover or an audit patch. Decision: a hidden face's own box is never uncovered for it (the audit would only patch it back over both); only padding, bodies and objects give way.
4. **Contract checker and ARCHITECTURE §3.7:** head estimates off face frames, `backfill == ceil(0.5 × fps)`, and `keep_clear` validated.
5. **Web preview:** mosaics are drawn in the mask's shape, `keep_clear` is cut out, the draw order matches the render, and locally hidden people get the face mosaic or a head estimate (whole body only for Remove person).

## Street-interview job (j_bOnehM8xFcyRxZXQ0X6gmg; fixture `tests/fixtures/live_street_2026_11_04.json`)

Covered share of the frame, live plan (bounding boxes) vs. this commit's plan on the same tracks:

| | max | median | mean | frames > 25 % |
|---|---|---|---|---|
| before | 96.8 % | 62.3 % | 59.8 % | 353 / 361 |
| after | 21.9 % | 7.5 % | 9.6 % | 0 / 361 |

Frame 105: 81.7 % → 7.6 %. Frame 210: 94.9 % → 2.8 %. Frame 285: 94.2 % → 20.7 %.

## Verified

- ruff, ruff format, pyright: clean. Web: `pnpm lint`, `pnpm typecheck`, `pnpm test` (921 passed).
- Offline pytest: the full run on this tree before the squash showed only failures that I fixed (or that came from a venv change mid-run); I re-ran each affected file green. The deploy job's offline suite passed on `5706839`.
- New tests: `tests/test_style_identity.py` (15), including a check that YuNet sees no face under the mosaic at its real cell size.
- Faked clock: at 2026-11-05T02:00Z the only failures were `test_api` access-code/service-key, which assumed the judge window was shut. They now pin the access clock (passing at today's time, 11-05 02:00Z and +7 d). The other two failures under the fake clock (`test_scale_to_zero`) come from the clock-faking harness (extra PYTHONPATH, `uv --with`); they pass on the real clock. +7 d: the same two harness failures only.
- `bash scripts/entry-check.sh` on a fresh clone of origin/main: see below.

## Entry check (`bash scripts/entry-check.sh`, fresh clone)

- `5706839`: E1, E2 and E4–E12 OK; **E3 FAIL**: "e3: still legible in redacted.mp4 on 252/269 visible frames (+1 more: e4)". E3 checks pixels: each should-hide truth box must lose ≥ 75 % of its content contrast and correlate < 0.5 with the source. The 6-cell mosaic, with each cell keeping its own mean, kept the face's coarse light and dark (contrast ratio 0.70, correlation about 0.6). Measured alternatives: 3 or 2 cells with per-cell means still failed (264 and 236 frames).
- Fix (`cfe11d1`): every cell is the face region's mean colour plus fixed per-cell noise (±24), with 4 cells across (coarser than the 6 allowed, never finer). E3 alone: OK (3 failing frames at 6 cells; 0 at 4). Targeted suites (guard, audit loop/opinion/gpu, receipt, audit24, demo job, metrics): 451 passed. Web: 921 passed.
- `cfe11d1` full run: E1–E12 all OK: **ENTRY: PASS** (entry-check 2026-11-04T16:56:09Z at `cfe11d1`, a fresh clone of the commit pushed to main).

## Open (owner, 11-04 after 17:00Z; being worked on now)

- The audit patches kept faces at the clip ends (café j_nHnMijG4M64lroDQadni-w, street j_iK6xyjgwe5qE_6ixbN67uA).
- The street job's child is uncovered at about 3.5–7.5 s, and patches are scattered after about 8 s.

## Follow-ups pushed after the lane (owner requests, 11-04 evening)

- `9bf9b22` (after `b9a330f`/`f3ca863`): kept faces excused by the audit within 1 s of SAM's box, children covered whole, covers follow the live box, frosted look, web preview fix for cross-origin video. Deploy green, fresh-clone ENTRY: PASS.
- `02e9199`: a kept face always wins (all covers, audit patches too), per-frame audit patches held ±0.3 s, patches over 6 % of the frame left as review spots, 0.3 s back-fill, scene-coloured frosted look. Full suite 1670 passed; deploy run 41909723984 in progress at 20:46Z.
- Not done: camera-motion compensation for the 2 s gap hold, realigning misaligned covers, auto-keep conversation partner / auto-merge re-entries.
- `0f7a9f6`: any tie to the conversation keeps an adult clear (the interviewer, the guest and their re-entries kept with no human action; children never; strangers hidden). Deploy run 41927059206 started 22:38Z.
- `lane/motion` (91ff183, merged as 1748e2d): held boxes follow the camera's pan. Pushed to main only after its fresh-clone entry check passes.
- The brief's "one squashed commit" was not met: the lane reached main as 5706839 + cfe11d1 (and follow-ups); main's history is not rewritten.
