/**
 * Prepared-clock time helpers (UI-SPEC §0, §3.6, §10.6; PRE-A API-NOTES §5b).
 *
 * The prepared clip has a constant integer frame rate, so prepared frame `i`
 * sits at `i / fps` seconds. Everything on screen uses that clock; `job.times`
 * (source seconds) is only validated here and shown on the receipt.
 */

export const MAX_FPS = 30;

/** Player time (seconds) → prepared frame, with the quarter-frame switch point. */
export function frameAt(mediaTime: number, fps: number, frames: number): number {
  if (!Number.isFinite(mediaTime)) return 0;
  const raw = Math.floor(mediaTime * fps + 0.25);
  return Math.min(Math.max(raw, 0), Math.max(frames - 1, 0));
}

/** Start of a prepared frame on the player's clock, in seconds. */
export function frameStart(frame: number, fps: number): number {
  return frame / fps;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** `m:ss` from a prepared frame, in integer arithmetic so it never rounds up. */
export function formatFrame(frame: number, fps: number): string {
  const whole = Math.floor(frame / fps);
  return `${Math.floor(whole / 60)}:${pad2(whole % 60)}`;
}

/** `m:ss.s` from a prepared frame (the Why drawer's precision). */
export function formatFrameTenths(frame: number, fps: number): string {
  const tenths = Math.floor((10 * frame) / fps);
  const whole = Math.floor(tenths / 10);
  return `${Math.floor(whole / 60)}:${pad2(whole % 60)}.${tenths % 10}`;
}

/** `m:ss` from seconds on the prepared clock (transcript turns). */
export function formatSeconds(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${pad2(whole % 60)}`;
}

/** `m:ss–m:ss` for a frame span. */
export function formatFrameRange(first: number, last: number, fps: number): string {
  return `${formatFrame(first, fps)}–${formatFrame(last, fps)}`;
}

/** Spoken form of a frame span for accessible names ("0:04 to 0:13"). */
export function spokenFrameRange(first: number, last: number, fps: number): string {
  return `${formatFrame(first, fps)} to ${formatFrame(last, fps)}`;
}

export type TimelineProblem =
  | "fps_not_integer"
  | "fps_out_of_range"
  | "no_frames"
  | "times_wrong_length"
  | "times_not_finite"
  | "times_decreasing";

export interface TimelineInput {
  fps: number;
  frames: number;
  times: ReadonlyArray<number | null>;
}

/**
 * The checks §3.6 runs before drawing any overlay. Repeated values and a first
 * time above zero are valid (variable-frame-rate sources); only decreasing,
 * missing or non-finite values fail.
 */
export function checkTimeline({ fps, frames, times }: TimelineInput): TimelineProblem | null {
  if (!Number.isInteger(fps)) return "fps_not_integer";
  if (fps < 1 || fps > MAX_FPS) return "fps_out_of_range";
  if (!Number.isInteger(frames) || frames < 1) return "no_frames";
  if (times.length !== frames) return "times_wrong_length";
  let previous = Number.NEGATIVE_INFINITY;
  for (const t of times) {
    if (t === null || !Number.isFinite(t)) return "times_not_finite";
    if (t < previous) return "times_decreasing";
    previous = t;
  }
  return null;
}
