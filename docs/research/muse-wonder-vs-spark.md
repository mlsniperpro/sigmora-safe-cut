# Muse Wonder 1.0 vs Muse Spark 1.3

Read 2026-10-24. Meta's model pages (`dev.meta.ai/docs/models`, `developer.meta.com/ai/models/…`) **couldn't be opened** (network policy, see `BLOCKED.md`). Sources: Meta's official cookbook (**[GH-cookbook]**, commit `0a99b98`, which doesn't mention Wonder at all), a third-party issue on inspect_ai (**[3P-issue]**), and launch coverage via web-search summaries (**[3P-press]**: [TechCrunch 2026-10-12](https://techcrunch.com/2026/10/12/meta-releases-its-first-frontier-model-muse-wonder/), [VentureBeat](https://venturebeat.com/technology/metas-new-muse-wonder-and-muse-wonder-full-models-achieve-frontier-performance-but-only-the-weaker-one-is-available-via-api), [OpenRouter listing](https://openrouter.ai/meta/muse-wonder), eesel.ai reviews). Treat every row as a hypothesis.

## What's said about each

| | `muse-spark-1.3` | `muse-wonder-1.0` (preview) |
|---|---|---|
| Released | 2026-09-02 [3P-issue] | 2026-10-12 [3P-press] |
| Positioning | Default model of the API; high-volume, multimodal reasoning [GH-cookbook] | "Meta's most capable", positioned for **agentic and coding** work (multi-file changes, sub-agents, parallel tools) [3P-press] |
| Inputs | text, image (≤~50/request), video, PDF; audio "not fully supported" (MAXXING §2) [GH-cookbook] | text, image, **video, audio**, PDF → text [3P-press] |
| Context / output | 1,048,576 / 131,072 [3P-issue] | 1,048,576 / ? [3P-press] |
| Effort levels | `none`…`high`, `xhigh` = `high` [GH-cookbook]; `max` → 400 [3P-issue] | `minimal`…**`max`** [3P-press] |
| Structured output | `text.format` json_schema strict [GH-cookbook] | supported [3P-press] |
| Price (per 1M in / cached / out) | $1.25 / $0.15 / $4.25 | **$4.00 / $0.20 / $20.00** [3P-press] (3.2× input, 4.7× output) |
| Rate limits | 3,000 RPM, 4M TPM [SNIP] | 3,000 RPM, 4M TPM [3P-press] |
| Latency | not published | not published. A preview, and likely slower at `max` |
| Caveat | — | "**Wonder Full**" (stronger) is **Muse Code-only** (subscription); `effort: max` does **not** select it, and there's no API flag [3P-press] |
| Benchmarks | — | AA Index ≈52 (Wonder) vs ≈56 (Full); a single secondary source [3P-press] |

**Bottom line from the sources:** Wonder's advertised strengths are coding and agentic work, not vision. Nothing found claims better **video understanding or person-role judgement** than Spark 1.3. Its audio input claim is interesting, since Spark 1.3's audio is degraded, but Voice Transcribe already covers speech for $0.003/min. At ≈4× the price, Wonder has to show a measured gain to be adopted (MAXXING §2: the owner prefers depth over a model tour).

## Hypotheses WP0 should test (probe f, ≤$1.50 of the WP0 budget)
1. **H1, scene pass quality:** on 3 hero clips, Wonder's participant list (description + evidence) matches the human labels **more often** than Spark 1.3 at `high`. Metric: participants found / missed / hallucinated vs the hero labels.
2. **H2, hard role calls:** on 5 hard SoM keyframe sets (camera-waver, introduced-but-silent, side-on guest, re-entry, child), Wonder at `max` gets ≥1 more right than Spark at `high`, **without** saying `participant` on any bystander or child. One false keep disqualifies it.
3. **H3, audio:** Wonder hears the soundtrack well enough to quote the self-introduction verbatim, where Spark 1.3 says "no speech" (cookbook issue #59 symptom). If true, Wonder could replace the separate speech call for the scene pass only. Voice Transcribe stays as the timing source.
4. **H4, effort levels:** `max` is accepted on Wonder and rejected on Spark (400); `xhigh` behaves like `high` on Spark. Record the exact error body.
5. **H5, cost and latency:** measure wall-clock and `usage` per call. Adopt Wonder for scene or escalation only if quality improves **and** per-clip cost stays **≤ 1.5× the Spark-only cost** at 8 fps. Today that's ≤ $1.25 against Spark's $0.83 (API-NOTES §9). Wonder for scene + escalation is +$0.41, or $1.25, right at the limit, so any wider use of Wonder fails this test. (An earlier draft said ≤ $1.20 against an older $0.77 base. The bar is now relative so it doesn't drift with the cost model.)
6. **H6, frame-number honesty:** on the burned-in counter clip, which model reads the right frame number at the right event more often (DESIGN §5)? This decides how much the scene pass's times can be trusted, even as context.
7. **H7, structured-output strictness:** both models honour the same strict schema with nullable fields and `maxItems` (`docs/prompts/miss-loop.md`).

**Decision rule** (for API-NOTES and `config.py`): set `SAFECUT_SCENE_MODEL` / `SAFECUT_ESCALATE_MODEL` to `muse-wonder-1.0` only if H1 or H2 shows a gain with zero new false keeps, and H5 fits the budget. Otherwise keep Spark 1.3 and say why in the README ("we tested Wonder; it didn't beat Spark on our task").
