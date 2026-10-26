import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { geometryMatches, regionWords, ringOnScreen, thumbnailCrop } from "./keyframe";

const g = { bar_h: 40, frame_width: 1280, frame_height: 720, image_width: 1280, image_height: 760 };
const job = { width: 1280, height: 720 };

describe("keyframe geometry (UI-SPEC §4.3)", () => {
  it("maps the spec's test case", () => {
    expect(ringOnScreen([600, 200, 660, 250], g, 640)).toEqual([300, 120, 330, 145]);
  });

  it("accepts only a fully consistent geometry", () => {
    expect(geometryMatches(g, job, { width: 1280, height: 760 })).toBe(true);
    expect(geometryMatches(g, job, { width: 1280, height: 720 })).toBe(false);
    expect(geometryMatches({ ...g, image_height: 720 }, job, { width: 1280, height: 720 })).toBe(false);
    expect(geometryMatches(g, { width: 1920, height: 1080 }, { width: 1280, height: 760 })).toBe(false);
    expect(geometryMatches(undefined, job, { width: 1280, height: 760 })).toBe(false);
  });

  it("crops a square inside the frame part of the image", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 1270 }), fc.integer({ min: 0, max: 710 }), fc.integer({ min: 1, max: 600 }), fc.integer({ min: 1, max: 600 }), (x, y, w, h) => {
        const box: [number, number, number, number] = [x, y, Math.min(1280, x + w), Math.min(720, y + h)];
        const [l, t, r, b] = thumbnailCrop(box, g);
        return l >= 0 && t >= 40 && r <= 1280 + 1e-9 && b <= 760 + 1e-9 && Math.abs(r - l - (b - t)) < 1e-9;
      }),
      { numRuns: 2000 },
    );
  });

  it("describes positions in words", () => {
    expect(regionWords([900, 200, 940, 250], 1280, 720)).toBe("in the top right");
    expect(regionWords([600, 340, 680, 380], 1280, 720)).toBe("in the centre");
    expect(regionWords([10, 340, 60, 380], 1280, 720)).toBe("on the left");
  });
});
