# WP3: decide (binding + policy) and leak guard

**Branch** `wp3-decide` · **Wave** B · **Starts** after WP0 merges · **Depends on** WP0 contracts only · **Budget** $0 (no API calls)

**Owns:** `safecut/decide/`, `safecut/guard/`, `tests/test_policy*.py`, `tests/test_binding*.py`, `tests/test_guard*.py`, and the CLI subcommands `decide` and `guard`.

## Goal

Pure, exhaustively tested logic that turns `tracks.json` + `roles.json` into `decisions.json` (deny by default), then `plan.json` (where the redaction goes on every frame, padded in space and time so nothing leaks at track edges). This is the safety core, so correctness beats cleverness.

## Steps

1. **Binding (`decide/bind.py`):** map a point (from the role pass or the miss loop) to a track on a frame. A point inside the track's mask dilated by 10% → match. Otherwise the nearest box within 0.1 × the frame diagonal. Vote across keyframes, with a Hungarian assignment for conflicts; ties → no binding (`unsure`).
2. **Grouping:** group a person's `face:*` and `person:*` tracks into one review **item** when their boxes overlap consistently (face box inside the person box on ≥80% of shared frames).
3. **Policy (`decide/policy.py`), straight from DESIGN §2.5:**
   - The default is `hide` for every track of every sensitive concept.
   - `keep` only if the role is participant with 3/3 votes, AND it's not a child, AND it's consistent on ≥2 keyframes, AND (when a transcript exists) the participant has speech or an introduction as evidence.
   - Children: `hide`, `locked: true`.
   - New IDs mid-clip: `hide` until the creator merges them into a participant.
   - Screens and documents: `hide` unless the content is non-personal (menu, map, slide); then `needs_you`, never auto-`keep`.
   - Prominent bystanders (box height > 25% of the frame) get the `person_solid` style (whole-person mask) — the Reddit finding in DESIGN §2.7b.
   - Styles: text, screens, plates and documents → `solid`; faces → `pixelate` (locked grid, ≤6 blocks across the face, plus noise) or `solid`.
   - Every item has a human-readable `reason`.
4. **Creator overrides:** `apply_review(decisions, edits)` lets the creator toggle hide/keep (except locked items), merge a new ID into a participant, or "remove person". It returns new decisions with `decided_by: creator`, without re-tracking.
5. **Leak guard (`guard/plan.py`), straight from DESIGN §2.6:**
   - Spatial padding: faces 15% + 8 px; others 8% + 8 px.
   - Temporal: extend ±8 frames, **back-fill 15 frames before the first detection**, hold the last box through gaps ≤2 s while growing it 2% per frame.
   - Crowd fallback: fill the crowded region on `crowded_frames`.
   - Lock the pixelation grid to the item's first box, so cells don't shift.
   - Output `plan.json`.
6. **CLI:** `safecut decide --job …` and `safecut guard --job …`.

## Tests (the bar is high here)

Use hypothesis property tests:
- Nothing with role ≠ participant is ever `keep`.
- Children are never `keep`, even after creator edits.
- Every frame a hidden track is visible on has a plan region covering its padded box.
- The back-fill covers the 15 frames before first detection, and gap hold covers ≤2 s gaps.
- Locked grids never move.

Also table tests for every rule above, a golden test on WP0/WP1 fixtures, and 100% branch coverage on `policy.py` (`pytest --cov`).

## Done when

- [ ] All properties and rules are tested; coverage report in the PR.
- [ ] `decide` + `guard` run on the fixture job and produce valid contracts.
- [ ] The PR has a table: rule → test name.
