# The closed loop, on one traced job

Safe Cut runs as a loop of perception, reasoning, policy, action and verification, with the creator as the final authority. This page walks one job through it, using the files it wrote.

> **Synthetic trace.** The job is the demo clip `fixtures/clips/SC-A-91-synthetic-20261030.mp4` (drawn shapes on a market set) replayed from `fixtures/jobs/demo/raw/`. Every "model" answer below was generated from the clip's ground truth by `scripts/make_demo_job.py`, not returned by SAM 3.1, Muse Spark or Voice Transcribe. It shows what each stage receives and decides; it is not evidence of model quality. The same commands on a consented hero clip with `MODEL_API_KEY` set record real responses (`scripts/go-live.sh`), and this page is then regenerated from those.

Reproduce it with:

```bash
uv run safecut run fixtures/clips/SC-A-91-synthetic-20261030.mp4 --out "$(mktemp -d)/demo" --replay --auto-approve-policy
```

## 1. Perceive: SAM 3.1 tracks every candidate (`tracks.json`)

One SAM 3.1 request per concept (face, person, license plate, screen, phone, document, name badge), plus the miss loop's sweep, gives fifteen tracks:

- `face:1`–`face:4` and `person:1`–`person:4`;
- `license plate:1`;
- `screen:1`;
- `envelope:1` (added later by the miss loop, step 3);
- `face:5` and `person:5`: the passer-by coming back into frame after leaving it (`reentry_of: face:2` / `person:2`);
- `face:6` and `person:6`: Kev, the guest, walking out of frame on the right and back in from the left (`reentry_of: face:3` / `person:3`).

SAM gives a returning person new IDs and the `reentry_of` link is kept as a hint only. A person who is lost and found again is a **new** track, and starts hidden, even the guest.

## 2. Listen and read the scene: Voice Transcribe, then Muse Spark (`transcript.json`, `scene.json`)

Voice Transcribe returns diarized turns, among them:
- S1: "Hi, I'm Amina, welcome back to the channel."
- S1: "Today I'm at the market with my friend Kev."
- S2: "Hey everyone, great to be here!"

The scene pass sees the whole clip with that transcript and names two participants:
- the woman in the orange top (speaker S1, introduction "I'm Amina");
- the man in the green top who joins from the right (S2, introduced as "my friend Kev").

## 3. Decide who is who: three independent votes on numbered keyframes (`roles.json`)

The role pass sends Muse Spark Set-of-Mark keyframes: frames with each track's box and label drawn on them. It does this three times, independently:

| Track | Votes | Result |
|---|---|---|
| `face:1` (Amina) | participant, participant, participant | participant: "introduces herself as Amina (S1) and talks to camera" |
| `face:3` (Kev) | participant ×3 | participant: "introduced by the host as her friend Kev; he answers her (S2)" |
| `face:2` (passer-by) | bystander ×3 | bystander: "walks past in the background; nobody addresses them" |
| `face:4` | child, bystander, bystander | **child**: one child vote is enough |
| `face:5` (the passer-by, back) | bystander, unsure, bystander | **unsure**, so it is escalated once at maximum effort; the ruling suggests bystander |
| `face:6` (Kev, back) | participant, unsure, participant | **unsure**, escalated; the ruling suggests participant |

The objects get a content check:
- `screen:1` is "a wall screen showing an email inbox with names" (sensitive);
- `license plate:1` is a parked car's plate.

The **miss loop** asks what SAM didn't track. It proposes "an addressed envelope on the table" with the phrase `envelope`, and a new SAM sweep turns that phrase into `envelope:1`.

## 4. Apply the policy: deny by default (`decisions.json`)

The policy (`safecut/decide/policy.py`, 100 % branch-covered and property-tested) only ever moves a track *out* of hidden. Grouping joins each face and person track into one item:

| Item | Decision | Decided by | Why |
|---|---|---|---|
| Amina (`face:1`, `person:1`) | keep | model | three participant votes, speech evidence (S1), consistent across keyframes |
| Kev (`face:3`, `person:3`) | keep | model | the same, with S2 |
| Passer-by (`face:2`, `person:2`) | hide, whole-person cover | model | bystander |
| Child (`face:4`, `person:4`) | hide, **locked** | model | a child; the creator can't keep it clear |
| Passer-by again (`face:5`, `person:5`) | **needs you** (renders hidden) | policy | "checks didn't all agree; a closer look suggests bystander" |
| Kev again (`face:6`, `person:6`) | **needs you** (renders hidden) | policy | "checks didn't all agree; a closer look suggests participant" |
| Inbox screen | hide, solid | model | sensitive screen |
| Plate | hide, solid | policy | plates are always hidden |
| Envelope | hide, solid | model | sensitive document |

The leak guard (`plan.json`) then pads every hidden box, back-fills before a track's first detection, extends past its last one, and holds the box through short gaps, so nothing flickers into view at a track's edges.

## 5. The creator decides (`review.json`, `approval.json`)

The review panel shows these items in three columns: hidden, kept clear and needs you. Each item has a Why drawer with the keyframe, the votes and the reason. Each tap is one edit sent to `POST /v1/jobs/{id}/review`. WP3's `apply_review` folds it over the policy's decisions, and the guard re-plans. Edits are idempotent by `edit_id`, and Undo is an edit of its own.

What the creator can't do: keep the child clear, keep an audit patch clear, or merge anything into a non-participant. The approval pins the decisions it approved (`decisions_sha256`, over every item but the audit's own locked patches), so a later edit needs a new approval. In the review panel the creator would tap **Same as…** to merge Kev's returning track into Kev. In this trace, `--auto-approve-policy` stands in for the creator and accepts the policy as it is, so both needs-you items stay hidden: the passer-by, and Kev for the few frames after he walks back in.

## 6. Act, then verify the action: render and audit (`redacted.mp4`, `audit.json`)

The render draws the plan, with solid covers, locked-grid pixelation, or whole-person masks. Then the audit checks the *output*:
- the every-frame detector looks for any face still visible (here YuNet, because EgoBlur's gated weights aren't installed; all 360 frames were scanned);
- the Muse Spark red team looks at frames sampled once a second.

Any leak becomes an audit patch (a new hidden item, locked, labelled `A1`…), and the affected frames are rendered again. Publishing is refused while `unresolved > 0`. This trace's audit found no leak: the drawn faces aren't real faces to YuNet, and the synthetic red team found none.

## 7. Prove it: the privacy receipt (`receipt.json`, `receipt.html`)

The receipt lists every item:
- what was decided, by whom and why;
- the audit's counts;
- which model did which job;
- how data was handled (Standard mode, `store: false`, uploads deleted);
- the cost.

It is sealed with `sha256(prev_hash + canonical JSON)`, and `validate_job_dir` re-derives every field from the job's own files, so a receipt that disagrees with its job fails validation.
