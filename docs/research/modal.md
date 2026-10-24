# Modal (API + worker hosting)

Read 2026-10-24. **`modal.com` couldn't be opened** from this session (network policy, see `docs/BLOCKED-PRE-A.md`). Facts come from web-search summaries, either of Modal's own pages (**[SNIP]**) or of third-party price trackers (**[3P]**). Re-check on <https://modal.com/pricing> and <https://modal.com/docs> before WP5 commits to numbers.

## Plans and credits
| Plan | Price | Included credits | Limits | Source |
|---|---|---|---|---|
| **Starter** | $0/mo | **$30/mo** compute | 3 seats, 100 containers, 10 concurrent GPUs; **5 crons, 8 web endpoints** | [3P] costbench.com, pricingsaas.com (May 2026 diff) |
| Team | $250/mo + compute | $100/mo | unlimited seats, 1,000 containers, 50 GPUs; crons and endpoints unlimited | [3P] |
| Hackathon partner credits | — | **$100** (select participants, MAXXING §1) | — | event page |

A Starter region-selection surcharge (1.5–1.75×) is mentioned by one tracker [3P]. Don't pin a region.

## Compute prices (per second)
| Resource | Price | Per hour | Source |
|---|---|---|---|
| CPU | $0.0000131 / core-s | $0.047 / core-h | [3P] |
| Memory | $0.00000222 / GiB-s | $0.008 / GiB-h | [3P] |
| T4 GPU | $0.000164 / s | $0.59 / h | [3P] costbench; [SNIP] Modal's T4 blog |
| L4 GPU | $0.000222 / s | $0.80 / h | [3P] computeprices.com |

## Features WP5 needs
- **Web endpoints:** a **150 s maximum HTTP request timeout**, even when the function may run longer. Long work should `spawn()` a function call and have the client poll, or use 303 redirects (browsers follow about 20). **[SNIP]** [modal.com/docs/guide/webhook-timeouts](https://modal.com/docs/guide/webhook-timeouts). → The API must be **async jobs**: `POST /jobs` returns a `job_id`, then `GET /jobs/{id}`. The design already does this.
- Request body: "up to 4 GiB" [3P]. Irrelevant, because uploads go **direct to storage via presigned URL** (ARCHITECTURE §5), ≤150 MB.
- **Cron:** `@app.function(schedule=modal.Cron("0 * * * *"))` or `modal.Period(hours=1)`. Starter allows **5 crons**; we need 1 (the 24 h deletion sweep, run hourly). [3P] (API mirror)
- **Secrets:** `modal.Secret.from_name("safecut")`. Keys ≤16,384 chars, values ≤32,768 chars. **[SNIP]** [modal.com/docs/guide/secrets](https://modal.com/docs/guide/secrets). The CLI is `modal secret create safecut MODEL_API_KEY=…`; the owner runs it, never an agent printing the key.
- **Volumes:** persistent file storage with `.commit()` / `.reload()` for cross-container visibility [3P]. Job directories (`jobs/<id>/`) live here; the cron deletes them after 24 h. Size limits and pricing weren't found. **Check before launch.**
- **Cold starts:** no official number found. The third-party guidance is that cold starts plus heavy imports can exceed the 150 s web timeout → keep the web function light (FastAPI only) and do the heavy imports (torch, cv2) in the worker function. Use `min_containers=1` on the web function only during judging (Nov 4–9), at ≈ $0.047/h for 1 core.

## Estimate: one 30 s clip
Assumptions: the CPU worker gets **2 cores + 4 GiB** for **3 minutes** (prepare, render, receipts, waiting on Meta calls), plus **1 GPU-minute** for EgoBlur Gen 2 (≈900 frames × 21 ms ≈ 19 s of inference + model load; `egoblur-gen2.md`).

| Part | Calc | USD |
|---|---|---|
| CPU | 180 s × 2 cores × $0.0000131 | 0.0047 |
| Memory | 180 s × 4 GiB × $0.00000222 | 0.0016 |
| GPU (T4) | 60 s × $0.000164 | 0.0098 |
| GPU (L4, alternative) | 60 s × $0.000222 | (0.0133) |
| **Total per clip** | T4 | **≈ $0.016** |

- With $30/mo Starter credits that's **≈1,850 clips/month**, so Modal isn't the constraint; Meta credits are (≈$0.87/clip, API-NOTES §9).
- The waiting-on-Meta time is billed CPU. If WP0 measures SAM latency well above a minute, move the wait into the async client with many jobs per container, or lower the cores while waiting.
- GPU container cold start (pulling torch + weights) may dominate the 1 GPU-minute. Keep the weights in a Volume and measure.

## Owner step (O2)
Create a Modal account (Starter), claim the hackathon's $100 partner credits if offered, then `gh secret set MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` on this repo.
