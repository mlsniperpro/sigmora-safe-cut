# Safe Cut: what "done" means for the whole entry (owner-set, 2026-10-30)

Wave A (WP0 foundation, WP6 web on mocks) and the PRE-A/PRE-B docs are merged. **Nothing between the upload and the redacted video exists yet.** Three cloud sessions now build the rest in parallel lanes and are not finished until the whole entry passes the checks below. A lane that finishes its own scope early takes the next failing E-line in its area.

Deadline: submissions close **2026-11-05 02:00 UTC** (Nov 4, 9 PM ET). We submit a day early.

## Lanes

| Tag | Scope (work packages) | Owns |
|---|---|---|
| `SAFECUT-SENSE` | WP1 prepare + SAM 3.1 tracking, WP2 speech + scout (scene, Set-of-Mark, role pass ×3, escalation, miss loop), the live-recording path | `safecut/prepare.py`, `safecut/track/`, `safecut/meta/` (extensions), `safecut/speech/`, `safecut/scout/`, `fixtures/{sam,muse,asr}/`, `scripts/go-live.sh` |
| `SAFECUT-SAFETY` | WP3 bind + policy + leak guard, WP4 render + EgoBlur audit + red-team + auto-patch + privacy receipt | `safecut/decide/`, `safecut/guard/`, `safecut/render/`, `safecut/audit/`, `safecut/receipt/` |
| `SAFECUT-SHIP` | WP5 pipeline + API + Modal + demo mode, the web app on the real API, WP7 eval, WP8 submission package, `scripts/entry-check.sh`, integration of all lanes | `safecut/pipeline.py`, `safecut/api/`, `safecut/cli.py`, `deploy/`, `.github/`, `web/`, `eval/`, `scripts/entry-check.sh`, `README.md`, `docs/SUBMISSION.md`, `docs/VIDEO-SCRIPT.md`, `docs/AGENTIC-LOOP.md`, `docs/LAUNCH.md`, `BLOCKED.md` |

Each stage package exposes `run(job_dir: Path, *, replay: bool = False) -> Path` (returns the contract file it wrote) and registers its CLI subcommand through the registry in `safecut/cli.py`. SHIP lands that registry plus stage stubs on main within its first two hours. Until then a lane calls its own `run()` from tests. Shared files (`pyproject.toml`, `uv.lock`, `safecut/contracts.py`, `safecut/config.py`) take small additive edits only. On a `uv.lock` conflict, merge `pyproject.toml` by hand and regenerate the lock with `uv lock`.

## Integration through main

- Work on your lane branch (`lane-sense`, `lane-safety`, `lane-ship`). If the sandbox only lets you push `claude/…` branches, use that and say so in the PR.
- When a slice is green, do all of the following:
  1. `git fetch origin && git rebase origin/main`.
  2. Run the **full repo suite** (E1 below), not just your lane.
  3. Merge into `main` with a merge commit (`git checkout main && git merge --no-ff <lane> && git push origin main`). Never force-push `main`.
  4. Continue on your branch from the new `main`.
- Push to `main` at most 3 times an hour per lane. Merge real slices only: no WIP, no format-only commits.
- Keep exactly one PR per lane open (lane branch → main) as the running log: Decisions, Self-review, evidence, gate line.
- If `main` is red, the lane that broke it fixes it before anything else. SHIP watches `main` after every merge and repairs integration breakage.

## E-lines: the entry is done only when `bash scripts/entry-check.sh` prints every line OK and then `ENTRY: PASS`

SHIP writes `scripts/entry-check.sh` first. It prints one `E<n>: OK` or `E<n>: FAIL <reason>` line per check, then `ENTRY: PASS` or `ENTRY: FAIL (<n>)`. **Checks may be added or made stricter, never removed or weakened.** The owner reviews every diff to this script.

- **E1 Full suite, fresh clone.** `uv sync --all-groups`, `uv run pytest -q` (everything except `-m live`), `uv run ruff check`, `uv run ruff format --check` and the repo's pyright config all pass. In `web/`: `pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm test`.
- **E2 Every stage, replay.** `safecut prepare|track|transcribe|scene|roles|decide|guard|render|audit|receipt --job <dir> --replay` each writes its §3 contract file, and that file validates against `safecut.contracts`.
- **E3 End to end, offline.** `uv run safecut run <demo clip> --out <tmp> --replay --auto-approve-policy` runs with the network blocked. It produces:
  - `redacted.mp4`: H.264, with an audio stream when the source has one;
  - `audit.json` with `unresolved == 0`;
  - `receipt.json` whose hash chain verifies, plus `receipt.html`.

  Scored against the clip's ground truth: every should-hide object is ≥95% covered on ≥99% of its visible frames; no should-keep object is hidden on more than 10% of its frames; zero leak bursts (≥3 consecutive exposed frames).
- **E4 Safety core.** The WP3 property tests run with ≥2000 hypothesis examples each:
  - non-participants are never kept;
  - children are never kept, even after creator edits;
  - every visible frame of a hidden track is covered by its padded box;
  - back-fill and gap-hold hold;
  - locked grids never move.

  Plus 100% branch coverage on `safecut/decide/policy.py`, and an injected 3-frame leak that the audit finds and patches.
- **E5 API.** A TestClient flow in replay: create → upload → start → poll → items → review → render → result → delete. Plus tests for:
  - both auth paths (judge access code, Sigmora service key);
  - the per-IP rate limit and the daily USD cap;
  - upload limits (60 s, 150 MB) and CORS;
  - the 24 h deletion job and `/healthz`.
- **E6 Web on the real API.** A Playwright run against a locally started API in replay. It covers the labelled replay demo job, upload → review (keep/hide toggle, merge a new ID, remove person, a locked child that can't be kept) → render → result + receipt. Axe must report zero serious or critical violations. `MockBackend` only appears in unit tests.
- **E7 Deploy-ready.** Both deploy paths and a smoke test exist:
  - `deploy/modal_app.py`: the ASGI app, a worker, a Volume and the 24 h deletion cron.
  - `.github/workflows/deploy.yml`: skips with a notice when its secrets are missing.
  - The web app's Vercel settings, documented in `web/README.md`.
  - `scripts/deploy-check.sh <api-url> <web-url>`.

  Deployed, with URLs in the README, once the secrets exist; until then a `BLOCKED.md` line.
- **E8 Live-ready.** Every Meta call has a `pytest -m live` test: Files, SAM 3.1, Muse Spark (scene, role, escalate, red-team), Voice Transcribe, and the open-weight path. `scripts/go-live.sh <clip>` records a full job's raw responses into `fixtures/jobs/<id>/raw/` in one command, under a USD cap. Without `MODEL_API_KEY` it exits 2 with a one-line message naming the missing input.
- **E9 Eval.** `eval/run.py --split hero|dev|public --variant blur_all|egoblur|detector_only|muse_no_track|full|no_audit [--replay]` runs. At least one committed run per variant exists. `eval/RESULTS.md` is generated from committed runs only, and the WP7 metric unit tests pass.
- **E10 Submission package.** All of these exist:
  - `README.md` (WP8 list, including "What each Meta model does here" and "What existed before Oct 26");
  - `docs/SUBMISSION.md`;
  - `docs/VIDEO-SCRIPT.md` (≤ 3:00);
  - `docs/AGENTIC-LOOP.md`;
  - `docs/LAUNCH.md`.

  Every number traces to a committed `metrics.json` or run ID; the script checks that each number it finds in them appears in `eval/RESULTS.md`.
- **E11 Hygiene.** No secrets in history or tree (a pattern scan for key and token shapes). No TODO/FIXME/XXX in shipped code. No skipped tests other than `-m live` without a key. The README's fresh-clone steps actually run.
- **E12 Owner list.** Root `BLOCKED.md` lists every owner input as a checklist with exact steps. It merges the per-lane lists and drops anything already done.

## Schedule (UTC)

| By | What |
|---|---|
| Oct 30 15:00 | SHIP: CLI registry, stage stubs, `entry-check.sh` (failing honestly), on main |
| Oct 31 18:00 | SENSE and SAFETY: every stage runs in replay on the synthetic demo job and is merged. SHIP: `safecut run --replay` end to end on real stages (E2, E3) |
| Nov 1 18:00 | E4–E7 green; the web app on the real API |
| Nov 2 18:00 | E8 and E9 green; the live path proven the moment the key exists; audit rounds |
| **Nov 3 12:00** | **Feature freeze.** After this: fixes, tests, polish only |
| Nov 3 18:00 | E10–E12 green: `ENTRY: PASS` on main |
| Nov 4 02:00 | Owner submits (a day early) |
| Nov 4 18:00 | Sessions stop |

## Owner inputs (no lane may wait on these; build behind replay and list them)

- `MODEL_API_KEY` in the cloud environment, with `api.meta.ai` allowed.
- Hero footage with releases (`docs/SHOTLIST.md`).
- Modal tokens.
- The `safecut.sigmora.org` domain and the Vercel project.
- Making the repo public.
- EgoBlur weights, if gated.
- `BASETEN_API_KEY` for the open-weight bonus.
- The voice-over, and the submit click.

Until the key and footage arrive, the demo job is the synthetic clip in `fixtures/clips/`, with replay responses generated from its `truth.json`. These are labelled synthetic wherever they appear and are never presented as real model output.
