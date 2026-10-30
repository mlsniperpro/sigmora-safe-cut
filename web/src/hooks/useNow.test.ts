import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useNow } from "./useNow";

describe("useNow", () => {
  beforeEach(() => vi.useFakeTimers({ now: new Date("2026-10-30T12:00:00Z") }));
  afterEach(() => vi.useRealTimers());

  it("wakes right at a deadline, not at the next interval tick (§10.3, §2.6.1)", () => {
    const at = Date.now() + 3_000;
    const { result } = renderHook(() => useNow(15_000, [at]));
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBeLessThan(at);
    act(() => vi.advanceTimersByTime(3_000));
    expect(result.current).toBeGreaterThanOrEqual(at);
  });

  it("ignores past and missing deadlines, and still ticks every interval", () => {
    const start = Date.now();
    const { result } = renderHook(() => useNow(15_000, [null, start - 1_000]));
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe(start);
    act(() => vi.advanceTimersByTime(15_000));
    expect(result.current).toBe(start + 15_000);
  });
});
