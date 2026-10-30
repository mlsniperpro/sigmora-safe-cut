import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { rewriteFrameRefs } from "./rewrite";

const clock = { fps: 30, frames: 900 };

describe("rewriteFrameRefs (UI-SPEC §10.6 evidence rewrite)", () => {
  it.each([
    ["introduced at F 000090, speaks to camera", "introduced at 0:03, speaks to camera"],
    ["speaks to camera at frames 120–600", "speaks to camera at 0:04–0:20"],
    ["waves at F90 and F120", "waves at 0:03 and 0:04"],
    ["looks at the camera at frame 9, never speaks", "looks at the camera at 0:00, never speaks"],
    ["Face 7 is the host", "Face 7 is the host"],
    ["seen at F 001200", "seen at F 001200"],
    ["possible missed object at F420", "possible missed object at 0:14"],
    ["background, never addressed", "background, never addressed"],
    ["introduced at frame 90, speaks to camera 120–600", "introduced at 0:03, speaks to camera 0:04–0:20"],
    ["seen in frames 90 and 120", "seen in 0:03 and 0:04"],
    ["frames 90, 120 and 150, never addressed", "0:03, 0:04 and 0:05, never addressed"],
    ["at F 000090 with 2–3 people nearby", "at 0:03 with 2–3 people nearby"],
    ["speaks at 120", "speaks at 120"],
    ["at frame 90. Later 120–240", "at 0:03. Later 120–240"],
    ["frames 240-600", "0:08–0:20"],
  ])("%s", (input, expected) => {
    expect(rewriteFrameRefs(input, clock)).toBe(expected);
  });

  it("leaves a list alone when one of its frames is out of range", () => {
    expect(rewriteFrameRefs("frames 90 and 1200", clock)).toBe("frames 90 and 1200");
  });

  it("is case-insensitive and handles 'F 000000'", () => {
    expect(rewriteFrameRefs("Frame 30; f 000000", clock)).toBe("0:01; 0:00");
  });

  it("never throws, never leaves placeholders, and is a no-op on text without digits", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 120 }), (s) => {
        const out = rewriteFrameRefs(s, clock);
        if (out.includes("\u0000") && !s.includes("\u0000")) return false;
        return /\d/.test(s) || out === s;
      }),
      { numRuns: 3000 },
    );
  });

  it("converts any valid F label to its m:ss time", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 899 }), (f) => {
        const mm = Math.floor(Math.floor(f / 30) / 60);
        const ss = String(Math.floor(f / 30) % 60).padStart(2, "0");
        return rewriteFrameRefs(`at F ${String(f).padStart(6, "0")}`, clock) === `at ${mm}:${ss}`;
      }),
      { numRuns: 900 },
    );
  });
});
