/**
 * Typed client for the Safe Cut API (WP5; routes and shapes in UI-SPEC §8, §10).
 *
 * The client always talks to the API at `NEXT_PUBLIC_SAFECUT_API` (`client.ts`);
 * unit tests swap in the mock backend (`src/test/mock-backend.ts`). Every
 * response body is parsed against its schema; anything else becomes a typed
 * `ApiError`.
 */
import type { z } from "zod";
import {
  actionAckSchema,
  codeCheckSchema,
  createJobResponseSchema,
  demoResponseSchema,
  errorBodySchema,
  jobResponseSchema,
  resultResponseSchema,
  reviewAckSchema,
  type ActionAck,
  type CodeCheck,
  type CreateJobResponse,
  type DemoResponse,
  type ErrorBody,
  type JobResponse,
  type ResultResponse,
  type ReviewAck,
  type ReviewEdit,
} from "./contracts";
import { WakeTracker } from "./wake";

/** A request's timeout while the service is known to be awake (it answered in the last two minutes). */
export const REQUEST_TIMEOUT_MS = 15_000;
/**
 * A request's timeout otherwise. The API scales to zero and Modal queues the first request after a quiet
 * spell until a container is up (10 to 40 s; UI-SPEC §10.3 "Cold start"), so the first request waits for it.
 * Under Modal's own 150 s limit per request, so a real outage is ours to report, not a gateway error.
 */
export const COLD_START_TIMEOUT_MS = 60_000;
export const GET_RETRY_DELAYS_MS: readonly number[] = [2_000, 4_000, 8_000];
/** A call that times out twice has waited out a cold start at least once: a third wait would only hide an outage. */
const MAX_TIMEOUTS_PER_CALL = 2;

export type ApiErrorKind = "http" | "network" | "timeout" | "schema";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly detail: ErrorBody["error"] | null;
  /** Seconds from a `Retry-After` header, when the server sent one. */
  readonly retryAfterS: number | null;

  constructor(init: {
    kind: ApiErrorKind;
    message: string;
    status?: number | null;
    detail?: ErrorBody["error"] | null;
    retryAfterS?: number | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status ?? null;
    this.detail = init.detail ?? null;
    this.code = init.detail?.code ?? null;
    this.retryAfterS = init.retryAfterS ?? null;
  }
}

export interface RawResponse {
  status: number;
  headers: { get(name: string): string | null };
  body: unknown;
}

export interface RequestInit {
  method: "GET" | "POST" | "DELETE";
  path: string;
  body?: unknown;
  signal?: AbortSignal;
}

/** The seam between the client and the network (live fetch or the mock backend). */
export interface Transport {
  request(init: RequestInit): Promise<RawResponse>;
  upload(url: string, file: Blob, contentType: string, onProgress: (fraction: number) => void, signal: AbortSignal): Promise<void>;
}

export { apiBaseUrl } from "./api-base";

function parseRetryAfter(value: string | null): number | null {
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds;
  const date = Date.parse(value);
  return Number.isNaN(date) ? null : Math.max(0, (date - Date.now()) / 1000);
}

/**
 * Requests that are safe to send twice, so a timeout or network error may be retried: every GET, and
 * `POST /v1/codes/check`, which only reads. Every other POST is not: a request that timed out may still have
 * been processed (a cold start can finish a `POST /start` or `/render` after the browser gave up), so
 * repeating it could create a second job or bill a second render. Those are reported instead, and the job's
 * polling shows whether the server accepted them (UI-SPEC §10.3 "Timeouts"). `DELETE` isn't retried either.
 */
function isIdempotent(init: RequestInit): boolean {
  return init.method === "GET" || (init.method === "POST" && init.path === "/v1/codes/check");
}

/** A gateway answering for an API that isn't up yet; anything else came from the API itself. */
const GATEWAY_STATUSES = new Set([502, 503, 504]);

/**
 * Wraps a request in its timeout (15 s once the service is awake, 60 s before), mapping aborts to `timeout`
 * and fetch failures to `network`, and tells `wake` whether the API answered.
 */
async function send(transport: Transport, wake: WakeTracker, init: RequestInit): Promise<RawResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), wake.isAwake() ? REQUEST_TIMEOUT_MS : COLD_START_TIMEOUT_MS);
  const outer = init.signal;
  const onOuterAbort = () => controller.abort();
  outer?.addEventListener("abort", onOuterAbort, { once: true });
  try {
    const raw = await transport.request({ ...init, signal: controller.signal });
    if (GATEWAY_STATUSES.has(raw.status)) wake.lost();
    else wake.answered();
    return raw;
  } catch (cause) {
    if (controller.signal.aborted && !outer?.aborted) {
      wake.lost();
      throw new ApiError({ kind: "timeout", message: `${init.method} ${init.path} timed out` });
    }
    if (cause instanceof ApiError) throw cause;
    if (!outer?.aborted) wake.lost();
    throw new ApiError({ kind: "network", message: `${init.method} ${init.path} failed: ${String(cause)}` });
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", onOuterAbort);
  }
}

function checkStatus(init: RequestInit, raw: RawResponse): void {
  if (raw.status >= 200 && raw.status < 300) return;
  const parsed = errorBodySchema.safeParse(raw.body);
  throw new ApiError({
    kind: "http",
    status: raw.status,
    message: `${init.method} ${init.path} → ${raw.status}`,
    detail: parsed.success ? parsed.data.error : null,
    retryAfterS: parseRetryAfter(raw.headers.get("Retry-After")),
  });
}

function parseBody<S extends z.ZodType>(schema: S, init: RequestInit, raw: RawResponse): z.infer<S> {
  const parsed = schema.safeParse(raw.body);
  if (!parsed.success) {
    throw new ApiError({
      kind: "schema",
      status: raw.status,
      message: `${init.method} ${init.path}: response doesn't match the contract: ${parsed.error.issues
        .slice(0, 3)
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ")}`,
    });
  }
  return parsed.data;
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        reject(new ApiError({ kind: "network", message: "aborted" }));
      },
      { once: true },
    );
  });

export interface ClientOptions {
  transport: Transport;
  /** Injected for tests so retries don't wait for real. */
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  /** Injected for tests; the app's client owns its own. */
  wake?: WakeTracker;
}

export class SafeCutClient {
  private readonly transport: Transport;
  private readonly wait: (ms: number, signal?: AbortSignal) => Promise<void>;
  /** Whether the API is probably waking from a cold start; the UI subscribes to it (`useServiceWaking`). */
  readonly wake: WakeTracker;

  constructor({ transport, sleep: wait = sleep, wake = new WakeTracker() }: ClientOptions) {
    this.transport = transport;
    this.wait = wait;
    this.wake = wake;
  }

  /**
   * A JSON request, retried only on network errors and timeouts, and only when it is safe to send twice
   * (`isIdempotent`, §10.3). The whole call, retries included, counts as one wait for the wake-up signal.
   */
  private async call<S extends z.ZodType>(schema: S, init: RequestInit): Promise<z.infer<S>> {
    const delays = isIdempotent(init) ? GET_RETRY_DELAYS_MS : [];
    const end = this.wake.begin();
    try {
      let timeouts = 0;
      for (let attempt = 0; ; attempt += 1) {
        try {
          const raw = await send(this.transport, this.wake, init);
          checkStatus(init, raw);
          return parseBody(schema, init, raw);
        } catch (error) {
          if (error instanceof ApiError && error.kind === "timeout") timeouts += 1;
          const retryable = error instanceof ApiError && (error.kind === "network" || error.kind === "timeout") && timeouts < MAX_TIMEOUTS_PER_CALL;
          const delay = delays[attempt];
          if (!retryable || delay === undefined || init.signal?.aborted) throw error;
          await this.wait(delay, init.signal);
        }
      }
    } finally {
      end();
    }
  }

  checkCode(code: string, signal?: AbortSignal): Promise<CodeCheck> {
    return this.call(codeCheckSchema, { method: "POST", path: "/v1/codes/check", body: { code }, ...(signal && { signal }) });
  }

  createJob(
    input: { code: string; size_bytes: number; content_type: string; file_name: string },
    signal?: AbortSignal,
  ): Promise<CreateJobResponse> {
    return this.call(createJobResponseSchema, { method: "POST", path: "/v1/jobs", body: input, ...(signal && { signal }) });
  }

  upload(url: string, file: Blob, contentType: string, onProgress: (fraction: number) => void, signal: AbortSignal): Promise<void> {
    return this.transport.upload(url, file, contentType, onProgress, signal);
  }

  startJob(jobId: string, signal?: AbortSignal): Promise<ActionAck> {
    return this.call(actionAckSchema, { method: "POST", path: `/v1/jobs/${encodeURIComponent(jobId)}/start`, ...(signal && { signal }) });
  }

  getJob(jobId: string, signal?: AbortSignal): Promise<JobResponse> {
    return this.call(jobResponseSchema, { method: "GET", path: `/v1/jobs/${encodeURIComponent(jobId)}`, ...(signal && { signal }) });
  }

  getResult(jobId: string, signal?: AbortSignal): Promise<ResultResponse> {
    return this.call(resultResponseSchema, { method: "GET", path: `/v1/jobs/${encodeURIComponent(jobId)}/result`, ...(signal && { signal }) });
  }

  review(jobId: string, edit: ReviewEdit, signal?: AbortSignal): Promise<ReviewAck> {
    return this.call(reviewAckSchema, { method: "POST", path: `/v1/jobs/${encodeURIComponent(jobId)}/review`, body: edit, ...(signal && { signal }) });
  }

  render(jobId: string, signal?: AbortSignal): Promise<ActionAck> {
    return this.call(actionAckSchema, { method: "POST", path: `/v1/jobs/${encodeURIComponent(jobId)}/render`, ...(signal && { signal }) });
  }

  audit(jobId: string, signal?: AbortSignal): Promise<ActionAck> {
    return this.call(actionAckSchema, { method: "POST", path: `/v1/jobs/${encodeURIComponent(jobId)}/audit`, ...(signal && { signal }) });
  }

  /** Resolves on 2xx and on any 404 (the job is gone either way, §10.3). */
  async deleteJob(jobId: string, signal?: AbortSignal): Promise<void> {
    const init: RequestInit = { method: "DELETE", path: `/v1/jobs/${encodeURIComponent(jobId)}`, ...(signal && { signal }) };
    const end = this.wake.begin();
    try {
      const raw = await send(this.transport, this.wake, init);
      if (raw.status === 404) return;
      checkStatus(init, raw);
    } finally {
      end();
    }
  }

  getDemo(heroId: string, signal?: AbortSignal): Promise<DemoResponse> {
    return this.call(demoResponseSchema, { method: "GET", path: `/v1/demo/${encodeURIComponent(heroId)}`, ...(signal && { signal }) });
  }
}
