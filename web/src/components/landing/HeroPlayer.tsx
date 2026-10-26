"use client";
/**
 * The landing hero: the pinned demo job's raw clip and Safe Cut result, with a
 * labelled toggle that keeps the playback time (UI-SPEC §1.1, §1.5).
 */
import { useEffect, useRef, useState } from "react";
import { isMockMode } from "@/lib/api";
import { getClient } from "@/lib/client";
import type { DemoResponse } from "@/lib/contracts";
import { SITE } from "@/lib/site";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { useReportMode } from "../mode";
import { PlayCircleIcon } from "../icons";

type Version = "raw" | "safecut";

export function HeroPlayer({ onAuditor }: { onAuditor?: (audit: DemoResponse["audit"]) => void }) {
  const [demo, setDemo] = useState<DemoResponse | null>(null);
  const [failed, setFailed] = useState(false);
  /** Presigned URLs live 15 minutes: a load error refetches the demo once for fresh ones (§1.4). */
  const [refreshes, setRefreshes] = useState(0);
  const [version, setVersion] = useState<Version>("safecut");
  const reduced = useReducedMotion();
  const video = useRef<HTMLVideoElement>(null);
  const resumeAt = useRef<number | null>(null);
  // The sample hero in mock mode isn't a real run, so it doesn't claim demo mode.
  useReportMode(isMockMode() ? null : demo?.mode);

  useEffect(() => {
    const controller = new AbortController();
    getClient()
      .getDemo(SITE.heroId, controller.signal)
      .then((d) => {
        setDemo(d);
        onAuditor?.(d.audit);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [onAuditor, refreshes]);


  const switchTo = (next: Version) => {
    if (next === version) return;
    resumeAt.current = video.current?.currentTime ?? 0;
    setVersion(next);
  };

  const src = demo ? (version === "raw" ? demo.job.prepared_url : demo.video_url) : undefined;
  const mock = isMockMode();

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
            onLoadedMetadata={(e) => {
              if (resumeAt.current !== null) {
                e.currentTarget.currentTime = resumeAt.current;
                resumeAt.current = null;
                if (!reduced) void e.currentTarget.play().catch(() => undefined);
              }
            }}
            onError={() => {
              if (refreshes === 0) setRefreshes(1);
              else setFailed(true);
            }}
            aria-label={version === "raw" ? "Raw footage of the demo clip" : "The demo clip after Safe Cut"}
          >
            {demo.captions_url && <track kind="captions" src={demo.captions_url} srcLang="en" label="English" default />}
          </video>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-white/80">{failed ? null : "Loading the demo…"}</div>
        )}
        {reduced && demo && !failed && (
          <button
            type="button"
            className="absolute bottom-14 left-3 flex min-h-11 items-center gap-2 rounded-md bg-surface px-3 text-sm font-medium text-text"
            onClick={() => void video.current?.play()}
          >
            <PlayCircleIcon size={18} /> Play demo
          </button>
        )}
      </div>
      <figcaption className="flex flex-col gap-2 border-t border-border p-3 text-sm">
        <div role="radiogroup" aria-label="Version" aria-describedby="toggle-hint" className="inline-flex w-fit rounded-lg border border-border bg-surface-2 p-0.5">
          {(["raw", "safecut"] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={version === v}
              tabIndex={version === v ? 0 : -1}
              disabled={!demo}
              className={`min-h-11 rounded-md px-3 font-medium lg:min-h-9 ${version === v ? "bg-surface text-text shadow-sm" : "text-muted"}`}
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
          {mock ? "Sample clip: drawn shapes, not real people." : SITE.heroHasChild ? "Staged demo. Everyone shown signed a release (a guardian signed for the child)." : "Staged demo. Everyone shown signed a release."}
        </p>
        {failed && <p>The demo video didn&apos;t load. You can still try Safe Cut with an access code.</p>}
      </figcaption>
    </figure>
  );
}
