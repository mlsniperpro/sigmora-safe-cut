# WP6: web app (review panel, receipt, landing/demo page)

**Branch** `wp6-web` · **Wave** A, starting at kickoff against mock JSON · **Depends on** the contracts in ARCHITECTURE.md §3 (mock them), then WP5's API · **Budget** $0

**Owns:** `web/` (a Next.js App Router app, pnpm, TypeScript), `web/mocks/` (fixture JSON matching the contracts), and `web/README.md`.

## Goal

The screens the demo video and the judges see. This is 25% of the score (Demo), and the Startup track judges whether it feels like a product. Clear, fast and calm: the creator should understand every decision in seconds.

## Screens

1. **Landing (`/`):**
   - Plays the hero result (raw ↔ Safe Cut toggle, labelled).
   - A 3-step "how it works" (Muse Spark decides who · SAM 3.1 keeps them hidden · audit checks the render).
   - The results table (filled from `eval/results` by WP8; placeholder until then).
   - A side-by-side of "blur every face" vs Safe Cut.
   - "Try it" (access code) and links to the repo and Sigmora.
2. **Upload (`/try`):** access code → drag-and-drop (≤60 s, ≤150 MB) → presigned upload → progress through the stages with plain-language labels ("Finding people and objects", "Working out who's part of the story", …).
3. **Review panel (`/jobs/[id]`), the heart of the demo:**
   - The video player with the redaction overlay preview (from `plan.json` boxes, drawn on a canvas over the raw video; it doesn't need a re-render).
   - Three columns of chips: **Hidden**, **Kept clear**, **Needs you**.
   - Each chip shows a thumbnail (redacted), the kind (person/child/plate/screen/document), the **reason**, and a "Why?" drawer. The drawer shows the SoM keyframe with the numbered box highlighted, the votes, and the transcript evidence.
   - One tap toggles hide/keep (locked children show a lock with the explanation). "Merge into participant" for a re-entry ID. "Remove person".
   - Edits post to `/review` and the overlay updates immediately, with no re-tracking.
   - "Approve & render" → progress → result.
4. **Result + receipt (`/jobs/[id]/result`):** the redacted video, a download, the audit summary ("900 frames checked, 1 leak found and fixed"), and an embedded `receipt.html`. "Publish to Sigmora" appears only when opened from Sigmora (query param).
5. **Demo-mode banner** whenever the API returns `mode: "replay"`.

## Steps

1. Scaffold with `pnpm create next-app@latest web --ts --app --eslint --tailwind --src-dir --use-pnpm --no-import-alias`. Use the official CLI; don't hand-roll the config. Add `vitest` + Testing Library, plus scripts: `lint`, `typecheck` (`tsc --noEmit`), `test`.
2. Write a typed API client (`web/src/lib/api.ts`) that uses `web/mocks/` when `NEXT_PUBLIC_SAFECUT_API` is unset. The mocks follow the contracts exactly; update them when WP0's `contracts.py` merges.
3. Build the screens above. Accessibility: keyboard-operable chips, visible focus, colour never the only signal (icons + text), captions on the hero video.
4. Make the overlay canvas sync to `requestVideoFrameCallback`, with a frame-accurate mapping via `job.times`.
5. Deployment needs a Vercel project and a custom domain, which the owner and Claude set up. Don't deploy from the sandbox. Document the env vars in `web/README.md`.

## Tests

Component tests for the chips (toggle, lock, merge), the review reducer, and the API client against mocks. The canvas mapping is unit-tested (frame ↔ time).

## Done when

- [ ] All screens work end to end against the mocks; `pnpm lint && pnpm typecheck && pnpm test` pass.
- [ ] The PR has screenshots of every screen (mock data), and a short GIF of the review flow if possible.
- [ ] After WP5 merges: switching to the live API works (a follow-up PR is fine).
