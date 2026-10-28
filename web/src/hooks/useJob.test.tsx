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
/** When on, each job GET signs its media URLs afresh (`sig=<n>`), as the live API does. */
let signing = false;
let signed = 0;
const sign = (url: string) => `${url.split("?")[0]}?sig=${signed}`;
function signJob(raw: RawResponse): RawResponse {
  if (raw.status !== 200) return raw;
  signed += 1;
  const job = raw.body as JobResponse;
  return {
    ...raw,
    body: {
      ...job,
      keyframe_urls: Object.fromEntries(Object.entries(job.keyframe_urls ?? {}).map(([k, v]) => [k, sign(v)])),
      ...(job.job && { job: { ...job.job, prepared_url: sign(job.job.prepared_url ?? "https://media.example/prepared.mp4") } }),
    },
  };
}
beforeEach(() => {
  signing = false;
  signed = 0;
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  backend = new MockBackend({ latencyMs: 0, stepMs: 60_000 });
  const transport: Transport = {
    upload: (...args) => backend.upload(...args),
    request: (init: Parameters<MockBackend["request"]>[0]) => {
      const p = backend.request(init).then((raw) => (signing && init.method === "GET" && /^\/v1\/jobs\/[^/]+$/.test(init.path) ? signJob(raw) : raw));
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

describe("signed URLs on screen (UI-SPEC §10.7)", () => {
  const ready = (load: ReturnType<typeof useJob>["load"]) => (load.kind === "ready" ? load.job : null);

  it("polls keep the URLs on screen, so the video and thumbnails don't reload; refreshUrls takes fresh ones", async () => {
    signing = true;
    const { result } = renderHook(() => useJob("job-processing-track"));
    await settle();
    expect(ready(result.current.load)?.job?.prepared_url).toMatch(/sig=1$/);
    await poll();
    await poll();
    expect(gets("job-processing-track")).toBe(3);
    expect(ready(result.current.load)?.job?.prepared_url).toMatch(/sig=1$/);
    for (const url of Object.values(ready(result.current.load)?.keyframe_urls ?? {})) expect(url).toMatch(/sig=1$/);
    act(() => result.current.refreshUrls());
    await settle();
    expect(ready(result.current.load)?.job?.prepared_url).toMatch(/sig=4$/);
  });

  it("a fresh-URL refresh cut short by another tick still ends with fresh URLs", async () => {
    signing = true;
    const { result } = renderHook(() => useJob("job-review-hero1"));
    await settle();
    expect(ready(result.current.load)?.job?.prepared_url).toMatch(/sig=1$/);
    // The fresh GET is in flight when another tick (a poll, resume()) starts a plain one.
    act(() => result.current.refreshUrls());
    act(() => result.current.resume());
    await settle();
    expect(ready(result.current.load)?.job?.prepared_url).not.toMatch(/sig=1$/);
  });

  it("the quiet refresh brings fresh URLs, and survives the tab being hidden and shown again", async () => {
    signing = true;
    const visibility = vi.spyOn(document, "visibilityState", "get");
    const { result } = renderHook(() => useJob("job-review-hero1"));
    await settle();
    visibility.mockReturnValue("hidden");
    act(() => void document.dispatchEvent(new Event("visibilitychange")));
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    visibility.mockReturnValue("visible");
    act(() => void document.dispatchEvent(new Event("visibilitychange")));
    await act(() => vi.advanceTimersByTimeAsync(URL_REFRESH_MS - 30_000));
    await settle();
    expect(gets("job-review-hero1")).toBe(2);
    expect(ready(result.current.load)?.job?.prepared_url).toMatch(/sig=2$/);
    visibility.mockRestore();
  });
});

