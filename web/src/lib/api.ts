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

export const REQUEST_TIMEOUT_MS = 15_000;
export const GET_RETRY_DELAYS_MS: readonly number[] = [2_000, 4_000, 8_000];

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

/** Wraps a request in the 15 s timeout, mapping aborts to `timeout` and fetch failures to `network`. */
async function send(transport: Transport, init: RequestInit): Promise<RawResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const outer = init.signal;
  const onOuterAbort = () => controller.abort();
  outer?.addEventListener("abort", onOuterAbort, { once: true });
  try {
    return await transport.request({ ...init, signal: controller.signal });
  } catch (cause) {
    if (controller.signal.aborted && !outer?.aborted) {
      throw new ApiError({ kind: "timeout", message: `${init.method} ${init.path} timed out` });
    }
    if (cause instanceof ApiError) throw cause;
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
}

export class SafeCutClient {
  private readonly transport: Transport;
  private readonly wait: (ms: number, signal?: AbortSignal) => Promise<void>;

  constructor({ transport, sleep: wait = sleep }: ClientOptions) {
    this.transport = transport;
    this.wait = wait;
  }

  /** A JSON request, retried only on network errors and timeouts, and only for GETs (§10.3). */
  private async call<S extends z.ZodType>(schema: S, init: RequestInit): Promise<z.infer<S>> {
    const delays = init.method === "GET" ? GET_RETRY_DELAYS_MS : [];
    for (let attempt = 0; ; attempt += 1) {
      try {
        const raw = await send(this.transport, init);
        checkStatus(init, raw);
        return parseBody(schema, init, raw);
      } catch (error) {
        const retryable = error instanceof ApiError && (error.kind === "network" || error.kind === "timeout");
        const delay = delays[attempt];
        if (!retryable || delay === undefined || init.signal?.aborted) throw error;
        await this.wait(delay, init.signal);
      }
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
    const raw = await send(this.transport, init);
    if (raw.status === 404) return;
    checkStatus(init, raw);
  }

  getDemo(heroId: string, signal?: AbortSignal): Promise<DemoResponse> {
    return this.call(demoResponseSchema, { method: "GET", path: `/v1/demo/${encodeURIComponent(heroId)}`, ...(signal && { signal }) });
  }
}
