import { afterEach, describe, expect, it, vi } from "vitest";
import heroMock from "../../mocks/job-review-hero1.json";
import { ApiError, GET_RETRY_DELAYS_MS, REQUEST_TIMEOUT_MS, SafeCutClient, type RawResponse, type RequestInit, type Transport } from "./api";
import { MockBackend } from "./mock-backend";

const headers = (h: Record<string, string> = {}) => ({ get: (k: string) => h[k] ?? null });

function scripted(answers: Array<RawResponse | Error | "hang">) {
  const calls: RequestInit[] = [];
  const transport: Transport = {
    request(init) {
      calls.push(init);
      const next = answers.shift();
      if (next === undefined) throw new Error("no scripted answer left");
      if (next === "hang") {
        return new Promise((_, reject) => init.signal?.addEventListener("abort", () => reject(new Error("aborted"))));
      }
      return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
    },
    upload: () => Promise.resolve(),
  };
  const waits: number[] = [];
  const client = new SafeCutClient({ transport, sleep: (ms) => (waits.push(ms), Promise.resolve()) });
  return { client, calls, waits };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("mediaUrl", () => {
  it("accepts https and same-origin paths only", async () => {
    const { mediaUrl } = await import("./contracts");
    for (const ok of ["https://cdn.example/a.mp4", "/sample/prepared.mp4"]) expect(mediaUrl.safeParse(ok).success).toBe(true);
    for (const bad of ["javascript:alert(1)", "http://x/a.mp4", "//evil.com/a", "/\\evil.com/a", "data:text/html,x", ""]) expect(mediaUrl.safeParse(bad).success, bad).toBe(false);
  });
});

describe("SafeCutClient", () => {
  it("parses a valid job response", async () => {
    const { client, calls } = scripted([{ status: 200, headers: headers(), body: heroMock }]);
    const job = await client.getJob("j_hero1");
    expect(job.items).toHaveLength(4);
    expect(calls[0]).toMatchObject({ method: "GET", path: "/v1/jobs/j_hero1" });
  });

  it("encodes path segments", async () => {
    const { client, calls } = scripted([{ status: 200, headers: headers(), body: heroMock }]);
    await client.getJob("a/../b");
    expect(calls[0]?.path).toBe("/v1/jobs/a%2F..%2Fb");
  });

  it("rejects a response that breaks the contract with a schema error", async () => {
    const { client } = scripted([{ status: 200, headers: headers(), body: { ...heroMock, status: "exploded" } }]);
    await expect(client.getJob("j")).rejects.toMatchObject({ kind: "schema" });
  });

  it("treats malformed JSON as a schema error", async () => {
    const { client } = scripted([{ status: 200, headers: headers(), body: undefined }]);
    await expect(client.getJob("j")).rejects.toMatchObject({ kind: "schema" });
  });

  it("maps an error body to code, detail and Retry-After", async () => {
    const { client } = scripted([{ status: 429, headers: headers({ "Retry-After": "30" }), body: { error: { code: "rate_limited", message: "x" } } }]);
    const error = (await client.render("j").catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "http", status: 429, code: "rate_limited", retryAfterS: 30 });
  });

  it("keeps an HTTP error with an unparseable body, without a code", async () => {
    const { client } = scripted([{ status: 502, headers: headers(), body: "<html>" }]);
    await expect(client.getJob("j")).rejects.toMatchObject({ kind: "http", status: 502, code: null });
  });

  it("retries a GET after network errors with 2 s, 4 s, 8 s backoff, then gives up", async () => {
    const { client, calls, waits } = scripted([new TypeError("offline"), new TypeError("offline"), new TypeError("offline"), new TypeError("offline")]);
    await expect(client.getJob("j")).rejects.toMatchObject({ kind: "network" });
    expect(calls).toHaveLength(4);
    expect(waits).toEqual([...GET_RETRY_DELAYS_MS]);
  });

  it("recovers when a retry succeeds", async () => {
    const { client, calls } = scripted([new TypeError("offline"), { status: 200, headers: headers(), body: heroMock }]);
    await expect(client.getJob("j")).resolves.toMatchObject({ job_id: "j_hero1" });
    expect(calls).toHaveLength(2);
  });

  it("never retries a POST or an HTTP error", async () => {
    const post = scripted([new TypeError("offline")]);
    await expect(post.client.render("j")).rejects.toMatchObject({ kind: "network" });
    expect(post.calls).toHaveLength(1);
    const http = scripted([{ status: 500, headers: headers(), body: { error: { code: "internal" } } }]);
    await expect(http.client.getJob("j")).rejects.toMatchObject({ kind: "http", status: 500 });
    expect(http.calls).toHaveLength(1);
  });

  it("aborts after 15 s as a timeout", async () => {
    vi.useFakeTimers();
    const { client } = scripted(["hang"]);
    const pending = client.render("j").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
    expect(await pending).toMatchObject({ kind: "timeout" });
  });

  it("treats a 404 on DELETE as success and other errors as failures", async () => {
    await expect(scripted([{ status: 404, headers: headers(), body: { error: { code: "expired" } } }]).client.deleteJob("j")).resolves.toBeUndefined();
    await expect(scripted([{ status: 204, headers: headers(), body: null }]).client.deleteJob("j")).resolves.toBeUndefined();
    await expect(scripted([{ status: 500, headers: headers(), body: { error: { code: "internal" } } }]).client.deleteJob("j")).rejects.toMatchObject({ status: 500 });
  });

  it("sends review edits as JSON bodies", async () => {
    const ack = { edit_id: "e", status: "review", has_render: false, items: heroMock.items, plan: heroMock.plan, audit: null };
    const { client, calls } = scripted([{ status: 200, headers: headers(), body: ack }]);
    await client.review("j", { type: "hide", edit_id: "e", item_id: "i_4" });
    expect(calls[0]).toMatchObject({ method: "POST", path: "/v1/jobs/j/review", body: { type: "hide", edit_id: "e", item_id: "i_4" } });
  });
});

describe("MockBackend (integration through the client)", () => {
  const make = (t = { now: 0 }) => {
    const backend = new MockBackend({ latencyMs: 0, stepMs: 100, now: () => t.now });
    return { backend, client: new SafeCutClient({ transport: backend, sleep: () => Promise.resolve() }), t };
  };

  it("runs a clip from code check to result", async () => {
    const { client, t } = make();
    await expect(client.checkCode("judge-code")).resolves.toMatchObject({ kind: "judge" });
    const created = await client.createJob({ code: "judge-code", size_bytes: 1000, content_type: "video/mp4", file_name: "a.mp4" });
    const progress: number[] = [];
    await client.upload(created.upload_url, new Blob(["x"]), "video/mp4", (p) => progress.push(p), new AbortController().signal);
    expect(progress.at(-1)).toBe(1);
    await client.startJob(created.job_id);
    expect((await client.getJob(created.job_id)).status).toBe("processing");
    t.now = 250;
    expect((await client.getJob(created.job_id)).stage).toBe("track");
    t.now = 10_000;
    const review = await client.getJob(created.job_id);
    expect(review.status).toBe("review");

    const ack = await client.review(created.job_id, { type: "hide", edit_id: "e1", item_id: "i_4" });
    expect(ack.items.find((i) => i.item_id === "i_4")).toMatchObject({ decision: "hide", decided_by: "creator" });
    // idempotent: the same edit_id twice is applied once
    const again = await client.review(created.job_id, { type: "hide", edit_id: "e1", item_id: "i_4" });
    expect(again.items).toEqual(ack.items);
    const undone = await client.review(created.job_id, { type: "undo", edit_id: "e2", reverts: "e1" });
    expect(undone.items.find((i) => i.item_id === "i_4")?.decision).toBe("needs_you");

    await expect(client.render(created.job_id)).resolves.toMatchObject({ status: "rendering" });
    await expect(client.render(created.job_id)).rejects.toMatchObject({ status: 409 });
    t.now = 20_000;
    const done = await client.getJob(created.job_id);
    expect(done.status).toBe("done");
    const result = await client.getResult(created.job_id);
    expect(result.audit.unresolved).toBe(0);

    await client.deleteJob(created.job_id);
    await expect(client.getJob(created.job_id)).rejects.toMatchObject({ status: 404 });
  });

  it("serves fixtures by name and error fixtures as errors", async () => {
    const { client } = make();
    await expect(client.getJob("job-review-cafe")).resolves.toMatchObject({ job_id: "j_cafe" });
    await expect(client.getJob("error-404-expired")).rejects.toMatchObject({ status: 404, code: "expired" });
    await expect(client.getJob("nope")).rejects.toMatchObject({ status: 404, code: "not_found" });
    await expect(client.getResult("result-fixed")).resolves.toMatchObject({ audit: { passes: 2 } });
  });

  it("scripts every /try refusal by access code", async () => {
    const { client } = make();
    await expect(client.checkCode("wrong")).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    await expect(client.checkCode("not-yet")).rejects.toMatchObject({ status: 401, code: "code_not_active" });
    await expect(client.createJob({ code: "expired", size_bytes: 1, content_type: "video/mp4", file_name: "a" })).rejects.toMatchObject({ code: "code_not_active" });
    await expect(client.createJob({ code: "ok", size_bytes: 157_286_401, content_type: "video/mp4", file_name: "a" })).rejects.toMatchObject({ status: 413 });
    const job = await client.createJob({ code: "too-big", size_bytes: 1, content_type: "video/mp4", file_name: "a" });
    await expect(client.startJob(job.job_id)).rejects.toMatchObject({ status: 422, code: "job_cap" });
  });

  it("injects failures for the next matching request only", async () => {
    const { client, backend } = make();
    backend.inject(/^POST \/v1\/jobs\/[^/]+\/review$/, "error-500");
    await expect(client.review("job-review-hero1", { type: "hide", edit_id: "a", item_id: "i_4" })).rejects.toMatchObject({ status: 500 });
    await expect(client.review("job-review-hero1", { type: "hide", edit_id: "a", item_id: "i_4" })).resolves.toMatchObject({ edit_id: "a" });
  });

  it("merges, covers a spot and undoes both like WP3", async () => {
    const { client } = make();
    const merged = await client.review("job-review-reentry", { type: "merge", edit_id: "m", item_id: "i_9", into: "i_1" });
    expect(merged.items.map((i) => i.item_id)).toEqual(["i_1"]);
    expect(merged.items[0]?.track_ids).toEqual(["face:2", "person:1", "face:9"]);
    const unmerged = await client.review("job-review-reentry", { type: "undo", edit_id: "u", reverts: "m" });
    expect(unmerged.items.map((i) => i.item_id).sort()).toEqual(["i_1", "i_9"]);

    const covered = await client.review("result-unresolved-review", { type: "cover_spot", edit_id: "c", spot_id: "s1" });
    expect(covered.status).toBe("review");
    expect(covered.audit?.spots[0]?.covered_by).toBe("p_1");
    expect(covered.items.find((i) => i.item_id === "p_1")).toMatchObject({ audit_label: "A1", locked: true, origin: "audit_patch" });
    const uncovered = await client.review("result-unresolved-review", { type: "undo", edit_id: "u2", reverts: "c" });
    expect(uncovered.audit?.spots[0]?.covered_by).toBeNull();
    expect(uncovered.items.some((i) => i.item_id === "p_1")).toBe(false);
  });

  it("refuses edits on a read-only job", async () => {
    const { client } = make();
    await expect(client.review("result-audit-failed", { type: "hide", edit_id: "a", item_id: "i_4" })).rejects.toMatchObject({ status: 409, code: "read_only" });
  });
});
