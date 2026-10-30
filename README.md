# Sigmora Safe Cut

**Publish real-world footage without exposing the people who never agreed to be in it.**

Safe Cut watches a clip filmed in public and decides, from context, what shouldn't be published: bystanders (not participants), children, number plates, and screens and documents that show personal data. Muse Spark reasons about who is part of the story. SAM 3.1 keeps each hidden item covered frame by frame. Anything uncertain stays hidden by default. A second pass audits the final render before anything goes live, and the creator approves every decision.

Built for the **Meta Global AI Developer Hackathon** (Startup track), with Meta's Muse models and SAM 3.1 on the Meta Model API.

> **Status:** the whole pipeline runs end to end in replay on a synthetic demo clip (drawn shapes; its recorded answers were generated from the clip's ground truth, not returned by Meta). Live runs on consented footage start once the owner adds the Meta key (`BLOCKED.md`). Every line of product code here is dated after the kickoff (Oct 26, 12:00 ET).

## Run it yourself

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/). Everything below is offline: replay reads recorded responses and the network is blocked.

<!-- fresh-clone:start -->
```bash
uv sync --locked
uv run safecut run fixtures/clips/SC-A-91-synthetic-20261030.mp4 --out "$(mktemp -d)/demo" --replay --auto-approve-policy
uv run python eval/run.py --split dev --variant full --replay
```
<!-- fresh-clone:end -->

`safecut run` prints each stage and writes `redacted.mp4`, `audit.json`, `receipt.json` and `receipt.html` to the job folder. `eval/run.py` scores a run against the clip's ground truth (`eval/RESULTS.md` lists the committed runs). The API (`uv run uvicorn --factory safecut.api.app:create_app`) and the web app are documented in `web/README.md`.

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
