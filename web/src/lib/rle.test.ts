import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { cachedMaskRuns, decodeCounts, maskRuns } from "./rle";

/** pycocotools `rleEncode` + `rleToString`, written independently of the decoder under test. */
function encode(mask: boolean[][]): { size: [number, number]; counts: string } {
  const h = mask.length;
  const w = mask[0]?.length ?? 0;
  const counts: number[] = [];
  let current = false;
  let run = 0;
  for (let x = 0; x < w; x++) {
    for (let y = 0; y < h; y++) {
      if (mask[y]![x] !== current) {
        counts.push(run);
        run = 0;
        current = !current;
      }
      run += 1;
    }
  }
  counts.push(run);
  let s = "";
  counts.forEach((c, i) => {
    let x = i > 2 ? c - counts[i - 2]! : c;
    let more = true;
    while (more) {
      let ch = x & 0x1f;
      x >>= 5;
      more = ch & 0x10 ? x !== -1 : x !== 0;
      if (more) ch |= 0x20;
      s += String.fromCharCode(ch + 48);
    }
  });
  return { size: [h, w], counts: s };
}

function paint(h: number, w: number, runs: ReadonlyArray<readonly [number, number, number]>): boolean[][] {
  const out = Array.from({ length: h }, () => Array<boolean>(w).fill(false));
  for (const [x, y, n] of runs) for (let i = 0; i < n; i++) out[y + i]![x] = true;
  return out;
}

describe("COCO RLE masks", () => {
  it("decodes what pycocotools' encoder writes, pixel for pixel", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 12 }).chain((h) => fc.integer({ min: 1, max: 12 }).chain((w) => fc.array(fc.array(fc.boolean(), { minLength: w, maxLength: w }), { minLength: h, maxLength: h }))),
        (mask) => {
          const rle = encode(mask);
          const runs = maskRuns(rle);
          expect(runs).not.toBeNull();
          expect(paint(rle.size[0], rle.size[1], runs!)).toEqual(mask);
        },
      ),
      { numRuns: 2_000 },
    );
  });

  it("handles long runs (multi-character counts) and negative deltas", () => {
    const h = 300;
    const w = 200;
    const mask = Array.from({ length: h }, (_, y) => Array.from({ length: w }, (_, x) => x > 50 && x < 120 && y > 20 && y < 260));
    const rle = encode(mask);
    expect(rle.counts.length).toBeGreaterThan(5);
    expect(paint(h, w, maskRuns(rle)!)).toEqual(mask);
    expect(decodeCounts(rle.counts)[0]).toBe(51 * h + 21);
  });

  it("refuses counts that don't describe the mask, so the caller covers the whole box", () => {
    expect(maskRuns({ size: [4, 4], counts: "3" })).toBeNull(); // too short
    expect(maskRuns({ size: [2, 2], counts: "0;" })).toBeNull(); // runs past the end
    expect(maskRuns({ size: [2, 2], counts: "\u0001" })).toBeNull(); // not an RLE character
    expect(maskRuns({ size: [2, 2], counts: "p" })).toBeNull(); // truncated: continuation bit, then nothing
  });

  it("caches decoded masks by content", () => {
    const rle = encode([[true, false], [false, true]]);
    expect(cachedMaskRuns({ ...rle })).toBe(cachedMaskRuns({ ...rle }));
  });
});
