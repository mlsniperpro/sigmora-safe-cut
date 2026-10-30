# SAFECUT-SHIP win checklist

Every E-line SHIP owns, every brief requirement, and the judging criteria, each with its evidence. `- [x]` done,
`- [P]` waits on an owner input (root `BLOCKED.md`), `- [-]` not applicable, `- [ ]` open.

## Brief order (`.agent/briefs/SAFECUT-SHIP.md`)

- [x] `scripts/entry-check.sh`: one line per E-line, `ENTRY: PASS` only on a full run with every line OK once; bounded (`ENTRY_TIMEOUT`), E3 offline in a network namespace. Test: `tests/test_entry_check.py` (refuses PASS on any failure, a missing line, a duplicate, a partial run).
- [x] `safecut/cli.py` registry + stage resolution (`safecut/stages.py`): `safecut run|<stage>|approve|publish|validate`; an unmerged stage exits 3 naming its lane. Merged to main 56d3d1b within the first two hours.
- [x] `safecut/pipeline.py`: idempotent, resumable stages (`job_log.jsonl` digests), the USD cap before each paid stage, zero network in replay (`safecut/netguard.py`), stop for review, then publish. `tests/test_pipeline.py`.
- [x] API (E5): every UI-SPEC §8 route, both auth paths, per-IP and paid-action limits, caps, upload limits, CORS, the 24 h deletion, `/healthz`, demo replay with `mode: "replay"` and `synthetic`. `tests/test_api.py`, entry-check E5 OK.
- [ ] Web on the real API (E6): `pnpm e2e:api` passes 61/63; the merge of a new ID needs a participant re-entry in the demo job (requested from SENSE).
- [x] WP6 handoff: `web/README.md` written (local API, e2e, Vercel table); MockBackend only in `web/src/test/`.
- [x] Deploy-ready (E7): `deploy/modal_app.py`, `.github/workflows/deploy.yml` (skips with a notice), `scripts/deploy-check.sh` tested against a local API (`tests/test_deploy.py`).
- [P] Deployed with URLs in the README: needs the Modal tokens, the Modal secret and the Vercel project (BLOCKED.md).
- [ ] Eval (E9): five of six variants committed (`eval/results/`); `muse_no_track` waits on the scout lane's `muse_keyframe_boxes` hook.
- [x] Eval harness: labels + MOT loader and validator, pure metrics (`tests/test_metrics.py`), the test-split freeze, hash check and 3-run cap (`tests/test_metrics_harness.py`), `eval/report.py --check`.
- [P] SA-Co/VEval SmartGlasses public split: the official `facebook/SACo-VEval` dataset is gated on Hugging Face (manual terms acceptance; the ungated mirrors aren't Meta's, so they're not used, AGENTS rule 5), and running it needs `MODEL_API_KEY` (live SAM): both in BLOCKED.md.
- [ ] Submission package (E10): README, SUBMISSION, VIDEO-SCRIPT, AGENTIC-LOOP, LAUNCH (after the code E-lines, per the owner's priority).
- [x] E11 hygiene: entry-check E11 OK (history and tree secret scan, no markers, no skips, the README fresh-clone block runs).
- [x] E12 owner list: root `BLOCKED.md` merges every lane's inputs with exact steps.

## Findings closed

- [x] `/review` ran the guard on the event loop (async handler): now sync, in the threadpool.
- [x] The review toast vanished before a slow ack, taking its Undo: the 6 s now count from the ack; `JobPage.test.tsx` "a slow server" fails before the fix.
- [x] A replay job inside a live API would block live Meta calls: the stage guard is thread-local; hero jobs build in a child process.
- [x] The egoblur baseline was labelled EgoBlur while YuNet ran: the run records its detector and the report names it.
- [x] The replay network guard leaked between tests: autouse reset in `tests/conftest.py`.
- [x] Guard re-plan cost (3.9 s per review edit on the demo clip): reported to SAFETY with a profile; fixed on main in 51a67bb.

## Judging criteria

- [ ] Impact (30): real numbers need the key and footage; synthetic runs only so far, labelled synthetic.
- [ ] Meta tooling (25): README "What each Meta model does here" (E10).
- [ ] Demo (25): the landing replays the demo job; the video script (E10).
- [x] Technical depth (20): contracts across every stage, resumable pipeline, signed URLs, caps, audit and receipt, an offline end-to-end check (E3 OK).
