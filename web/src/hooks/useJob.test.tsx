/**
 * Polling through the real client and mock backend (UI-SPEC §10.3): one 5xx while a job is
 * on screen retries quietly, and /try's poller keeps polling a just-started `created` job.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SafeCutClient, type RawResponse, type Transport } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { MockBackend } from "@/lib/mock-backend";
import { FAST_MS, URL_REFRESH_MS } from "@/lib/polling";
import { useJob, withFreshUrls } from "./useJob";
import type { JobResponse } from "@/lib/contracts";

let backend: MockBackend;
const gets = (id: string) => backend.log.filter((l) => l.method === "GET" && l.path === `/v1/jobs/${id}`).length;

/** Requests still in flight: the mock backend loads fixtures lazily, outside the fake clock. */
const inflight = new Set<Promise<RawResponse>>();
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  backend = new MockBackend({ latencyMs: 0, stepMs: 60_000 });
  const transport: Transport = {
    upload: (...args) => backend.upload(...args),
    request: (init: Parameters<MockBackend["request"]>[0]) => {
      const p = backend.request(init);
      inflight.add(p);
      void p.finally(() => inflight.delete(p)).catch(() => undefined);
      return p;
    },
  };
  setClientForTests(new SafeCutClient({ transport, sleep: () => Promise.resolve() }));
});
afterEach(() => {
  setClientForTests(null);
  vi.useRealTimers();
});

/** Lets every in-flight request and the hook's promise chain finish without moving the clock. */
const settle = () =>
  act(async () => {
    while (inflight.size > 0) await Promise.allSettled([...inflight]);
    for (let i = 0; i < 10; i++) await new Promise((resolve) => setImmediate(resolve));
  });
const poll = async () => {
  await act(() => vi.advanceTimersByTimeAsync(FAST_MS));
  await settle();
};

describe("useJob polling", () => {
  it("rides out one 5xx while a job is on screen, then keeps polling", async () => {
    const { result } = renderHook(() => useJob("job-processing-track"));
    await settle();
    expect(result.current.load.kind).toBe("ready");
    backend.inject(/^GET \/v1\/jobs\/job-processing-track$/, "error-500");
    await poll();
    expect(result.current.load.kind).toBe("ready");
    await poll();
    expect(result.current.load.kind).toBe("ready");
    expect(gets("job-processing-track")).toBe(3);
  });

  it("shows the error after a second 5xx in a row", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { result } = renderHook(() => useJob("job-processing-track"));
    await settle();
    backend.inject(/^GET \/v1\/jobs\/job-processing-track$/, "error-500", 2);
    await poll();
    await poll();
    expect(result.current.load.kind).toBe("unexpected");
  });

  it("a first-load 5xx isn't retried: there's nothing on screen to keep", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    backend.inject(/^GET \/v1\/jobs\/job-processing-track$/, "error-500");
    const { result } = renderHook(() => useJob("job-processing-track"));
    await settle();
    expect(result.current.load.kind).toBe("unexpected");
  });

  it("stops at `created` on a job page, but /try's poller keeps polling after /start", async () => {
    const page = renderHook(() => useJob("job-created"));
    await settle();
    await poll();
    expect(gets("job-created")).toBe(1);
    page.unmount();
    const tryPoller = renderHook(() => useJob("job-created", { pollCreated: true }));
    await settle();
    await poll();
    await poll();
    expect(gets("job-created")).toBe(4);
    expect(tryPoller.result.current.load.kind).toBe("ready");
  });

  it("a paused page refetches quietly before its signed URLs expire, and a failed refresh keeps the page", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { result } = renderHook(() => useJob("job-review-hero1"));
    await settle();
    expect(result.current.load.kind).toBe("ready");
    await act(() => vi.advanceTimersByTimeAsync(FAST_MS * 10));
    expect(gets("job-review-hero1")).toBe(1);
    await act(() => vi.advanceTimersByTimeAsync(URL_REFRESH_MS));
    await settle();
    expect(gets("job-review-hero1")).toBe(2);
    backend.inject(/^GET \/v1\/jobs\/job-review-hero1$/, "error-500");
    await act(() => vi.advanceTimersByTimeAsync(URL_REFRESH_MS));
    await settle();
    expect(result.current.load.kind).toBe("ready");
    await act(() => vi.advanceTimersByTimeAsync(URL_REFRESH_MS));
    await settle();
    expect(gets("job-review-hero1")).toBe(4);
  });
});

describe("withFreshUrls", () => {
  it("takes only the signed URLs from the newer response", () => {
    const base = {
      job_id: "j",
      status: "review",
      keyframe_urls: { "1": "https://old/k1" },
      job: { prepared_url: "https://old/p.mp4", fps: 30 },
      result: { video_url: "https://old/v.mp4" },
      items: ["mine"],
    } as unknown as JobResponse;
    const fresh = { ...base, status: "done", keyframe_urls: { "1": "https://new/k1" }, job: { prepared_url: "https://new/p.mp4", fps: 30 }, result: { video_url: "https://new/v.mp4" }, items: ["theirs"] } as unknown as JobResponse;
    const merged = withFreshUrls(base, fresh) as unknown as typeof base & { items: string[] };
    expect(merged.keyframe_urls).toEqual({ "1": "https://new/k1" });
    expect(merged.job?.prepared_url).toBe("https://new/p.mp4");
    expect(merged.result?.video_url).toBe("https://new/v.mp4");
    expect(merged.status).toBe("review");
    expect(merged.items).toEqual(["mine"]);
  });
});
