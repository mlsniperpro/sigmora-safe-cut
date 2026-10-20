# AGENTS.md: rules for every agent working in this repo

This repo is **Sigmora Safe Cut**, our entry to the **Meta Global AI Developer Hackathon** (Cerebral Valley, remote): Startup track, theme "Build for Your World". The event runs Oct 26 12:00 ET → **submissions due Nov 4 21:00 ET** (Nov 5 05:00 EAT). Judging criteria: Impact 30% · Use of Meta AI tooling 25% · Technical depth and execution 20% · Demo 25%. The Startup track is judged on "technical execution and whether it holds up in production".

You have access to **this repo only**. Everything you need is in `docs/`. Read in this order: `docs/MAXXING.md` → `docs/ARCHITECTURE.md` → your work package in `docs/work-packages/` → `docs/DESIGN.md` / `docs/EVAL.md` for detail.

## Hard rules

1. **No product code before Oct 26 12:00 ET (16:00 UTC).** Before then only docs are allowed in this repo. Check the time (`date -u`) before writing any code. If it's earlier, stop and report.
2. **Your work package is your scope.** Work on the branch named in your WP and touch only the paths it owns. If you need a change in another WP's paths, write it under "Requests for other WPs" in your PR description; don't make the change yourself.
3. **Data contracts are law.** The JSON files that pass between pipeline stages are defined in `docs/ARCHITECTURE.md` §3 and implemented as pydantic models in `safecut/contracts.py` (WP0). Don't change a contract without updating both, and note the change in your PR.
4. **The repo will be public**, and the event waiver says nothing submitted is confidential. Never commit keys, tokens, real footage of non-consenting people, customer data, or raw API responses for real-public clips. Consented hero clips and their API responses are allowed (fixtures).
5. **Footage handling.** Only consented clips (hero/dev from the private bucket, or the CC BY 4.0 SA-Co/VEval SmartGlasses split) may enter this sandbox. Real-public eval clips (the `test` split) never come here; the owner's machine runs those (`eval/run.py --split test`). Never download, scrape, or use third-party footage.
6. **Meta API: Standard mode only.** Use model IDs without `-contributor`, set `store: false` on Responses, and delete uploaded files after use (`DELETE /v1/files/{id}`). Read the key from `MODEL_API_KEY` (the env var Meta's docs use). Never print it.
7. **No geo-circumvention.** Meta's Geographic Use Policy forbids bypassing its geographic controls. Kenya isn't restricted, so calls go direct. Never add proxying to "work around" availability.
8. **Model IDs come from env, never hard-coded in logic** (see ARCHITECTURE.md §4). Defaults live in `safecut/config.py`.
9. **Honest numbers only.** Every metric in the README, submission or video must come from a committed `eval/results/<run-id>/metrics.json`. Never invent, round up, or extrapolate.
10. **Budget.** Total Meta credits are $150 for the whole event. The pipeline logs cost per call (`cost.jsonl`). Stay under the per-WP budget in your WP. Use fixtures and replay mode for tests; live calls are only for probes and marked integration tests (`pytest -m live`).
11. **Tooling.** Python 3.12 with `uv` (never pip directly), `ruff`, `pytest` (+ `hypothesis` for pure logic). Web: Node 24, `pnpm` (never npm or yarn). ffmpeg comes from `imageio-ffmpeg` so it works without a system install.
12. **Done means tested.** `uv run pytest` and `uv run ruff check` pass, and the web app passes `pnpm lint && pnpm typecheck && pnpm test`. Don't run a production build of the web app locally; Vercel builds it on push. Your PR description lists what you verified, what you couldn't (and why), and every live-call cost.
13. **If you're blocked** (a missing key, a gated download, an API that behaves differently from the docs), write `BLOCKED.md` on your branch with exactly what you need, finish everything else you can, and stop. Don't fake a result.

## Commit style

Conventional commits (`feat(scout): …`, `test(policy): …`). Small commits. End each commit message with the attribution line your harness gives you.
