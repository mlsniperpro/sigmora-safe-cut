"use client";
/**
 * The review player (UI-SPEC §3.6): the raw prepared clip with the redaction
 * preview drawn on a canvas, frame-accurate via requestVideoFrameCallback.
 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { drawOverlay, overlayOps, type OverlayInput } from "@/lib/overlay";
import { frameAt, frameStart } from "@/lib/time";

export interface VideoPaneHandle {
  seekToFrame: (frame: number) => void;
  togglePlay: () => void;
}

export interface VideoPaneProps {
  src: string | undefined;
  captionsUrl: string | null;
  /** Called once when the video fails to load: a fresh GET brings fresh signed URLs (§10.7). */
  onMediaError?: () => void;
  fps: number;
  frames: number;
  width: number;
  height: number;
  overlay: Omit<OverlayInput, "frame" | "mode" | "width" | "height">;
  timeline: ReadonlyArray<{ id: string; first: number; last: number; covered: boolean }>;
  selected: string | null;
}

const noSubscribe = () => () => undefined;

/** How long a media error waits for a fresh URL before the player gives up (§10.7). */
export const FRESH_URL_WAIT_MS = 10_000;

export const TIMELINE_ROWS = 24;

/** The timeline's rows: the first `TIMELINE_ROWS` items, the last swapped for the selection if it's further down. */
export function timelineRows<T extends { id: string }>(timeline: readonly T[], selected: string | null): T[] {
  const rows = timeline.slice(0, TIMELINE_ROWS);
  if (!selected || rows.some((t) => t.id === selected)) return rows;
  const pick = timeline.find((t) => t.id === selected);
  return pick ? [...rows.slice(0, TIMELINE_ROWS - 1), pick] : rows;
}

export const VideoPane = forwardRef<VideoPaneHandle, VideoPaneProps>(function VideoPane(props, ref) {
  const { src, captionsUrl, fps, frames, width, height, timeline, selected, onMediaError } = props;
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [mode, setMode] = useState<"safecut" | "raw">("safecut");
  const rvfc = useSyncExternalStore(
    noSubscribe,
    () => "requestVideoFrameCallback" in HTMLVideoElement.prototype,
    () => true,
  );
  const [failed, setFailed] = useState(false);
  /** The src we already asked to refresh, so an expired URL gets exactly one retry. */
  const [refreshedFor, setRefreshedFor] = useState<string | null>(null);
  /**
   * The src the player is using. A fresher URL in props (a background refresh) doesn't replace it,
   * because that would reload the video from 0:00; it's taken only when the player has none yet or
   * after an error.
   */
  const [playing, setPlaying] = useState(src);
  if (src && (!playing || (refreshedFor !== null && src !== refreshedFor && src !== playing))) {
    setPlaying(src);
    // A fresh URL that came after the wait gave up (a slow refetch) still gets its try.
    if (failed) setFailed(false);
  }
  // Asked for a fresh URL but none came (the refetch gave back the same one): say the video
  // didn't load rather than leave a dead player.
  useEffect(() => {
    if (refreshedFor === null || playing !== refreshedFor) return;
    const t = setTimeout(() => setFailed(true), FRESH_URL_WAIT_MS);
    return () => clearTimeout(t);
  }, [refreshedFor, playing]);
  const latest = useRef({ props, mode });
  useLayoutEffect(() => {
    latest.current = { props, mode };
  });
  const frameRef = useRef(0);

  const draw = useCallback((mediaTime: number) => {
    const c = canvas.current;
    const v = video.current;
    if (!c || !v) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const { props: p, mode: m } = latest.current;
    const frame = frameAt(mediaTime, p.fps, p.frames);
    frameRef.current = frame;
    const ops = overlayOps({ ...p.overlay, frame, mode: m, width: p.width, height: p.height });
    drawOverlay(ctx, v.readyState >= 2 ? v : null, ops, c.width / p.width);
  }, []);

  // Keep the canvas the size of the displayed video, in device pixels.
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const resize = () => {
      const rect = c.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      c.width = Math.max(1, Math.round(rect.width * dpr));
      c.height = Math.max(1, Math.round(rect.height * dpr));
      draw(video.current?.currentTime ?? 0);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(c);
    resize();
    return () => ro.disconnect();
  }, [draw]);

  // Redraw on every presented frame; fall back to rAF on browsers without rVFC, and say so.
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    let handle = 0;
    let stopped = false;
    if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
      const loop: VideoFrameRequestCallback = (_now, meta) => {
        if (stopped) return;
        draw(meta.mediaTime);
        handle = v.requestVideoFrameCallback(loop);
      };
      handle = v.requestVideoFrameCallback(loop);
      return () => {
        stopped = true;
        v.cancelVideoFrameCallback(handle);
      };
    }
    const tick = () => {
      if (stopped) return;
      draw(v.currentTime);
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => {
      stopped = true;
      cancelAnimationFrame(handle);
    };
  }, [draw, playing]);

  // Redraw when edits, selection or the toggle change while paused.
  useEffect(() => {
    draw(video.current?.currentTime ?? 0);
  }, [draw, props.overlay, mode, selected]);

  useImperativeHandle(
    ref,
    () => ({
      seekToFrame(frame: number) {
        const v = video.current;
        if (!v) return;
        v.pause();
        // Aim at the middle of the frame so the quarter-frame switch point lands on it.
        v.currentTime = frameStart(frame, fps) + 0.5 / fps;
        draw(v.currentTime);
      },
      togglePlay() {
        const v = video.current;
        if (!v) return;
        if (v.paused) void v.play().catch(() => undefined);
        else v.pause();
      },
    }),
    [draw, fps],
  );

  return (
    // Desktop (§3.1): the player on the left with the Raw/Safe Cut switch beside it, at most 40% of the
    // viewport tall, so the chip columns start on the first screen and the preview stays in view.
    <div
      className="lg:grid lg:grid-cols-[auto_minmax(0,1fr)] lg:items-start lg:gap-x-6"
      style={{ ["--player-lg-w" as string]: `min(calc(40vh * ${width} / ${height}), 52rem)` }}
    >
      {/* Below 1024 px the player is at most 40% of the viewport tall, so chips stay reachable at 200% zoom and in landscape. */}
      <div
        className="relative mx-auto w-[min(100%,var(--player-max-w))] overflow-hidden rounded-xl bg-black lg:mx-0 lg:w-[var(--player-lg-w)]"
        style={{ aspectRatio: `${width} / ${height}`, ["--player-max-w" as string]: `calc(40vh * ${width} / ${height})` }}
      >
        {failed ? (
          <p className="flex h-full items-center justify-center p-4 text-sm text-white/80">The video didn&apos;t load. The decisions below still work.</p>
        ) : (
          <video
            ref={video}
            className="absolute inset-0 h-full w-full"
            src={playing}
            controls
            playsInline
            preload="auto"
            // A source that loads re-arms the one refresh, for when its signed URL expires later.
            onLoadedMetadata={() => setRefreshedFor(null)}
            onError={() => {
              // A background refresh already brought a fresher URL: switch to it first.
              if (src && playing && src !== playing && refreshedFor === null) {
                setRefreshedFor(playing);
                setPlaying(src);
              } else if (onMediaError && playing && refreshedFor === null) {
                setRefreshedFor(playing);
                onMediaError();
              } else {
                setFailed(true);
              }
            }}
            aria-label="Your clip, with the Safe Cut preview drawn over it"
          >
            {captionsUrl && <track kind="captions" src={captionsUrl} srcLang="en" label="English" default />}
          </video>
        )}
        <canvas ref={canvas} aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full" />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm lg:col-start-2 lg:row-start-1 lg:mt-0 lg:flex-col lg:items-start">
        <div role="radiogroup" aria-label="Preview" className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
          {(["raw", "safecut"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              data-mode={m}
              aria-checked={mode === m}
              tabIndex={mode === m ? 0 : -1}
              className={`min-h-11 rounded-md px-3 font-medium lg:min-h-9 ${mode === m ? "bg-surface shadow-sm" : "text-muted"}`}
              onClick={() => setMode(m)}
              onKeyDown={(e) => {
                if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
                  e.preventDefault();
                  const next = m === "raw" ? "safecut" : "raw";
                  setMode(next);
                  e.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-mode="${next}"]`)?.focus();
                }
              }}
            >
              {m === "raw" ? "Raw" : "■ Safe Cut"}
            </button>
          ))}
        </div>
        <p className="text-muted">Preview. The final render covers the same areas.</p>
        {!rvfc && <p className="text-muted">Preview may lag by a frame in this browser. The final render isn&apos;t affected.</p>}
      </div>
      {/* Decorative (the chips carry the same spans): 24 rows at most, so a long list can't push the
          chips away, always including the selected item so its bars light up (§3.3). */}
      <div aria-hidden="true" className="relative mt-2 hidden flex-col gap-0.5 lg:col-start-1 lg:flex lg:w-[var(--player-lg-w)]">
        {timelineRows(timeline, selected).map((t) => (
          <div key={t.id} className="relative h-1.5 rounded bg-surface-2">
            <div
              className={`absolute h-full rounded ${t.id === selected ? "bg-accent" : t.covered ? "bg-hidden-fg/40" : "bg-kept-fg/40"}`}
              style={{ left: `${(t.first / frames) * 100}%`, width: `${Math.max(0.5, ((t.last - t.first + 1) / frames) * 100)}%` }}
            />
          </div>
        ))}
      </div>
    </div>
  );
});
