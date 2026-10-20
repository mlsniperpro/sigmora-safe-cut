# Sigmora Safe Cut

**Publish real-world footage without exposing the people who never agreed to be in it.**

Safe Cut watches a clip filmed in public and decides, from context, what shouldn't be published: bystanders (not participants), children, number plates, and screens and documents that show personal data. Muse Spark reasons about who is part of the story. SAM 3.1 keeps each hidden item covered frame by frame. Anything uncertain stays hidden by default. A second pass audits the final render before anything goes live, and the creator approves every decision.

Built for the **Meta Global AI Developer Hackathon** (Startup track), with Meta's Muse models and SAM 3.1 on the Meta Model API.

> **Status (2026-10-20): pre-event.** This repo holds design docs only. Code starts at the hackathon kickoff (Oct 26, 12:00 ET), and every line of product code here is dated after it.

## What existed before Oct 26

Safe Cut is a new, standalone codebase. It plugs into **Sigmora** (sigmora.org), our existing content platform for creators, which before the event already had:
- Clip preparation and an object-tracking provider interface (a fal SAM 3 provider that never ran live).
- A redaction layer (blur, pixelate or solid boxes on source-anchored tracks) and a renderer.
- An agent action with priced approval cards, an editor tracking UI, and a publishing queue.

None of that code is copied here. Sigmora calls Safe Cut's API as its host app. See `docs/DESIGN.md` §3.

## Docs

| File | What |
|---|---|
| [docs/MAXXING.md](docs/MAXXING.md) | How we win: the judging map, schedule, owner steps, risks |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The standalone architecture, the data contracts between stages, models and config |
| [docs/DESIGN.md](docs/DESIGN.md) | The pipeline design and the research behind it |
| [docs/EVAL.md](docs/EVAL.md) | Labelled dataset, metrics, baselines, protocol |
| [docs/DEMO.md](docs/DEMO.md) | Demo video beats and the live-demo plan |
| [docs/SHOTLIST.md](docs/SHOTLIST.md) | Footage to film, consent rules, release form |
| [docs/CREATOR-PROBLEMS.md](docs/CREATOR-PROBLEMS.md) | Evidence of creator pain |
| [docs/work-packages/](docs/work-packages/) | Parallel work packages for the build |

## License

MIT. See [LICENSE](LICENSE).
