import fc from "fast-check";
import { describe, expect, it } from "vitest";
import {
  checkTimeline,
  formatFrame,
  formatFrameRange,
  formatFrameTenths,
  formatSeconds,
  frameAt,
  frameStart,
} from "./time";

describe("frameAt (UI-SPEC §10.6, PRE-A vector T5)", () => {
  const cases: Array<[string, number, number]> = [
    ["start", 0.0, 0],
    ["just before the switch point", 0.0249, 0],
    ["at the switch point", 0.025, 1],
    ["exactly frame 1", 1 / 30, 1],
    ["middle of frame 1", 0.05, 1],
    ["near the end", 29.99, 899],
    ["past the end", 31.0, 899],
    ["before 0", -0.5, 0],
    ["just below the next switch", 0.0583, 1],
    ["just above it", 0.0584, 2],
  ];
  it.each(cases)("%s", (_name, m, expected) => {
    expect(frameAt(m, 30, 900)).toBe(expected);
  });

  it("treats a non-finite media time as frame 0", () => {
    expect(frameAt(Number.NaN, 30, 900)).toBe(0);
  });

  it("always lands in [0, frames-1] and round-trips every frame start", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 30 }),
        fc.integer({ min: 1, max: 5000 }),
        fc.double({ min: -100, max: 1000, noNaN: true }),
        (fps, frames, m) => {
          const f = frameAt(m, fps, frames);
          return Number.isInteger(f) && f >= 0 && f < frames;
        },
      ),
      { numRuns: 2000 },
    );
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 30 }), fc.integer({ min: 0, max: 1799 }), (fps, i) => {
        return frameAt(frameStart(i, fps), fps, 1800) === i;
      }),
      { numRuns: 2000 },
    );
  });

  it("is monotonic in media time", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 30 }),
        fc.double({ min: 0, max: 120, noNaN: true }),
        fc.double({ min: 0, max: 120, noNaN: true }),
        (fps, a, b) => {
          const [lo, hi] = a <= b ? [a, b] : [b, a];
          return frameAt(lo, fps, 3600) <= frameAt(hi, fps, 3600);
        },
      ),
      { numRuns: 2000 },
    );
  });
});

describe("display times (UI-SPEC §10.6)", () => {
  it.each([
    [0, "0:00", "0:00.0"],
    [9, "0:00", "0:00.3"],
    [90, "0:03", "0:03.0"],
    [1500, "0:50", "0:50.0"],
    [1977, "1:05", "1:05.9"],
  ])("frame %i", (frame, mss, tenths) => {
    expect(formatFrame(frame, 30)).toBe(mss);
    expect(formatFrameTenths(frame, 30)).toBe(tenths);
  });

  it("never shows a time later than the frame's true start", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 30 }), fc.integer({ min: 0, max: 100000 }), (fps, i) => {
        const [m, s] = formatFrame(i, fps).split(":").map(Number) as [number, number];
        return m * 60 + s <= i / fps + 1e-9;
      }),
      { numRuns: 2000 },
    );
  });

  it("formats seconds and ranges", () => {
    expect(formatSeconds(65.9)).toBe("1:05");
    expect(formatSeconds(-2)).toBe("0:00");
    expect(formatFrameRange(120, 390, 30)).toBe("0:04–0:13");
  });
});

describe("checkTimeline (UI-SPEC §3.6, §10.6)", () => {
  it.each([
    ["CFR source", 30, 4, [0.0, 0.03333333333333333, 0.06666666666666667, 0.1], null],
    ["VFR repeat", 10, 4, [0.0, 0.1, 0.1, 0.26], null],
    ["first frame above 0", 10, 4, [0.04, 0.1, 0.1, 0.1], null],
    ["decreasing", 30, 3, [0.0, 0.1, 0.05], "times_decreasing"],
    ["wrong length", 30, 5, [0.0, 0.03333333333333333, 0.06666666666666667, 0.1], "times_wrong_length"],
    ["not finite (NaN)", 30, 3, [0.0, Number.NaN, 0.06666666666666667], "times_not_finite"],
    ["not finite (null)", 30, 3, [0.0, null, 0.06666666666666667], "times_not_finite"],
    ["fps 29.97", 29.97, 1, [0], "fps_not_integer"],
    ["fps 60", 60, 1, [0], "fps_out_of_range"],
    ["fps 0", 0, 1, [0], "fps_out_of_range"],
    ["no frames", 30, 0, [], "no_frames"],
  ] as const)("%s", (_n, fps, frames, times, expected) => {
    expect(checkTimeline({ fps, frames, times })).toBe(expected);
  });

  it("accepts every non-decreasing finite list of the right length", () => {
    fc.assert(
      fc.property(fc.array(fc.double({ min: 0, max: 100, noNaN: true }), { minLength: 1, maxLength: 300 }), (xs) => {
        const times = [...xs].sort((a, b) => a - b);
        return checkTimeline({ fps: 30, frames: times.length, times }) === null;
      }),
      { numRuns: 1000 },
    );
  });
});
