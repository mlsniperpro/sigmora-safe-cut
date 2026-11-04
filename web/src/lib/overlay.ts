/**
 * The review overlay (UI-SPEC §3.6): which shapes to draw on a prepared frame,
 * given the plan and the creator's local edits, and how to draw them.
 */
import type { Box, Plan, Style, Track } from "./contracts";
import { cachedMaskRuns, type Run } from "./rle";

export const MAX_REGIONS = 200;
/** The guard's face padding (DESIGN §2.6): 15 % of the box each side plus 8 px. */
const FACE_PAD = 0.15;
const PAD_PX = 8;
/** DESIGN §2.7: a face spans 4 mosaic cells (the guard's `MAX_BLOCKS`). */
const MAX_BLOCKS = 4;
/** The renderer's per-cell noise amplitude (draw.py `NOISE`), in levels. */
const NOISE = 24;
/** draw.py's frosted finish: haze share and level, blur sigma (px), cells across an object. */
const HAZE = 0.35;
const HAZE_LEVEL = 225;
const FROST_SIGMA = 4;
const OBJECT_BLOCKS = 4;
/** DESIGN §2.7: a head estimate is the top of a body box, min(0.22·h, 0.9·w) tall. */
const HEAD_SHARE = 0.22;
const HEAD_ASPECT = 0.9;

type Grid = [number, number, number];

export type OverlayOp =
  | { kind: "cover"; box: Box; style: Style; grid: Grid | null; mask?: Run[] | null; clear?: Box[] }
  | { kind: "fill"; box: Box }
  | { kind: "outline"; box: Box; label: string; selected: boolean }
  | { kind: "spot"; box: Box; label: string };

export interface OverlayInput {
  frame: number;
  plan: Plan;
  /** Hidden or needs-you after local edits (merged items follow their target). */
  isCovered: (itemId: string) => boolean;
  /** Items the creator hid that the server hasn't planned yet, with their track IDs (`whole`: Remove person). */
  unplanned: ReadonlyArray<{ itemId: string; trackIds: readonly string[]; whole?: boolean }>;
  /** Visible items and their tracks, for outlines in Raw mode and for the selection. */
  items: ReadonlyArray<{ itemId: string; label: string; trackIds: readonly string[] }>;
  tracks: ReadonlyMap<string, Pick<Track, "boxes">>;
  spots: ReadonlyArray<{ label: string; first: number; last: number; boxes: Record<string, Box> }>;
  mode: "safecut" | "raw";
  selected: string | null;
  width: number;
  height: number;
}

/** The guard's `grow`: `frac` of the box each side plus `px`, rounded outward, clamped to the frame. */
function pad([x1, y1, x2, y2]: Box, frac: number, width: number, height: number, px = PAD_PX): Box {
  const dx = Math.ceil((x2 - x1) * frac) + px;
  const dy = Math.ceil((y2 - y1) * frac) + px;
  return [Math.max(0, x1 - dx), Math.max(0, y1 - dy), Math.min(width, x2 + dx), Math.min(height, y2 + dy)];
}

/** The head estimate of a body box (DESIGN §2.7), as the guard draws it where no face is seen. */
export function headBox([x1, y1, x2, y2]: Box): Box {
  const tall = Math.ceil(Math.min(HEAD_SHARE * (y2 - y1), HEAD_ASPECT * (x2 - x1)));
  return [x1, y1, x2, Math.min(y2, y1 + Math.max(1, tall))];
}

/** The item's locked mosaic grid, as the guard builds it: origin at its earliest face's padded first box, cells
 * sized so its widest face spans at most 6 (DESIGN §2.7). Null without a face track. */
function lockedGrid(trackIds: readonly string[], tracks: OverlayInput["tracks"], width: number, height: number): Grid | null {
  let first: { frame: number; box: Box } | null = null;
  let widest = 0;
  for (const id of trackIds.filter((t) => t.startsWith("face:"))) {
    for (const [key, box] of Object.entries(tracks.get(id)?.boxes ?? {})) {
      const frame = Number(key);
      if (!first || frame < first.frame) first = { frame, box };
      widest = Math.max(widest, box[2] - box[0]);
    }
  }
  if (!first) return null;
  const [x0, y0] = pad(first.box, FACE_PAD, width, height);
  return [x0, y0, Math.max(2, Math.ceil(widest / MAX_BLOCKS))];
}

function union(boxes: readonly Box[]): Box | null {
  if (boxes.length === 0) return null;
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ];
}

function boxesOn(trackIds: readonly string[], tracks: OverlayInput["tracks"], frame: number): Box[] {
  const key = String(frame);
  const out: Box[] = [];
  for (const id of trackIds) {
    const box = tracks.get(id)?.boxes[key];
    if (box) out.push(box);
  }
  return out;
}

/** The face box if the item has one on this frame, else the union of its boxes. */
function itemBox(trackIds: readonly string[], tracks: OverlayInput["tracks"], frame: number): Box | null {
  const faces = boxesOn(trackIds.filter((t) => t.startsWith("face:")), tracks, frame);
  return union(faces.length ? faces : boxesOn(trackIds, tracks, frame));
}

export function overlayOps(input: OverlayInput): OverlayOp[] {
  const ops: OverlayOp[] = [];
  const { frame, plan, tracks } = input;
  if (input.mode === "safecut") {
    for (const r of plan.frames[String(frame)] ?? []) {
      if (!input.isCovered(r.item_id)) continue;
      // Covers take the mask's shape when there is one, mosaics too, as the renderer draws them (§3.6). A mask
      // that doesn't decode, or isn't frame-sized, covers its whole box instead: never less than the box promises.
      const sized = r.mask && r.mask.size[0] === input.height && r.mask.size[1] === input.width;
      const mask = r.shape === "mask" && sized && r.mask ? cachedMaskRuns(r.mask) : null;
      const clear = r.keep_clear?.length ? r.keep_clear : null;
      ops.push({ kind: "cover", box: r.box, style: r.style, grid: r.grid ?? null, ...(mask && { mask }), ...(clear && { clear }) });
    }
    for (const u of input.unplanned) ops.push(...unplannedOps(u, tracks, frame, input.width, input.height));
    for (const fill of plan.crowd_fills) if (fill.frames.includes(frame)) ops.push({ kind: "fill", box: fill.box });
  } else {
    for (const item of input.items) {
      if (item.itemId === input.selected) continue;
      const box = itemBox(item.trackIds, tracks, frame);
      if (box) ops.push({ kind: "outline", box, label: item.label, selected: false });
    }
  }
  for (const spot of input.spots) {
    if (frame < spot.first || frame > spot.last) continue;
    const box = spot.boxes[String(frame)];
    if (box) ops.push({ kind: "spot", box, label: spot.label });
  }
  const selected = input.items.find((i) => i.itemId === input.selected);
  if (selected) {
    const box = itemBox(selected.trackIds, tracks, frame);
    if (box) ops.push({ kind: "outline", box, label: selected.label, selected: true });
  }
  // Covers first (they matter most), then outlines; never more than the cap.
  return ops.slice(0, MAX_REGIONS);
}

/** A locally hidden item before the server plans it, drawn as the guard will: its faces as the mosaic, else a head
 * estimate over each body (solid with no face to size a grid); the whole body only for Remove person. */
function unplannedOps(u: OverlayInput["unplanned"][number], tracks: OverlayInput["tracks"], frame: number, width: number, height: number): OverlayOp[] {
  const faces = boxesOn(u.trackIds.filter((t) => t.startsWith("face:")), tracks, frame);
  const bodies = boxesOn(u.trackIds.filter((t) => !t.startsWith("face:")), tracks, frame);
  if (u.whole) {
    return [...faces.map((b) => pad(b, FACE_PAD, width, height)), ...bodies.map((b) => pad(b, 0.08, width, height))].map((box) => ({ kind: "cover", box, style: "person_solid", grid: null }));
  }
  const grid = lockedGrid(u.trackIds, tracks, width, height);
  const boxes = faces.length ? faces : bodies.map(headBox);
  return boxes.map((b) => ({ kind: "cover", box: pad(b, FACE_PAD, width, height), style: grid ? "pixelate" : "solid", grid }));
}

let scratch: HTMLCanvasElement | null = null;
let layer: HTMLCanvasElement | null = null;

/**
 * Draws the ops onto a canvas sized to the video's displayed box. Boxes are in
 * prepared-frame pixels; `scale` maps them to canvas pixels.
 */
export function drawOverlay(ctx: CanvasRenderingContext2D, video: CanvasImageSource | null, ops: readonly OverlayOp[], scale: number): void {
  const s = (b: Box): Box => [b[0] * scale, b[1] * scale, b[2] * scale, b[3] * scale];
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  // The renderer's order (draw.py): mosaics from the untouched frame, then solids, then crowd fills.
  const rank = (op: OverlayOp): number => (op.kind === "fill" ? 2 : op.kind === "cover" && op.style === "pixelate" ? 0 : 1);
  const covers = ops.filter((op) => op.kind === "cover" || op.kind === "fill").sort((a, b) => rank(a) - rank(b));
  for (const op of covers) {
    if (op.kind === "cover" && op.clear) {
      // A cover that leaves kept faces clear is drawn on its own layer, those faces cut out, then laid on top.
      layer ??= document.createElement("canvas");
      layer.width = ctx.canvas.width;
      layer.height = ctx.canvas.height;
      const lctx = layer.getContext("2d");
      if (!lctx) continue;
      paint(lctx, video, op, scale);
      for (const c of op.clear) {
        const [x1, y1, x2, y2] = s(c);
        lctx.clearRect(x1, y1, x2 - x1, y2 - y1);
      }
      ctx.drawImage(layer, 0, 0);
    } else {
      paint(ctx, video, op, scale);
    }
  }
  for (const op of ops) {
    if (op.kind !== "outline" && op.kind !== "spot") continue;
    const [x1, y1, x2, y2] = s(op.box);
    const thick = op.kind === "outline" && op.selected ? 3 : 2;
    ctx.lineWidth = thick + 2;
    ctx.strokeStyle = "#111";
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    ctx.lineWidth = thick;
    ctx.strokeStyle = op.kind === "spot" ? "#fbbf24" : "#ffffff";
    if (op.kind === "spot") ctx.setLineDash([6, 4]);
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    ctx.setLineDash([]);
    ctx.font = "600 13px system-ui, sans-serif";
    const w = ctx.measureText(op.label).width + 8;
    const ty = Math.max(0, y1 - 20);
    ctx.fillStyle = "#111";
    ctx.fillRect(x1, ty, w, 18);
    ctx.fillStyle = "#fff";
    ctx.fillText(op.label, x1 + 4, ty + 13);
  }
}

/** One cover or crowd fill, as the renderer paints it (draw.py, owner 2026-11-04): frosted. Cells on the item's
 * locked grid (else about 4 across the region) take the region's mean colour lifted toward a light haze plus a fixed
 * per-cell noise, blurred, inside the region's mask runs (or box). Never a dark block. */
function paint(ctx: CanvasRenderingContext2D, video: CanvasImageSource | null, op: OverlayOp, scale: number): void {
  if (op.kind !== "cover" && op.kind !== "fill") return;
  const box = op.box;
  const grid = op.kind === "cover" && op.style === "pixelate" && op.grid ? op.grid : null;
  drawFrosted(ctx, video, box, grid, scale, op.kind === "cover" ? (op.mask ?? null) : null);
}

/** The region's mean colour (from the video when it has a frame), lifted toward the haze. */
function hazeOf(video: CanvasImageSource | null, box: Box): [number, number, number] {
  let mean: [number, number, number] = [HAZE_LEVEL, HAZE_LEVEL, HAZE_LEVEL];
  if (video) {
    scratch ??= document.createElement("canvas");
    scratch.width = 1;
    scratch.height = 1;
    const small = scratch.getContext("2d", { willReadFrequently: true });
    if (small) {
      try {
        small.imageSmoothingEnabled = true;
        small.drawImage(video, box[0], box[1], Math.max(1, box[2] - box[0]), Math.max(1, box[3] - box[1]), 0, 0, 1, 1);
        const [r, g, b] = small.getImageData(0, 0, 1, 1).data;
        mean = [r ?? HAZE_LEVEL, g ?? HAZE_LEVEL, b ?? HAZE_LEVEL];
      } catch {
        // A cross-origin video taints the canvas (no pixel reads): the preview frosts in the plain haze instead.
      }
    }
  }
  return [0, 1, 2].map((i) => (1 - HAZE) * (mean[i] ?? HAZE_LEVEL) + HAZE * HAZE_LEVEL) as [number, number, number];
}

function drawFrosted(ctx: CanvasRenderingContext2D, video: CanvasImageSource | null, box: Box, grid: Grid | null, scale: number, mask: Run[] | null): void {
  const [gx, gy, cell] = grid ?? [box[0], box[1], Math.max(2, Math.ceil(Math.min(box[2] - box[0], box[3] - box[1]) / OBJECT_BLOCKS))];
  const [r, g, b] = hazeOf(video, box);
  const x0 = gx + Math.floor((box[0] - gx) / cell) * cell;
  const y0 = gy + Math.floor((box[1] - gy) / cell) * cell;
  ctx.save();
  ctx.beginPath();
  if (mask) for (const [x, y, h] of mask) ctx.rect(x * scale, y * scale, Math.ceil(scale) + 0.5, h * scale + 0.5);
  else ctx.rect(box[0] * scale, box[1] * scale, (box[2] - box[0]) * scale, (box[3] - box[1]) * scale);
  ctx.clip();
  ctx.filter = `blur(${Math.max(1, FROST_SIGMA * scale)}px)`;
  for (let y = y0; y < box[3]; y += cell) {
    for (let x = x0; x < box[2]; x += cell) {
      const n = cellNoise((x - gx) / cell, (y - gy) / cell);
      ctx.fillStyle = `rgb(${clampByte(r + n[0])}, ${clampByte(g + n[1])}, ${clampByte(b + n[2])})`;
      ctx.fillRect(x * scale, y * scale, cell * scale + 0.5, cell * scale + 0.5);
    }
  }
  ctx.restore();
}

function clampByte(v: number): number {
  return Math.max(0, Math.min(255, Math.round(v)));
}

/** A fixed noise per cell and channel in [-NOISE, NOISE] (a preview of draw.py's; the same per frame, never random). */
function cellNoise(col: number, row: number): [number, number, number] {
  const out: [number, number, number] = [0, 0, 0];
  for (let ch = 0; ch < 3; ch++) {
    let h = (Math.imul(col | 0, 73856093) ^ Math.imul(row | 0, 19349663) ^ Math.imul(ch + 1, 83492791)) >>> 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
    out[ch] = (h % (2 * NOISE + 1)) - NOISE;
  }
  return out;
}
