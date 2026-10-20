# WP7: evaluation harness, baselines, results

**Branch** `wp7-eval` · **Wave** B · **Starts** after WP0 merges · **Depends on** WP0 contracts; it runs the real pipeline once WP1–WP4 merge · **Budget** ≤ $12 on dev and hero data in the sandbox (test-split runs happen on the owner's Mac)

**Owns:** `eval/` (harness, metrics, baselines, `LABELING-GUIDE.md`, `results/`), `tests/test_metrics*.py`.

## Goal

Every number in the submission is earned and reproducible (EVAL.md). One headline table: **entity recall, exposure rate, leak bursts and over-blur**, across the baselines and the full system, plus review load, creator time and cost.

## Steps

1. **Labels:** a loader for the EVAL.md §1 label JSON and MOT box files; a validator; `eval/LABELING-GUIDE.md` (from EVAL.md §1/§6, plus the edge cases); a split freezer that writes `eval/splits/test.sha256` from the clip list + labels.
2. **Metrics (`eval/metrics.py`), pure and unit-tested:**
   - **Coverage per GT box per frame:** the share of GT box area under the rendered redaction regions, computed from `plan.json` (+ audit patches) exactly as the renderer applies them.
   - Entity recall: an entity counts as hidden when ≥95% of its visible frames are covered.
   - Exposure rate: the share of entity-frames <90% covered.
   - Leak bursts: runs of ≥3 consecutive exposed frames.
   - Over-blur: should-keep entities hidden for >10% of their frames.
   - Review load: needs-you items per minute.
   - Cost: from `cost.jsonl`.
3. **Baselines (EVAL.md §3), each as a pipeline variant:**
   - `blur_all`: SAM `face`, everything hidden.
   - `egoblur`: EgoBlur Gen 2 on every frame (reuse WP4's detector wrapper).
   - `detector_only`: SAM class prompts, no Muse reasoning, all screens hidden.
   - `muse_no_track`: Muse keyframe boxes held between keyframes.
   - `full`.
   - `no_audit`.
4. **Runner:** `eval/run.py --split dev|test|hero|public --variant <v> [--replay]`.
   - It writes `eval/results/<run-id>/` with `metrics.json`, `per_clip.csv`, `cost.json`, `config.json` (model IDs, git SHA, split hash) and the worst-5 exposures (frames saved **only for consented clips**).
   - For the `test` split (real-public clips), it writes metrics only and stores nothing visual. Refuse to run `test` if `eval/splits/test.sha256` doesn't match.
   - It caps itself at 3 test runs (counter file).
5. **Public split:** the SA-Co/VEval SmartGlasses (CC BY 4.0) loader, for tracking and leak-guard numbers (no role labels). Report it as supplementary.
6. **Report:** `eval/report.py` builds `eval/RESULTS.md` (the tables, with each number linking to its run ID) and charts (PNG, consistent colours) for the README and video.

## Tests

Metric unit tests on hand-made cases (full cover, partial cover, a 2-frame vs 3-frame leak, over-blur thresholds), plus a determinism test (same inputs → same metrics).

## Done when

- [ ] All metrics are implemented and tested, and the baselines run on the hero/dev data in the sandbox (replay where possible). A dev run is committed with its run ID.
- [ ] `eval/run.py --split test` works on the owner's Mac, documented step by step in `eval/README.md` (Claude runs it locally).
- [ ] `RESULTS.md` is generated from committed runs only.
