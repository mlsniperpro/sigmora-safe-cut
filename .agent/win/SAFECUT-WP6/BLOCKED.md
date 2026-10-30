# SAFECUT-WP6 blockers (owner inputs only)

Everything below is wired behind the mock API or a replay fixture, so the web app works without it today.

- [ ] Vercel project for `web/` and the custom domain (`safecut.sigmora.org`, MAXXING O5): owner account action. Env to set: `NEXT_PUBLIC_SAFECUT_API` (WP5's API base URL), `NEXT_PUBLIC_SAFECUT_HERO_ID`, `NEXT_PUBLIC_SIGMORA_URL`, `NEXT_PUBLIC_REPO_URL`, and `NEXT_PUBLIC_PRIVACY_CONTACT` (the owner's privacy email for `/privacy`, UI-SPEC §7.1; until it's set, the page points to GitHub issues). See `web/README.md`.
- [ ] Hero clip footage with signed releases (MAXXING O1 / SHOTLIST): the landing player and the side-by-side use sample media until the pinned hero job exists.
- [ ] Make the repo public before submission (official guide: "Repositories must be public"; repos stay private until the owner OKs it). The "Source on GitHub" link points at it.
- [ ] Baseten credits request (for the open-weight bonus, WP2's call; model id `meta-models/muse-spark-open-1026`).
- [ ] The 3-minute demo video (owner records; web provides the demo-mode screens).
