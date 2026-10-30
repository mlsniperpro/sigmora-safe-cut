# Rules for every Safe Cut lane session (owner-set, 2026-10-30)

These rules apply on top of your lane brief. Where `AGENTS.md`, `docs/MAXXING.md` or a work package says otherwise, these rules win. That covers these lines:
- "touch only your paths": replaced by the lane ownership table in `.agent/ENTRY-DONE.md`;
- "write BLOCKED.md and stop";
- "never push to main";
- any line that tells you to ask the owner or wait.

## Start

1. Run `date -u`.
2. `git fetch --all --prune` and branch from the latest `origin/main`.
3. Read these, in order:
   - `AGENTS.md`;
   - `.agent/ENTRY-DONE.md`;
   - your lane brief;
   - `docs/ARCHITECTURE.md`;
   - the work packages your lane covers (`docs/work-packages/`);
   - `docs/API-NOTES.md`, `docs/prompts/` (PRE-A) and `docs/UI-SPEC.md` (PRE-B), where your lane touches them;
   - `docs/DESIGN.md` and `docs/EVAL.md` for detail.
4. Read the Wave A handoffs (`.agent/win/SAFECUT-WP0/HANDOFF.md`, `.agent/win/SAFECUT-WP6/HANDOFF.md`) and reuse what WP0 built in `safecut/meta/`. Don't rebuild it.

## Win mandate

Your goal is to WIN this competition. "Finished" is not enough. The brief is the floor, not the ceiling.

**Order of work.** Code first: close every code gap and get the code itself to winning quality before docs, submission text or video prep.

**Owner inputs.** Credentials, accounts and footage come later. Wire each one behind a stub or replay fixture, list it in your lane's BLOCKED file, and prove the path works the moment the input arrives.

**Work continuously until the deadline, and never idle-wait on anyone.** Every round:
1. Audit the whole entry, across every lane's merged work, as a strict judge and a hostile senior reviewer would.
2. Close gaps in order of score impact (Impact 30, Meta tooling 25, Demo 25, Technical depth 20).
3. Test hard:
   - the full suite;
   - high-count property tests;
   - fuzz, soak and failure-injection runs in the background;
   - the replay end-to-end path;
   - a fresh-clone README run, done the way a judge would do it.
4. Fix root causes. Never weaken a test, a check or a threshold.
5. Re-audit and repeat.

When everything is green, raise the bar against past winners and the strongest competitors.

**Check-ins.** Schedule your own check-ins every 60–90 minutes so the loop survives across turns, and resume after a usage limit.

## Decision rule

Never ask questions and never wait for answers. When something is ambiguous, decide it yourself by these principles:
1. What moves the needle: a better product for its users and a stronger entry in front of the judges.
2. A clearer, less confusing user experience.
3. Proven engineering best practice.
4. Safe is cheap: when two options are close, take the reversible, lower-risk one.

Research before deciding (official docs, primary sources, how the best products handle it), then decide and keep building. Record each non-trivial call in your PR's Decisions section: what you chose, what you rejected, why, and the sources.

The only things you can't decide are those that physically need the owner: secrets, sign-ups, spending money, messages to real people, filming, and making the repo public. Build those paths behind replay, list the exact input needed as a checklist, and carry on.

## Quality bar (cut scope by the work packages' own priorities, never quality)

1. **State of the art.** Before locking in a technique, check the official docs for the exact library and API versions you use, plus recent primary sources. Record the choice, with links, in the PR.
2. **Tests:**
   - unit tests for every pure function;
   - hypothesis tests where inputs vary;
   - integration tests at every stage boundary;
   - an end-to-end replay test;
   - failure paths: timeouts, bad or empty input, rate limits, partial results.

   No skipped or flaky tests.
3. **Robustness.** Schema-validate every external input. Use typed errors. Every network call gets a timeout, bounded retries with backoff, and idempotency. No silent fallbacks. Secrets come only from env.
4. **Scale.** No avoidable quadratic work. Stream large media. Bound memory and concurrency. Cap paid calls per job and per day. State in the PR where it would break first.
5. **Code quality.** Strict typing (the repo's pyright config; TS strict). Lint clean. Small modules. No dead code or TODOs. Match the existing conventions.
6. **Self-review before every merge.** Read your diff as a strict senior reviewer would. Run the code-review or simplify skill if the session has one.
7. **Honest evidence.** Every claim in the PR comes from a command you ran, with its output. Say plainly what isn't done or verified. Synthetic replay data is always labelled synthetic.

## Subagents

Every Agent/Task launch sets model `sonnet` and effort `high`. Integration, deciding which findings are real, merges and the gate stay in the main session. Verify every subagent finding before acting on it. Run at most two subagents at once.

## The gates

Your TAG is in your lane brief.
1. Create `.agent/win/<TAG>/` with:
   - `checks.sh`: every lint, typecheck, unit, property, integration and replay e2e command for your lane, plus `scripts/entry-check.sh` once it exists;
   - `WIN-CHECKLIST.md`;
   - `reaudit.md` and `break-it.md`;
   - `gate.conf`, if needed.

   Format: `.agent/WIN-GATE.md`. Every checklist item is a `- [x]`/`- [P]`/`- [-]`/`- [ ]` line with evidence.
2. Run `bash .agent/win-gate.sh <TAG>` after every fix. Every FAIL line is a work item: fix its cause, never the gate.
3. The entry gate is `bash scripts/entry-check.sh` on a fresh clone of `origin/main`. Its FAIL lines in your area are your work items.

Don't edit `.agent/win-gate.sh` or `.agent/ENTRY-DONE.md`.

## GitHub

Commit locally as often as you like. Push and merge only real, green slices, squashing WIP first. Merge into `main` at most 3 times an hour, following the integration steps in `ENTRY-DONE.md`. Keep exactly one PR per lane. Don't comment on, close or retitle other PRs or issues. Before a turn ends, push whatever is green.

## Budget

Every session shares one account usage limit, so keep tokens lean:
- cap command output (`tail`, `grep`, `head`);
- don't re-read large files;
- skip reruns that can't change a result.

Meta credits: $150 for the whole event. Live calls only in `-m live` tests and `scripts/go-live.sh`, and only when `MODEL_API_KEY` is set. Log the cost of each call.

## Finish

You are finished only when one of these holds:
- your transcript shows, after your last code change, your lane gate at `GATE: PASS` on the HEAD merged into `main`, and `bash scripts/entry-check.sh` printing `ENTRY: PASS` on a fresh clone of `origin/main`;
- `date -u` is past `2026-11-04T18:00Z`.

Then post a final status in your PR and delete your own check-in routines.
