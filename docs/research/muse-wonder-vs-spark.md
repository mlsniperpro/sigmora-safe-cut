# Muse Wonder 1.0 vs Muse Spark 1.3

Read 2026-10-24. Meta's model pages (`dev.meta.ai/docs/models`, `developer.meta.com/ai/models/…`) **couldn't be opened** (network policy, see `docs/BLOCKED-PRE-A.md`). Sources: Meta's official cookbook (**[GH-cookbook]**, commit `0a99b98`, which doesn't mention Wonder at all), a third-party issue on inspect_ai (**[3P-issue]**), and launch coverage via web-search summaries (**[3P-press]**: [TechCrunch 2026-10-12](https://techcrunch.com/2026/10/12/meta-releases-its-first-frontier-model-muse-wonder/), [VentureBeat](https://venturebeat.com/technology/metas-new-muse-wonder-and-muse-wonder-full-models-achieve-frontier-performance-but-only-the-weaker-one-is-available-via-api), [OpenRouter listing](https://openrouter.ai/meta/muse-wonder), eesel.ai reviews). Treat every row as a hypothesis.

## What's said about each

| | `muse-spark-1.3` | `muse-wonder-1.0` (preview) |
|---|---|---|
| Released | 2026-09-02 [3P-issue] | 2026-10-12 [3P-press] |
| Positioning | Default model of the API; high-volume, multimodal reasoning [GH-cookbook] | "Meta's most capable", positioned for **agentic and coding** work (multi-file changes, sub-agents, parallel tools) [3P-press] |
| Inputs | text, image (≤~50/request), video, PDF; audio "not fully supported" (MAXXING §2) [GH-cookbook] | text, image, **video, audio**, PDF → text [3P-press] |
| Context / output | 1,048,576 / 131,072 [3P-issue] | 1,048,576 / ? [3P-press] |
| Effort levels | `minimal`…`high`, **`xhigh` (deeper than `high`), `max`**; `none` → 400 [OWNER-2026-10-24, [reasoning page](https://dev.meta.ai/docs/reasoning)]. The cookbook's "`xhigh` = `high`" and a pre-Sep-4 report of `max` → 400 are out of date | the same levels, including **`max`**; `none` → 400 [OWNER-2026-10-24] |
| Structured output | `text.format` json_schema strict [GH-cookbook] | supported [3P-press] |
| Price (per 1M in / cached / out) | $1.25 / $0.15 / $4.25 | **$4.00 / $0.20 / $20.00** [3P-press] (3.2× input, 4.7× output) |
| Rate limits | 3,000 RPM, 4M TPM [SNIP] | 3,000 RPM, 4M TPM [3P-press] |
| Latency | not published | not published. A preview, and likely slower at `max` |
| Caveat | — | "**Wonder Full**" (stronger) is **Muse Code-only** (subscription); `effort: max` does **not** select it, and there's no API flag [3P-press] |
| Benchmarks | — | AA Index ≈52 (Wonder) vs ≈56 (Full); a single secondary source [3P-press] |

**Bottom line from the sources:** Wonder's advertised strengths are coding and agentic work, not vision. Nothing found claims better **video understanding or person-role judgement** than Spark 1.3. Its audio input claim is interesting, since Spark 1.3's audio is degraded, but Voice Transcribe already covers speech for $0.003/min. At ≈4× the price, Wonder has to show a measured gain to be adopted (MAXXING §2: the owner prefers depth over a model tour).

## Hypotheses WP0 should test (probe f, ≤$1.50 of the WP0 budget)
1. **H1, scene pass quality:** on 3 hero clips, Wonder's participant list (description + evidence) matches the human labels **more often** than Spark 1.3 at the same effort (`medium`, as the scene pass uses). Metric: participants found / missed / hallucinated vs the hero labels.
2. **H2, hard role calls:** on 5 hard SoM keyframe sets (camera-waver, introduced-but-silent, side-on guest, re-entry, child), Wonder at `max` gets ≥1 more right than Spark at `max`, **without** saying `participant` on any bystander or child. One false keep disqualifies it.
3. **H3, audio:** Wonder hears the soundtrack well enough to quote the self-introduction verbatim, where Spark 1.3 says "no speech" (cookbook issue #59 symptom). If true, Wonder could replace the separate speech call for the scene pass only. Voice Transcribe stays as the timing source.
4. **H4, effort levels:** confirm the live page: `max` is accepted on both models, and `xhigh` uses measurably more reasoning tokens than `high` (`usage.output_tokens_details.reasoning_tokens`). Record what `max` costs per escalation call, which replaces API-NOTES assumption A6.
5. **H5, cost and latency:** measure wall-clock and `usage` per call. Adopt Wonder for the scene pass or escalation only if quality improves **and** two cost tests pass:
   - **per clip:** cost stays ≤ 1.5× the Spark-only cost at 8 fps, which is ≤ $1.68 against Spark's $1.12 today (API-NOTES §9.1). Scene only ($1.36), escalation only ($1.42) and both ($1.66) all pass;
   - **budget:** the extra spend fits the unallocated headroom in the $150 ledger (API-NOTES §9.2: **$2.86** today). Nothing fits: Wonder for the scene pass adds +$0.24175 per run, which is +$9.43 over the 39 test and hero runs (36 test + 3 hero clips), so it's **not pre-approved** (§9.2).

   **Decided:** H1–H7 run in WP0's probe f (≤ $1.50 of WP0's $6), on the clips each hypothesis names. Wonder is adopted for the reported scene pass only if H1 shows a gain (for escalation: H2), with zero new false keeps, **and**, at that point, the ledger's measured spend leaves room for the option's cost, and the owner raises the test-line cap by its test-run share (API-NOTES §9.2: scene $9.43 room / $8.70 raise; escalation $11.65 / $10.76; both $21.08 / $19.46) (e.g. WP caps, pilots or public traffic came in under their lines). Otherwise Spark stays and the README reports the dev comparison. Wonder escalation uses `max_output_tokens: 24000`, a $0.55 reservation. (The bar is relative so it doesn't drift with the cost model.)
6. **H6, frame-number honesty:** on the burned-in counter clip, which model reads the right frame number at the right event more often (DESIGN §5)? This decides how much the scene pass's times can be trusted, even as context.
7. **H7, structured-output strictness:** both models honour the same strict schema with nullable fields, and whether `maxItems` is accepted under `strict`. The specs leave it out and enforce it in pydantic (`docs/prompts/miss-loop.md`); if it works, WP2 may add it back.

**Decision rule** (for API-NOTES and `config.py`): set `SAFECUT_SCENE_MODEL` / `SAFECUT_ESCALATE_MODEL` to `muse-wonder-1.0` only if H1 or H2 shows a gain with zero new false keeps, and H5 fits the budget. Otherwise keep Spark 1.3 and say why in the README ("we tested Wonder; it didn't beat Spark on our task").
