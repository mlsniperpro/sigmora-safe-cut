/**
 * The mock backend keeps `/try` jobs in storage, so a reload or the copied review link
 * finds them in mock mode, as the real API would for 24 hours.
 */
import { describe, expect, it } from "vitest";
import { MockBackend } from "./mock-backend";

function memoryStorage() {
  const data = new Map<string, string>();
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), data };
}

const DAY = 24 * 60 * 60 * 1000;

async function createAndStart(backend: MockBackend) {
  const created = await backend.request({ method: "POST", path: "/v1/jobs", body: { code: "any", size_bytes: 1000 } });
  const id = (created.body as { job_id: string }).job_id;
  await backend.request({ method: "POST", path: `/v1/jobs/${id}/start` });
  return id;
}

describe("MockBackend storage", () => {
  it("a /try job survives a reload (a new backend on the same storage), with its edits and a 24-hour deletes_at", async () => {
    let now = Date.parse("2026-11-06T10:00:00Z");
    const storage = memoryStorage();
    const first = new MockBackend({ latencyMs: 0, stepMs: 1, now: () => now, storage });
    const id = await createAndStart(first);
    now += 60_000;
    const before = await first.request({ method: "GET", path: `/v1/jobs/${id}` });
    const job = before.body as { status: string; deletes_at: string; items: Array<{ item_id: string }> };
    expect(job.status).toBe("review");
    expect(job.deletes_at).toBe("2026-11-07T10:00:00.000Z");
    // The typed code ("any") isn't a scripted one, so it never reaches storage.
    expect(storage.data.get("safecut.mock-jobs")).not.toContain('"any"');
    const item = job.items[0]?.item_id ?? "";
    await first.request({ method: "POST", path: `/v1/jobs/${id}/review`, body: { edit_id: "e1", type: "hide", item_id: item } });

    const reloaded = new MockBackend({ latencyMs: 0, stepMs: 1, now: () => now, storage });
    const after = await reloaded.request({ method: "GET", path: `/v1/jobs/${id}` });
    expect(after.status).toBe(200);
    expect(after.body).toEqual((await first.request({ method: "GET", path: `/v1/jobs/${id}` })).body);
    // New jobs don't reuse a stored ID.
    const next = await reloaded.request({ method: "POST", path: "/v1/jobs", body: { code: "any", size_bytes: 1000 } });
    expect((next.body as { job_id: string }).job_id).not.toBe(id);
  });

  it("forgets a job after its deletes_at, and a deleted job stays deleted", async () => {
    let now = Date.parse("2026-11-06T10:00:00Z");
    const storage = memoryStorage();
    const first = new MockBackend({ latencyMs: 0, now: () => now, storage });
    const kept = await createAndStart(first);
    const deleted = await createAndStart(first);
    await first.request({ method: "DELETE", path: `/v1/jobs/${deleted}` });
    const reloaded = new MockBackend({ latencyMs: 0, now: () => now, storage });
    expect((await reloaded.request({ method: "GET", path: `/v1/jobs/${deleted}` })).status).toBe(404);
    expect((await reloaded.request({ method: "GET", path: `/v1/jobs/${kept}` })).status).toBe(200);
    now += DAY + 1;
    const later = new MockBackend({ latencyMs: 0, now: () => now, storage });
    expect((await later.request({ method: "GET", path: `/v1/jobs/${kept}` })).status).toBe(404);
  });

  it("works without storage, and ignores storage it can't read or write", async () => {
    const broken = {
      getItem: () => "{not json",
      setItem: () => {
        throw new DOMException("full", "QuotaExceededError");
      },
    };
    const backend = new MockBackend({ latencyMs: 0, storage: broken });
    const id = await createAndStart(backend);
    expect((await backend.request({ method: "GET", path: `/v1/jobs/${id}` })).status).toBe(200);
    const none = new MockBackend({ latencyMs: 0 });
    expect((await none.request({ method: "GET", path: `/v1/jobs/${await createAndStart(none)}` })).status).toBe(200);
  });

  it("fixture jobs get a deletes_at 24 hours from now and aren't stored", async () => {
    const now = Date.parse("2026-11-06T10:00:00Z");
    const storage = memoryStorage();
    const backend = new MockBackend({ latencyMs: 0, now: () => now, storage });
    const res = await backend.request({ method: "GET", path: "/v1/jobs/job-review-hero1" });
    expect((res.body as { deletes_at: string }).deletes_at).toBe("2026-11-07T10:00:00.000Z");
    expect(JSON.parse(storage.data.get("safecut.mock-jobs") ?? "{}")).toEqual({});
  });

  it("result fixtures play the sample media in mock mode", async () => {
    const backend = new MockBackend({ latencyMs: 0, sample: { job: "job-review-sample", mediaBase: "/sample" } });
    const res = await backend.request({ method: "GET", path: "/v1/jobs/result-fixed/result" });
    expect(res.body).toMatchObject({ video_url: "/sample/redacted.mp4", receipt_html_url: "/sample/receipt.html", receipt_json_url: "/sample/receipt.json" });
    // The summary counts the sample clip's frames, as its receipt does (240 of 240).
    expect(res.body).toMatchObject({ frames: 240, audit: { frames_scanned: 240 } });
  });
});
