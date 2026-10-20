# WP2: speech + scout (scene pass, Set-of-Mark role pass, escalation, miss loop)

**Branch** `wp2-scout` · **Wave** B · **Starts** after WP0 merges · **Depends on** WP0 (and WP1's `tracks.json` shape, available from fixtures) · **Budget** ≤ $15

**Owns:** `safecut/speech/`, `safecut/scout/`, `safecut/meta/schemas/` (JSON schemas for structured output), `tests/test_speech*.py`, `tests/test_scout*.py`, `fixtures/muse/*`, `fixtures/asr/*` (additions), and the CLI subcommands `transcribe`, `scene` and `roles`.

## Goal

Produce `transcript.json`, `scene.json` and `roles.json` (ARCHITECTURE.md §3.3–3.5): who is part of the story, who isn't, which screens and documents are personal, and what SAM missed, with evidence tied to **frame numbers**, never free-text times.

## Steps

1. **Speech (`speech/`):**
   - Muse Voice Transcribe on the prepared clip's audio (extract with ffmpeg) → diarized turns with timestamps.
   - Fallback when `SAFECUT_SPEECH_SOURCE=spark-1.2`: ask Muse Spark 1.2 for a speaker-attributed transcript.
   - Map turn times to frame ranges with `job.times`.
2. **Scene pass (`scout/scene.py`):**
   - Send the whole clip (video input) to `SAFECUT_SCENE_MODEL`, together with the transcript. Ask who the host is, who is introduced or interviewed (with the transcript turn as evidence), and what's happening, plus candidate sensitive objects.
   - Use structured output (`text.format` json_schema, `strict: true`) and `store: false`.
   - This pass sets context only; its times aren't trusted.
3. **Set-of-Mark keyframes (`scout/som.py`):**
   - At 1 fps, draw every track's box from `tracks.json` with its **track number** in a high-contrast label, and burn the **frame number** in a corner. Write `som/<frame>.jpg`.
   - Keep labels legible at small sizes (test at 320 px).
   - Unit-test the drawing deterministically: pixel checks on the synthetic clip.
4. **Role pass (`scout/roles.py`):**
   - Send ≤50 SoM keyframes per call, plus the scene context and the transcript, to `SAFECUT_ROLE_MODEL`. Use the schema in ARCHITECTURE.md §3.5.
   - **Run it 3× independently.** A track is a participant only with 3/3 votes; any disagreement → `unsure`.
   - Disputed tracks get one escalation call to `SAFECUT_ESCALATE_MODEL` at `reasoning.effort: "max"`.
   - Children are flagged as `child` whenever any vote says child.
   - Screens and documents: `sensitive` + a `content` description, so the context test works (inbox hidden, menu clear).
5. **Miss loop:** for each `missed` item, call WP1's `track.sweep` with `sam_phrase` (max 2 loops, max 3 new phrases per loop). Bind returned tracks to the point using the WP3 binding helper, or a local nearest-box helper if WP3 hasn't merged yet; note it in the PR. Add the new tracks to `tracks.json` and re-run the role pass for them only.
6. **Points:** clamp to the 0–1000 grid and map them to the exact image size sent (DESIGN §2.3).
7. **CLI + replay:** `safecut transcribe|scene|roles --job … [--replay]`; all raw responses are saved under `jobs/<id>/raw/`.

## Tests

Schema validation on every fixture response. Self-consistency logic as pure functions with hypothesis tests (vote combinations → roles). A `-m live` test on hero clip 1: the guest and host are participants, and the passing child is a child.

## Done when

- [ ] `transcribe` → `scene` → `roles` run in replay from fixtures and produce valid contracts.
- [ ] The live run on hero clip 1 gets the role calls right (list each one in the PR), with the cost recorded.
- [ ] The PR includes 3 SoM keyframe images from the consented hero clip, and the prompt texts are in `safecut/scout/prompts/` (versioned).
