# Modal (API + worker hosting)

Read 2026-10-24; plan limits re-checked on <https://modal.com/pricing> 2026-10-25 (Starter: $30/mo credits, 3 seats, 100 containers, 10 GPU concurrency, 5 crons, 200 apps; web endpoints "limited", no number given). Facts come from web-search summaries, either of Modal's own pages (**[SNIP]**) or of third-party price trackers (**[3P]**). Re-check on <https://modal.com/pricing> and <https://modal.com/docs> before WP5 commits to numbers.

## Plans and credits
| Plan | Price | Included credits | Limits | Source |
|---|---|---|---|---|
| **Starter** | $0/mo | **$30/mo** compute | 3 seats, 100 containers, 10 concurrent GPUs; **5 crons**, 200 apps, web endpoints limited (no number) | [modal.com/pricing](https://modal.com/pricing), read 2026-10-25 |
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
- Request body: "up to 4 GiB" [3P]. Uploads must **not** go through the endpoint (150 MB against the 150 s web timeout above). ARCHITECTURE §5 and WP5 assume a presigned upload URL, but a **Modal Volume has none**. **Decided:** an S3-compatible **Cloudflare R2** bucket (sigmora.org already sits in Cloudflare, MAXXING O5) mounted in the worker with `modal.CloudBucketMount("<bucket>", bucket_endpoint_url="https://<account_id>.r2.cloudflarestorage.com", secret=<safecut-r2>, read_only=True)` (the mount reads the standard `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from that secret, [cloud-bucket-mounts](https://modal.com/docs/guide/cloud-bucket-mounts), read 2026-10-26; `SAFECUT_R2_*` are only for `boto3` presigning); `POST /v1/jobs` takes the declared `size_bytes` and `content_type` (`video/mp4` or `video/quicktime`) and answers **`413` with `error.code: "too_large"` and `error.size_bytes`** above **157,286,400 bytes (150 MiB = 150 × 1024 × 1024, the same number as PR #2 UI-SPEC §10.2)**; otherwise it returns a presigned R2 `PUT` URL **signed with that `Content-Length` and `Content-Type`** (15 min expiry, via `boto3`), so the browser's `PUT` must send exactly those two headers. The URL is single-use in practice: an upload that stalls, fails or outlives the 15 min is never resumed or re-signed; the client `DELETE`s that job and starts again with a new `POST /v1/jobs` (a fresh job and URL; a `created` job left behind is removed by the 24 h purge). `POST /start` `HEAD`s the object **synchronously, before queuing any paid step**: a missing object or a size other than the declared `size_bytes` answers **`409` with `error.code: "upload_incomplete"`**, spends nothing, and is not retryable on that job (the client offers [Try another clip], i.e. a new job); the worker then reads the upload from the mount. The bucket needs a **CORS rule** for the web origin (PUT with `Content-Type` and `Content-Length`), an owner step. The R2 bucket and its API token are an owner step (BLOCKED-PRE-A) and a Modal secret; the 24 h purge deletes R2 objects too. *Rejected:* streaming 150 MB through the ASGI endpoint (timeouts), and the clips bucket (read-only token).
- **Cron:** `@app.function(schedule=modal.Cron("*/5 * * * *"))`. Starter allows **5 crons**; we use 1, every 5 minutes: it re-queues `retry_later` jobs whose 5 min have passed (API-NOTES §10.3), and on minute 0 runs the hourly work (the 24 h purge and the Meta file sweep). [3P] (API mirror)
- **Secrets:** `modal.Secret.from_name("safecut")`. Keys ≤16,384 chars, values ≤32,768 chars. **[SNIP]** [modal.com/docs/guide/secrets](https://modal.com/docs/guide/secrets). The CLI is `modal secret create safecut MODEL_API_KEY=…`; the owner runs it, never an agent printing the key.
- **Volumes** ([modal.com/docs/guide/volumes](https://modal.com/docs/guide/volumes), read 2026-10-26): "At container creation time the latest state of an attached Volume is mounted"; other containers' commits appear only after `.reload()`, and "While a reload is in progress the Volume will appear empty to the container that initiated the reload"; "Last write wins in case of concurrent modification of the same file", "nor is distributed file locking supported"; v1 has a hard limit of 500,000 inodes and recommends ≤ 5 concurrent writers; v2 has no file-count limit and scales with writers to **distinct** files. **Decided (WP5):** a **v1** Volume (the default of `from_name`): "Volumes v2 are still in Beta. We cannot yet guarantee that no data will be lost", and this Volume holds the spend ledger; Safe Cut's few jobs a day stay far below v1's inode and writer limits. **Every file has one writer at a time:** during a processing segment, the job's worker; outside one (review edits, `cover_spot`, starting `POST /audit`, and `DELETE`), a `job_writer` Modal function with `max_containers=1` that reloads, applies the edit, runs the guard and commits, so two edits to one job are serialised; the web container never writes the Volume; a job's `cost.jsonl` is per job; `system` cost lines, the `/healthz` last-result cache and the startup-probe deploy marker only through the single-writer `budget` function (API-NOTES §10.2, §10.7). `GET /v1/jobs/{id}` reads job status from a `modal.Dict` (`safecut-job-status`), written by whichever function changes the status (the web container for `created`/`queued` and the `/start` refusals, the worker during a segment, `job_writer` for edits, `job_writer` for `deleted`, the cron for the `retry_later` re-queue and the purge); never from a Volume read in the web container. The 24 h purge sets the entry to `expired` (answered `404` `code: "expired"`, PR #2 §10.3) before deleting the job's files; Dict entries "expire after 7 days of inactivity" ([modal.Dict](https://modal.com/docs/reference/modal.Dict)), after which the job is `404` not found. Pinned hero jobs (exempt from the purge) are served by `GET /v1/demo/{hero_id}` **from their Volume files**, never from the Dict, so they outlive its 7-day expiry; result files are read after a `reload()` serialised by one `asyncio.Lock` per web container, and a file missing right after a reload is retried once, then answered `503` (never treated as an absent stage output). Job directories (`jobs/<id>/`) live here; the cron deletes them after 24 h. Size limits and pricing weren't found. **Check before launch.**
- **Cold starts:** no official number found. The third-party guidance is that cold starts plus heavy imports can exceed the 150 s web timeout → keep the web function light (FastAPI only) and do the heavy imports (torch, cv2) in the worker function. Use `min_containers=1` on the web function only during the public window (Nov 5–10 UTC, API-NOTES §9.2), at ≈ $0.047/h for 1 core.

## API names for WP5 (`modal` 1.6.2 from PyPI, signatures inspected in a scratch venv, 2026-10-24)
These are a primary source: the installed package's own signatures and docstrings. Pin `modal==1.6.2` in the `deploy` group.

| Need | API (1.6.2) | Notes and decision |
|---|---|---|
| Worker function | `@app.function(image=…, cpu=2, memory=4096, timeout=7200, secrets=[modal.Secret.from_name("safecut")], volumes={"/jobs": vol}, max_containers=…, retries=0)` | `timeout` covers execution and startup ("Maximum execution time for inputs and startup time in seconds"). **7,200 s = the 2 h limit per processing segment** of API-NOTES §10.1: each segment (up to review-ready; render + audit) is its own worker call, so the creator's review never runs inside one. `retries=0`, because stage retries are the client's job (§10.2) and a Modal retry would double-bill Meta calls |
| GPU audit function | the same, with `gpu="T4"` (or `"L4"`) | holds the EgoBlur weights in the Volume; `enable_memory_snapshot=True` can cut cold starts. Measure both |
| Public API | `@modal.asgi_app()` on a light function (FastAPI only), served at its `*.modal.run` URL | **`custom_domains` is a Team-plan feature** (modal.com/pricing, read 2026-10-25: listed under Team, not Starter), so on Starter the API stays on `*.modal.run` and the custom domain `safecut.sigmora.org` points at the Vercel web app, which calls the API URL from env. The 150 s web timeout (§ "Features") means: return the job id at once |
| Start a job, then poll | worker `.spawn(...)` → `FunctionCall`; `FunctionCall.get(timeout=0)` to poll | job status is in the `safecut-job-status` Dict (see Volumes above), so `GET /jobs/{id}` reads it without holding a call open; result files are on the Volume |
| Re-queue, 24 h deletion and file sweeper | `schedule=modal.Cron("*/5 * * * *")` (signature `Cron(cron_string, timezone="UTC")`) | one function every 5 minutes: re-queues `retry_later` jobs due (API-NOTES §10.3), and on minute 0 does the hourly work: purge jobs older than 24 h (except the pinned hero jobs, API-NOTES §12 WP5 deviation), and delete Meta files older than 6 h (API-NOTES §10.4). Starter allows 5 crons [3P] |
| Job storage | `modal.Volume.from_name("safecut-jobs", create_if_missing=True)`; `vol.commit()` after writes, `vol.reload()` before reads in another container | without `commit`/`reload`, another container doesn't see the files |
| Secrets | `modal.Secret.from_name("safecut")` → env vars (`MODEL_API_KEY`, …) | created by the owner with the `modal secret create` CLI |
| Warm container during judging | `min_containers=1` on the web function **and the `budget` function**, Nov 5–10 UTC only (the public window, API-NOTES §9.2; a cold `budget` would turn its 10 s reserve timeout into spurious `MetaUnavailable`) | ≈ $0.047/h for 1 core [3P price] |
| Cost ceiling | `max_containers` on the worker (e.g. 4) | bounds Modal spend and Meta concurrency together (§10.1) |

## Estimate: one 30 s clip
Assumptions: the CPU worker gets **2 cores + 4 GiB** for **3 minutes** (prepare, render, receipts, waiting on Meta calls), plus **1 GPU-minute** for EgoBlur Gen 2 (≈900 frames × 21 ms ≈ 19 s of inference + model load; `egoblur-gen2.md`).

| Part | Calc | USD |
|---|---|---|
| CPU | 180 s × 2 cores × $0.0000131 | 0.0047 |
| Memory | 180 s × 4 GiB × $0.00000222 | 0.0016 |
| GPU (T4) | 60 s × $0.000164 | 0.0098 |
| GPU (L4, alternative) | 60 s × $0.000222 | (0.0133) |
| **Total per clip** | T4 | **≈ $0.016** |

- With $30/mo Starter credits that's **≈1,850 clips/month**, so Modal isn't the constraint; Meta credits are (≈$1.12 per 30 s clip, API-NOTES §9).
- The waiting-on-Meta time is billed CPU. If WP0 measures SAM latency well above a minute, move the wait into the async client with many jobs per container, or lower the cores while waiting.
- GPU container cold start (pulling torch + weights) may dominate the 1 GPU-minute. Keep the weights in a Volume and measure.

## Owner step (O2)
Create a Modal account (Starter), claim the hackathon's $100 partner credits if offered, then `gh secret set MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` on this repo.
