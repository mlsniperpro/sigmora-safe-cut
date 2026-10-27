/**
 * Polling through the real client and mock backend (UI-SPEC §10.3): one 5xx while a job is
 * on screen retries quietly, and /try's poller keeps polling a just-started `created` job.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SafeCutClient, type RawResponse, type Transport } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { MockBackend } from "@/lib/mock-backend";
import { FAST_MS } from "@/lib/polling";
import { useJob } from "./useJob";

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
});
