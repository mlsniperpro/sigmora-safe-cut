import { afterEach, describe, expect, it, vi } from "vitest";
import { AWAKE_FOR_MS, WAKING_AFTER_MS, WakeTracker } from "./wake";

afterEach(() => {
  vi.useRealTimers();
});

describe("WakeTracker", () => {
  it("turns on once a request has waited the threshold, and off when the API answers", () => {
    vi.useFakeTimers();
    const wake = new WakeTracker();
    const seen: boolean[] = [];
    wake.subscribe(() => seen.push(wake.isWaking()));
    const end = wake.begin();
    vi.advanceTimersByTime(WAKING_AFTER_MS - 1);
    expect(wake.isWaking()).toBe(false);
    vi.advanceTimersByTime(1);
    expect(wake.isWaking()).toBe(true);
    wake.answered();
    expect(wake.isWaking()).toBe(false);
    end();
    expect(seen).toEqual([true, false]);
  });

  it("stays off for a request that finishes before the threshold", () => {
    vi.useFakeTimers();
    const wake = new WakeTracker();
    const end = wake.begin();
    vi.advanceTimersByTime(WAKING_AFTER_MS - 1);
    end();
    vi.advanceTimersByTime(WAKING_AFTER_MS * 2);
    expect(wake.isWaking()).toBe(false);
  });

  it("turns off when the last pending request ends without an answer", () => {
    vi.useFakeTimers();
    const wake = new WakeTracker();
    const end = wake.begin();
    vi.advanceTimersByTime(WAKING_AFTER_MS);
    expect(wake.isWaking()).toBe(true);
    end();
    expect(wake.isWaking()).toBe(false);
  });

  it("does not call a slow request a wake-up while the service is known to be awake", () => {
    vi.useFakeTimers();
    const wake = new WakeTracker();
    wake.answered();
    wake.begin();
    vi.advanceTimersByTime(WAKING_AFTER_MS * 3);
    expect(wake.isWaking()).toBe(false);
  });

  it("calls it one once the awake window has lapsed, and again after a timeout", () => {
    vi.useFakeTimers();
    const wake = new WakeTracker();
    wake.answered();
    vi.advanceTimersByTime(AWAKE_FOR_MS - 1_000);
    wake.begin();
    // It began while the service still counted as awake: it is a wake-up once it has waited the threshold.
    vi.advanceTimersByTime(WAKING_AFTER_MS - 1);
    expect(wake.isWaking()).toBe(false);
    vi.advanceTimersByTime(1);
    expect(wake.isWaking()).toBe(true);
    wake.answered();
    expect(wake.isWaking()).toBe(false);
    wake.lost();
    expect(wake.isAwake()).toBe(false);
    vi.advanceTimersByTime(WAKING_AFTER_MS);
    expect(wake.isWaking()).toBe(true);
  });

  it("stops notifying an unsubscribed listener", () => {
    vi.useFakeTimers();
    const wake = new WakeTracker();
    const listener = vi.fn();
    const off = wake.subscribe(listener);
    off();
    wake.begin();
    vi.advanceTimersByTime(WAKING_AFTER_MS);
    expect(listener).not.toHaveBeenCalled();
  });
});

describe("documented bounds", () => {
  it("counts the API as awake for less than its 300 s idle window (deploy/modal_app.py API_SCALEDOWN_S)", () => {
    expect(AWAKE_FOR_MS).toBeLessThan(300_000);
  });
});
