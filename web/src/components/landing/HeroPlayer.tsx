"use client";
/**
 * The landing hero: the pinned demo job's raw clip and Safe Cut result, with a
 * labelled toggle that keeps the playback time (UI-SPEC §1.1, §1.5).
 */
import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import type { DemoResponse } from "@/lib/contracts";
import { SITE } from "@/lib/site";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { useRemoteCaptions } from "@/hooks/useRemoteCaptions";
import { useReportMode } from "../mode";
import { WakingNotice } from "../WakingNotice";
import { PlayCircleIcon } from "../icons";

type Version = "raw" | "safecut";
const DEMO_RETRY_MS = 2_000;

export function HeroPlayer({ onAuditor }: { onAuditor?: (audit: DemoResponse["audit"]) => void }) {
  const [demo, setDemo] = useState<DemoResponse | null>(null);
  const [failed, setFailed] = useState(false);
  /** Presigned URLs live 15 minutes: a load error refetches the demo once for fresh ones (§1.4). */
  const [refreshes, setRefreshes] = useState(0);
  const [version, setVersion] = useState<Version>("safecut");
  const reduced = useReducedMotion();
  /** Reduced motion's "Play demo" button would cover the controls while the clip plays, so it shows only while paused. */
  const [playing, setPlaying] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const resumeAt = useRef<number | null>(null);
  /** One refetch per failure; a source that loads re-arms it, for a page left open past the URLs' 15 min. */
  const retried = useRef(false);
  /** The URL that failed: a refetch that gives it back means it won't play, so say so (§1.4). */
  const failedSrc = useRef<string | null>(null);
  /** A cold start's 5xx on the demo gets one quiet retry before the page says it didn't load. */
  const demoRetried = useRef(false);
  useReportMode(demo?.mode, demo?.synthetic);

  useEffect(() => {
    const controller = new AbortController();
    getClient()
      .getDemo(SITE.heroId, controller.signal)
      .then((d) => {
        const failedAgain = failedSrc.current !== null && (d.video_url === failedSrc.current || d.job.prepared_url === failedSrc.current);
        failedSrc.current = null;
        if (failedAgain) setFailed(true);
        setDemo(d);
        onAuditor?.(d.audit);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && (error.status ?? 0) >= 500 && !demoRetried.current) {
          demoRetried.current = true;
          // Not cleared with the request: the retry must come even if this effect re-runs first.
          setTimeout(() => setRefreshes((n) => n + 1), DEMO_RETRY_MS);
          return;
        }
        setFailed(true);
      });
    return () => controller.abort();
  }, [onAuditor, refreshes]);


  const switchTo = (next: Version) => {
    if (next === version) return;
    resumeAt.current = video.current?.currentTime ?? 0;
    // The new element starts paused; autoplay or the resume below reports play again.
    setPlaying(false);
    setVersion(next);
  };

  const src = demo ? (version === "raw" ? demo.job.prepared_url : demo.video_url) : undefined;
  const captions = useRemoteCaptions(demo?.captions_url);
  // §1.4: the poster shows while loading and stays under the message if the video fails. Before
  // the first answer only mock mode knows it (the sample's); live mode shows the dark frame.
  const poster = demo?.poster_url ?? null;

  return (
    <figure className="overflow-hidden rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
      <div className="relative aspect-video bg-black">
        {demo && !failed ? (
          <video
            key={version}
            ref={video}
            className="h-full w-full"
            src={src}
            poster={demo.poster_url ?? undefined}
            controls
            muted
            loop
            playsInline
            autoPlay={!reduced}
            preload="metadata"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            onLoadedMetadata={(e) => {
              retried.current = false;
              if (resumeAt.current !== null) {
                e.currentTarget.currentTime = resumeAt.current;
                resumeAt.current = null;
                if (!reduced) void e.currentTarget.play().catch(() => undefined);
              }
            }}
            onError={() => {
              if (retried.current) {
                setFailed(true);
                return;
              }
              retried.current = true;
              failedSrc.current = src ?? null;
              setRefreshes((n) => n + 1);
            }}
            aria-label={version === "raw" ? "Raw footage of the demo clip" : "The demo clip after Safe Cut"}
          >
            {captions && <track kind="captions" src={captions} srcLang="en" label="English" default />}
          </video>
        ) : (
          <div className="relative flex h-full flex-col items-center justify-center gap-2 px-3 text-center text-sm text-white/80">
            {/* eslint-disable-next-line @next/next/no-img-element -- a signed poster URL, like the video's own poster attribute */}
            {poster && <img src={poster} alt="" className="absolute inset-0 h-full w-full object-cover" />}
            {!failed && <span className="relative rounded bg-black/60 px-2 py-1">Loading the demo…</span>}
            <div className="relative">
              <WakingNotice className="rounded bg-black/60 px-2 py-1" />
            </div>
          </div>
        )}
        {reduced && demo && !failed && !playing && (
          <button
            type="button"
            className="absolute bottom-14 left-3 flex min-h-11 items-center gap-2 rounded-md bg-surface px-3 text-sm font-medium text-text"
            onClick={() => {
              // The button goes away once playback starts, so focus moves to the player's own controls.
              video.current?.focus();
              void video.current?.play().catch(() => undefined);
            }}
          >
            <PlayCircleIcon size={18} /> Play demo
          </button>
        )}
      </div>
      <figcaption className="flex flex-col gap-2 border-t border-border p-3 text-sm">
        <div role="radiogroup" aria-label="Version" aria-describedby="toggle-hint" className="inline-flex w-fit max-w-full flex-wrap rounded-lg border border-border bg-surface-2 p-0.5">
          {(["raw", "safecut"] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={version === v}
              tabIndex={version === v ? 0 : -1}
              disabled={!demo}
              className={`min-h-11 rounded-md px-3 font-medium lg:min-h-9 ${version === v ? "bg-surface text-text shadow-sm forced-color-adjust-none forced-colors:bg-[Highlight] forced-colors:text-[HighlightText]" : "text-muted"}`}
              onClick={() => switchTo(v)}
              onKeyDown={(e) => {
                if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
                  e.preventDefault();
                  const next = v === "raw" ? "safecut" : "raw";
                  switchTo(next);
                  (e.currentTarget.parentElement?.querySelector(`[data-v="${next}"]`) as HTMLButtonElement | null)?.focus();
                }
              }}
              data-v={v}
            >
              {v === "raw" ? "Raw footage" : "■ Safe Cut"}
            </button>
          ))}
        </div>
        <span id="toggle-hint" className="sr-only">
          Switch between the original clip and the Safe Cut result.
        </span>
        <p className="text-muted">
          <span className="font-medium text-text">Precomputed result.</span>{" "}
          {demo?.synthetic ? "Synthetic test clip: drawn shapes, not real people." : SITE.heroHasChild ? "Staged demo. Everyone shown signed a release (a guardian signed for the child)." : "Staged demo. Everyone shown signed a release."}
        </p>
        {failed && <p>The demo video didn&apos;t load. You can still try Safe Cut with an access code.</p>}
      </figcaption>
    </figure>
  );
}
