# Win gate

`bash .agent/win-gate.sh <TAG>` decides when a hackathon session is done. It is
the hackathon version of prod-kit's gate: every check covers only your branch's
diff against `origin/main`, and each session keeps its evidence in its own
folder, `.agent/win/<TAG>/`, so parallel sessions in one repo never block each
other. Your `/goal` is met only when the transcript shows this gate print
`GATE: PASS` on your pushed HEAD, after your last code change.

## Session tags

| Entry | TAG |
|---|---|
| Circle (Build With AI) | `CIRCLE` |
| Landys Inspect (OpenCV) WP1 to WP4 | `OPENCV-WP1` … `OPENCV-WP4` |
| Night Shift (GitLab) | `NIGHTSHIFT` |
| Counterexample (Nebius) | `COUNTEREXAMPLE` |
| Tastemaker (Qloo) | `TASTEMAKER` |
| MediQuest YouCam WP1, WP2, WP4 | `YOUCAM-WP1`, `YOUCAM-WP2`, `YOUCAM-WP4` |
| Safe Cut (Meta) PRE-A, PRE-B | `SAFECUT-PRE-A`, `SAFECUT-PRE-B` |

## One-time setup on your branch

```bash
git fetch origin main
git checkout origin/main -- .agent/win-gate.sh .agent/WIN-GATE.md .agent/win/.gitignore
mkdir -p .agent/win/<TAG>
```

Then write the files below and commit them with your next substantial push.

## What the gate reads

All paths are relative to `.agent/win/<TAG>/` unless noted.

| File | Format | Gate requires |
|---|---|---|
| `checks.sh` | Every lint, typecheck, unit/property, integration, replay e2e and build command for this entry, one per line, plain `set -euo pipefail` bash | Exists, contains a test command, exits 0 |
| Checklist (`WIN-CHECKLIST.md` here, else repo-root `WIN-CHECKLIST.md`, or `CHECKLIST=<path>` in `gate.conf`) | One line per judging criterion, brief requirement and audit finding: `- [x] … evidence`, `- [P] … owner input`, `- [-] … not applicable, why`, `- [ ] …` while open | No `- [ ]`, at least 15 resolved lines, and no table row still showing ❌ 🔧 ⏳ 🟡 🚧 ⚠️ WIP or TODO |
| Blockers (`BLOCKED.md` here, else repo-root `BLOCKED.md`, or `BLOCKED=<path>`) | Checklist of exact owner inputs (key name, account, footage, spend), never questions | Non-empty whenever any item is `- [P]` |
| `reaudit.md` | Header lines `AUDITED_COMMIT: <sha>`, `OPEN_CRITICAL: <n>`, `OPEN_HIGH: <n>`, `CLEAN_AUDITS_IN_A_ROW: <n>`, then the findings | 0 critical, 0 high, at least 2 clean audits in a row, and no code changed after `AUDITED_COMMIT` |
| `break-it.md` | `TESTED_COMMIT: <sha>`, then what you did to break it (fuzz, soak, failure injection, the replay e2e path, a fresh-clone README run) and the results | No code changed after `TESTED_COMMIT` |
| `pids` | One PID per line for background soak or fuzz runs | None still running |
| `gate-skip` | `<command substring> \| <reason>` | Only for a command that physically needs an owner input that is listed in the blockers file |
| `gate.conf` | `KEY=value` lines: `CHECKLIST`, `BLOCKED`, `BASE` (default `origin/main`) | Optional |

The gate also checks, on your branch only:

- **Git:** the working tree is clean and every commit is pushed.
- **Package scripts:** the `lint`, `typecheck`, `test` and `build` scripts of every package your diff touches pass.
- **Shortcuts:** no TODO/FIXME, stub, skipped or focused test, `|| true` or unjustified lint suppression appears in any line you added.
- **Secrets:** no secret pattern appears in any line you added. It runs gitleaks too when installed.

## Rules

- Never edit `win-gate.sh`. The gate fails if it differs from `origin/main`.
- Never weaken `checks.sh`, a test, or a threshold to get green. Fix the cause.
- `CLEAN_AUDITS_IN_A_ROW` goes back to 0 whenever an audit finds anything. An audit is a full pass as a strict judge and a hostile senior reviewer over the whole entry, not a re-read of your last diff.
- `- [P]` is only for what physically needs the owner: secrets and API keys, account sign-ups, spending money, messages to real people, filming footage, and making repos public. Everything else is yours to finish.
- A line that must contain a flagged word (a test fixture, say) takes a `gate-allow: <reason>` comment on the same line.
- Run the gate before every push, and paste its last line into your PR status.
