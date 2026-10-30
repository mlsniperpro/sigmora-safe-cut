/**
 * COCO run-length masks (WP0 `Rle`: `size` is [height, width], `counts` the compressed string
 * pycocotools writes). The overlay fills a region's mask shape when it has one (UI-SPEC §3.6).
 */
import type { Rle } from "./contracts";

/** pycocotools `rleFrString`: 6-bit groups offset by 48, 5 data bits each, sign bit on the last. */
export function decodeCounts(s: string): number[] {
  const counts: number[] = [];
  let p = 0;
  while (p < s.length) {
    let x = 0;
    let k = 0;
    let more = true;
    while (more) {
      if (p >= s.length) throw new Error("truncated RLE counts");
      const c = s.charCodeAt(p) - 48;
      if (c < 0 || c > 63) throw new Error("bad RLE character");
      x |= (c & 0x1f) << (5 * k);
      more = (c & 0x20) !== 0;
      p += 1;
      k += 1;
      if (!more && c & 0x10) x |= -1 << (5 * k);
    }
    if (counts.length > 2) x += counts[counts.length - 2]!;
    counts.push(x);
  }
  return counts;
}

/** A vertical run of mask pixels: column `x`, rows `y` to `y + h - 1`. */
export type Run = readonly [x: number, y: number, h: number];

/**
 * The mask's covered pixels as vertical runs (COCO masks are column-major), or null when the
 * counts don't describe a `size` mask: the caller then covers the whole box instead.
 */
export function maskRuns(rle: Rle): Run[] | null {
  const [height, width] = rle.size;
  let counts: number[];
  try {
    counts = decodeCounts(rle.counts);
  } catch {
    return null;
  }
  const total = height * width;
  const runs: Run[] = [];
  let at = 0;
  for (let i = 0; i < counts.length; i++) {
    const n = counts[i]!;
    if (n < 0 || at + n > total) return null;
    // Runs alternate, starting with background.
    if (i % 2 === 1) {
      let left = n;
      let pos = at;
      while (left > 0) {
        const x = Math.floor(pos / height);
        const y = pos % height;
        const h = Math.min(left, height - y);
        runs.push([x, y, h]);
        pos += h;
        left -= h;
      }
    }
    at += n;
  }
  return at === total ? runs : null;
}

const CACHE_MAX = 256;
const cache = new Map<string, Run[] | null>();

/** `maskRuns`, decoded once per mask: the overlay asks for the same masks on every frame. */
export function cachedMaskRuns(rle: Rle): Run[] | null {
  const key = `${rle.size[0]}x${rle.size[1]}:${rle.counts}`;
  if (cache.has(key)) {
    const hit = cache.get(key) ?? null;
    cache.delete(key);
    cache.set(key, hit);
    return hit;
  }
  const runs = maskRuns(rle);
  cache.set(key, runs);
  if (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value!);
  return runs;
}
