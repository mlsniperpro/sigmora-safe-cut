import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Transcript } from "@/lib/contracts";
import { useCaptions } from "./useCaptions";

const transcript = (text: string) => ({ status: "ok", turns: [{ speaker: "S1", start: 0, end: 1.5, text }], degraded: false }) as Transcript;

describe("useCaptions", () => {
  it("keeps one URL per captions text: a poll's new transcript object doesn't swap it, and unmounting doesn't revoke it", () => {
    let n = 0;
    URL.createObjectURL = vi.fn(() => `blob:captions-${++n}`);
    const revoke = vi.fn();
    URL.revokeObjectURL = revoke;
    const { result, rerender, unmount } = renderHook(({ t }) => useCaptions(t, true), { initialProps: { t: transcript("Hello there.") } });
    const first = result.current;
    expect(first).toMatch(/^blob:captions-/);
    rerender({ t: transcript("Hello there.") });
    expect(result.current).toBe(first);
    rerender({ t: transcript("Something else.") });
    expect(result.current).not.toBe(first);
    unmount();
    // StrictMode's simulated unmount in dev must not break a URL the <track> still uses.
    expect(revoke).not.toHaveBeenCalled();
    expect(renderHook(() => useCaptions(transcript("Hello there."), true)).result.current).toBe(first);
  });

  it("is null without audio", () => {
    expect(renderHook(() => useCaptions(transcript("Hello there."), false)).result.current).toBeNull();
  });
});
