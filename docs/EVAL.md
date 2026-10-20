> Imported unchanged from `sigmora-platform/docs/meta-hackathon/EVAL.md` on 2026-10-20 (pre-event design). Where file paths or the Oct 14 model choices differ, [ARCHITECTURE.md](ARCHITECTURE.md) and [MAXXING.md](MAXXING.md) take precedence: this repo is standalone, and it adds Muse Voice Transcribe and an optional Muse Wonder escalation.

# Safe Cut: evaluation plan

We claim one thing: **Safe Cut hides what shouldn't be published and keeps what should, more reliably and faster than the tools creators have today.** This doc defines how we measure that so every number in the submission is earned. No public video dataset labels participants vs bystanders, so the labelled set is itself a contribution.

## 1. Entities and labels

Every person or object a reviewer would discuss is an **entity**. Label each one once per clip:

```json
{
  "clip": "SC-A-01-cbd-20261018.mp4",
  "fps": 30, "frames": 1260, "width": 1920, "height": 1080,
  "split": "dev | test | hero",
  "entities": [
    {
      "id": "e1",
      "category": "participant | bystander | child | plate | screen | document | address | photo | other",
      "should_hide": true,
      "reason": "walks past behind the guest, never addresses camera",
      "difficulty": ["small", "occluded", "reentry", "motion_blur", "crowd"],
      "frames": { "first": 120, "last": 410 },
      "boxes": "tracks/SC-A-01/e1.mot.txt"
    }
  ],
  "notes": "harmless menu screen at 00:12 should stay CLEAR"
}
```

- `should_hide` is the ground truth, decided by **two labellers independently**. Disagreements are logged and resolved, and **inter-rater agreement is reported** (Cohen's κ on `should_hide`). That's our ceiling: published human agreement on bystander judgements is 80–93% (Hasan et al., IEEE S&P 2020).
- Screens are labelled by content: a PII screen is `should_hide: true`, a menu or map is `false`. This is the context test the incumbents fail.
- **Boxes**: track boxes (head or face for people; the full object for plates, screens and documents) in **MOT format** (`frame,id,x,y,w,h,1,-1,-1,-1`), keyed at 2 fps and interpolated, then checked by eye at fast motion.
- **Tool**: CVAT (free; video track annotation with interpolation; exports MOT). Run it via Docker on a build box rather than the Intel dev Mac. Never upload the real-public clips to a hosted labelling service.

**Splits:** `dev` (about 12 clips, tune prompts freely), `test` (about 18 clips, touched only for reported runs, max 3 runs), `hero` (the staged demo clips, reported separately).

## 2. Metrics

Primary (privacy) metrics:

| Metric | Definition | Why |
|---|---|---|
| **Entity recall** (should_hide) | share of should_hide entities hidden for at least 95% of their visible frames | did we catch the person or object at all |
| **Exposure rate** | share of should_hide entity-frames where less than 90% of the GT box area is covered by a redaction | a face visible for even a few frames identifies them |
| **Leak bursts** | count of runs of ≥3 consecutive exposed frames on any should_hide entity (≥0.1 s at 30 fps) | what a viewer can actually catch; target **0** on hero clips |

Secondary (usability) metrics:

| Metric | Definition |
|---|---|
| **Over-blur rate** | share of `should_hide: false` entities (participants, harmless screens) hidden for more than 10% of their frames |
| **Review load** | number of items the creator must decide ("needs you" chips) per minute of footage |
| **Creator time** | wall-clock from upload to approved render, vs manual masking of the same clip in an editor (timed once, on 3 clips) |
| **Cost** | Meta API dollars per minute of footage (SAM frames plus Muse Spark tokens) |

Supplementary public check (tracking and leak guard only, no role labels): SA-Co/VEval **SmartGlasses** split (CC BY 4.0, egocentric). Don't use the CC BY-NC splits or PP4AV (NC-ND) in anything published.

Coverage uses box area, not IoU, because a redaction larger than the face is correct (the padding is deliberate). It's computed per frame from our rendered redaction keyframes, interpolated exactly as the renderer does (`packages/shared/src/composition-redact.ts`).

## 3. Baselines (same clips, same metrics)

1. **Blur every face**: what YouTube Studio's "blur all faces" and CapCut Face Mosaic do. Implemented as SAM 3.1 prompt `"face"` with everything hidden. Expect high recall and terrible over-blur (the guest is gone).
1b. **EgoBlur Gen 2** (Meta's own open face and plate blurrer, run on every frame): the strongest "blur everything" baseline, and a Meta reference judges will recognise.
2. **Detector-only Safe Cut**: SAM 3.1 class prompts (`face`, `license plate`, `screen`) with no Muse Spark reasoning. Expect plate and screen recall but no participant/bystander split, and all screens hidden, menu included.
3. **Muse Spark without tracking**: Muse Spark's per-keyframe boxes held between keyframes. Expect leaks on motion; shows why SAM is needed.
4. **Safe Cut, full**: scout, track, bind, blur-by-default, audit.
5. *(Optional)* **Safe Cut without the audit pass**: isolates what the second-look loop adds.

The headline is one table: **recall, exposure, leak bursts and over-blur across the 5 rows**, plus a 10-second side-by-side clip of row 1 vs row 4.

## 4. Protocol

- All runs are scripted (`eval/run.ts --split test --variant full`) and write `eval/results/<run-id>/` with the raw API responses, the redaction keyframes, the metrics JSON and a cost receipt. Every number in the README links to a run ID.
- The test split is frozen before the first full run (a hash of the clip list plus labels is committed).
- Report failures honestly: list the worst 5 exposures with clip, time and cause (with frames shown only from consented clips).

## 5. Budget

$150 in Meta credits. A test pass is about 18 clips × 30 s at 8 fps × 4 prompts × $0.0002 ≈ **$3.50 of SAM** plus Muse Spark tokens (TBD on day 1; video tokens are not documented). Keep **3 full test runs** and about 10 dev iterations under $60, leaving room for demo renders and retries.

## 6. Labelling schedule

- **Oct 20–21:** label the dev split; settle the guide (edge cases: a person who looks at the camera but doesn't speak; a shop worker in the background; reflections).
- **Oct 22–23:** label the test split (2 labellers), compute κ, resolve disagreements.
- **Oct 24:** freeze the test split (hash), back it up privately, write `eval/LABELING-GUIDE.md`.
