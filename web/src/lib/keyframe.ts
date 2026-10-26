/**
 * Keyframe geometry (UI-SPEC §4.3): the Set-of-Mark image is the prepared frame
 * at its own size under a `bar_h`-pixel bar, so a track box maps into it by
 * shifting down `bar_h`, then scaling to the displayed width.
 */
import type { Box, KeyframeGeometry } from "./contracts";

export interface NaturalSize {
  width: number;
  height: number;
}

/** True only when every §4.3 check holds; otherwise the drawer hides the ring. */
export function geometryMatches(g: KeyframeGeometry | undefined, job: { width: number; height: number }, natural: NaturalSize): boolean {
  if (!g) return false;
  return (
    g.frame_width === job.width &&
    g.frame_height === job.height &&
    g.image_width === g.frame_width &&
    g.image_height === g.frame_height + g.bar_h &&
    natural.width === g.image_width &&
    natural.height === g.image_height
  );
}

/** A prepared-frame box → on-screen pixels in an image displayed `displayWidth` wide. */
export function ringOnScreen(box: Box, g: KeyframeGeometry, displayWidth: number): Box {
  const s = displayWidth / g.image_width;
  const [x1, y1, x2, y2] = box;
  return [x1 * s, (y1 + g.bar_h) * s, x2 * s, (y2 + g.bar_h) * s];
}

/**
 * The thumbnail crop around an item (UI-SPEC §3.3): about twice the item's box,
 * square, clamped to the frame, in keyframe-image pixels.
 */
export function thumbnailCrop(box: Box, g: KeyframeGeometry): Box {
  const [x1, y1, x2, y2] = box;
  const side = Math.min(Math.max(x2 - x1, y2 - y1) * 2, g.frame_width, g.frame_height);
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const left = Math.min(Math.max(cx - side / 2, 0), g.frame_width - side);
  const top = Math.min(Math.max(cy - side / 2, 0), g.frame_height - side);
  return [left, top + g.bar_h, left + side, top + g.bar_h + side];
}

/** Where on the image a label sits, in plain words for alt text ("in the back right"). */
export function regionWords(box: Box, width: number, height: number): string {
  const cx = (box[0] + box[2]) / 2 / width;
  const cy = (box[1] + box[3]) / 2 / height;
  const h = cx < 1 / 3 ? "left" : cx > 2 / 3 ? "right" : "centre";
  const v = cy < 1 / 3 ? "top" : cy > 2 / 3 ? "bottom" : "middle";
  if (v === "middle") return h === "centre" ? "in the centre" : `on the ${h}`;
  return `in the ${v} ${h}`;
}
