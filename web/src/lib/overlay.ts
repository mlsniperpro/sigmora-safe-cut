/**
 * The review overlay (UI-SPEC §3.6): which shapes to draw on a prepared frame,
 * given the plan and the creator's local edits, and how to draw them.
 */
import type { Box, Plan, Style, Track } from "./contracts";

export const MAX_REGIONS = 200;
const LOCAL_PAD = 0.15;

export type OverlayOp =
  | { kind: "cover"; box: Box; style: Style; grid: [number, number, number] | null }
  | { kind: "fill"; box: Box }
  | { kind: "outline"; box: Box; label: string; selected: boolean }
  | { kind: "spot"; box: Box; label: string };

export interface OverlayInput {
  frame: number;
  plan: Plan;
  /** Hidden or needs-you after local edits (merged items follow their target). */
  isCovered: (itemId: string) => boolean;
  /** Items the creator hid that the server hasn't planned yet, with their track IDs. */
  unplanned: ReadonlyArray<{ itemId: string; trackIds: readonly string[] }>;
  /** Visible items and their tracks, for outlines in Raw mode and for the selection. */
  items: ReadonlyArray<{ itemId: string; label: string; trackIds: readonly string[] }>;
  tracks: ReadonlyMap<string, Pick<Track, "boxes">>;
  spots: ReadonlyArray<{ label: string; first: number; last: number; boxes: Record<string, Box> }>;
  mode: "safecut" | "raw";
  selected: string | null;
  width: number;
  height: number;
}

function pad([x1, y1, x2, y2]: Box, frac: number, width: number, height: number): Box {
  const dx = (x2 - x1) * frac;
  const dy = (y2 - y1) * frac;
  return [Math.max(0, x1 - dx), Math.max(0, y1 - dy), Math.min(width, x2 + dx), Math.min(height, y2 + dy)];
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
    for (const fill of plan.crowd_fills) if (fill.frames.includes(frame)) ops.push({ kind: "fill", box: fill.box });
    for (const r of plan.frames[String(frame)] ?? []) {
      if (input.isCovered(r.item_id)) ops.push({ kind: "cover", box: r.box, style: r.style, grid: r.grid ?? null });
    }
    for (const u of input.unplanned) {
      for (const box of boxesOn(u.trackIds, tracks, frame)) ops.push({ kind: "cover", box: pad(box, LOCAL_PAD, input.width, input.height), style: "solid", grid: null });
    }
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

let scratch: HTMLCanvasElement | null = null;

/**
 * Draws the ops onto a canvas sized to the video's displayed box. Boxes are in
 * prepared-frame pixels; `scale` maps them to canvas pixels.
 */
export function drawOverlay(ctx: CanvasRenderingContext2D, video: CanvasImageSource | null, ops: readonly OverlayOp[], scale: number): void {
  const s = (b: Box): Box => [b[0] * scale, b[1] * scale, b[2] * scale, b[3] * scale];
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  for (const op of ops) {
    if (op.kind === "fill" || (op.kind === "cover" && (op.style !== "pixelate" || !op.grid || !video))) {
      const [x1, y1, x2, y2] = s(op.box);
      ctx.fillStyle = "#18181b";
      ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
    } else if (op.kind === "cover" && op.grid && video) {
      drawPixelated(ctx, video, op.box, op.grid, scale);
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

/** Coarse cells locked to the item's grid, so they don't shift between frames (DESIGN §2.7). */
function drawPixelated(ctx: CanvasRenderingContext2D, video: CanvasImageSource, box: Box, [gx, gy, cell]: [number, number, number], scale: number): void {
  const x0 = gx + Math.floor((box[0] - gx) / cell) * cell;
  const y0 = gy + Math.floor((box[1] - gy) / cell) * cell;
  const cols = Math.max(1, Math.ceil((box[2] - x0) / cell));
  const rows = Math.max(1, Math.ceil((box[3] - y0) / cell));
  scratch ??= document.createElement("canvas");
  scratch.width = cols;
  scratch.height = rows;
  const small = scratch.getContext("2d");
  if (!small) return;
  small.imageSmoothingEnabled = true;
  small.drawImage(video, x0, y0, cols * cell, rows * cell, 0, 0, cols, rows);
  ctx.save();
  ctx.beginPath();
  ctx.rect(box[0] * scale, box[1] * scale, (box[2] - box[0]) * scale, (box[3] - box[1]) * scale);
  ctx.clip();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(scratch, 0, 0, cols, rows, x0 * scale, y0 * scale, cols * cell * scale, rows * cell * scale);
  ctx.restore();
}
