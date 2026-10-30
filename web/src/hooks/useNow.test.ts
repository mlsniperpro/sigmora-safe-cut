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

  it("a deadline already due wakes at once, not at the next tick (Retry-After: 0)", () => {
    const { result, rerender } = renderHook(({ at }: { at: number | null }) => useNow(15_000, [at]), { initialProps: { at: null as number | null } });
    act(() => vi.advanceTimersByTime(5_000));
    const before = result.current;
    // The deadline is set later, at a time that has already come: it opens within a few ms.
    rerender({ at: Date.now() });
    act(() => vi.advanceTimersByTime(2));
    expect(result.current).toBeGreaterThan(before);
  });

  it("ignores missing deadlines, and still ticks every interval", () => {
    const start = Date.now();
    const { result } = renderHook(() => useNow(15_000, [null]));
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe(start);
    act(() => vi.advanceTimersByTime(15_000));
    expect(result.current).toBe(start + 15_000);
  });
});
