import { describe, expect, it } from "vitest";
import { BUSY_MS, FAST_MS, SLOW_MS, nextPollDelay } from "./polling";

describe("nextPollDelay (UI-SPEC §10.3)", () => {
  it("polls every 2 s for the first minute, then every 5 s", () => {
    expect(nextPollDelay("processing", 0, null, 0)).toBe(FAST_MS);
    expect(nextPollDelay("rendering", 59_999, null, 0)).toBe(FAST_MS);
    expect(nextPollDelay("processing", 60_000, null, 0)).toBe(SLOW_MS);
  });
  it("polls every 30 s while Meta is busy, or at retry_at when sooner", () => {
    expect(nextPollDelay("retry_later", 0, null, 0)).toBe(BUSY_MS);
    expect(nextPollDelay("retry_later", 0, "1970-01-01T00:00:10Z", 0)).toBe(10_000);
    expect(nextPollDelay("retry_later", 0, "1970-01-01T00:00:00Z", 5_000)).toBe(BUSY_MS);
  });
  it.each(["review", "needs_you", "done", "failed", "created"] as const)("stops in %s", (s) => {
    expect(nextPollDelay(s, 0, null, 0)).toBeNull();
  });
});
