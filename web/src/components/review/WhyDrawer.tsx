"use client";
/**
 * The "Why?" drawer (UI-SPEC §4): the Set-of-Mark keyframe SAM 3.1 tracked with
 * the item ringed, Muse Spark's rulings, and what was said. A modal dialog:
 * a side drawer on desktop, a bottom sheet on mobile.
 */
import { useEffect, useRef, useState } from "react";
import { DESKTOP_QUERY, useMediaQuery } from "@/hooks/useMediaQuery";
import type { Box, JobResponse, KeyframeGeometry } from "@/lib/contracts";
import { geometryMatches, regionWords, ringOnScreen } from "@/lib/keyframe";
import { formatFrame, formatFrameTenths } from "@/lib/time";
import type { WhyModel } from "@/lib/why/model";
import { CheckIcon, CloseIcon, CrossIcon, HiddenIcon, KeptIcon, LockIcon, NeedsIcon } from "../icons";

const STATE = {
  hide: { Icon: HiddenIcon, word: "Hidden" },
  keep: { Icon: KeptIcon, word: "Kept clear" },
  needs_you: { Icon: NeedsIcon, word: "Needs you" },
} as const;

type Loaded = { url: string; width: number; height: number } | { url: string; failed: true } | null;

function Keyframe({
  job,
  model,
  frame,
  boxFor,
  onError,
}: {
  job: JobResponse;
  model: WhyModel;
  frame: number;
  boxFor: (frame: number) => Box | null;
  onError?: () => void;
}) {
  const url = job.keyframe_urls[String(frame)];
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [displayWidth, setDisplayWidth] = useState(0);
  const img = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const el = img.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setDisplayWidth(el.getBoundingClientRect().width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [url]);
  const g: KeyframeGeometry | undefined = job.keyframe_geometry;
  const state = loaded && loaded.url === url ? loaded : null;
  const box = boxFor(frame);
  const others = job.tracks.filter((t) => t.boxes[String(frame)] && !(model.primaryTrack === t.track_id)).map((t) => t.track_id);
  const where = box && job.job ? `, ${regionWords(box, job.job.width, job.job.height)}` : "";
  const alt = `Keyframe at ${formatFrame(frame, job.job?.fps ?? 30)}. ${model.primaryTrack ?? model.label} is ringed${where}.${others.length ? ` Other labelled objects: ${others.join(", ")}.` : ""}`;
  if (!url) {
    return <p className="rounded-lg bg-surface-2 p-4 text-sm">The keyframe didn&apos;t load.</p>;
  }
  const ok = state && "width" in state && g && job.job ? geometryMatches(g, job.job, { width: state.width, height: state.height }) : false;
  const ring = ok && box && g && displayWidth > 0 ? ringOnScreen(box, g, displayWidth) : null;
  return (
    <div>
      {/* The image's ratio holds its place while it loads; a failure message sizes the box itself (large text, narrow phones). */}
      <div className="relative overflow-hidden rounded-lg bg-surface-2" style={g && !(state && "failed" in state) ? { aspectRatio: `${g.image_width} / ${g.image_height}` } : undefined}>
        {!state && <p className="absolute inset-0 flex items-center justify-center text-sm text-muted">Loading the keyframe…</p>}
        {state && "failed" in state ? (
          <p className="p-4 text-sm">The keyframe didn&apos;t load.</p>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- signed keyframe URLs, measured after load for the §4.3 geometry check
          <img
            ref={img}
            src={url}
            alt={alt}
            className="block h-auto w-full"
            onLoad={(e) => setLoaded({ url, width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
            onError={() => {
              setLoaded({ url, failed: true });
              onError?.();
            }}
          />
        )}
        {ring && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute rounded-sm border-[3px] border-white shadow-[0_0_0_2px_#111]"
            style={{ left: ring[0] - 3, top: ring[1] - 3, width: ring[2] - ring[0] + 6, height: ring[3] - ring[1] + 6 }}
          />
        )}
      </div>
      {state && "width" in state && !ok && <p className="mt-2 text-sm">The keyframe&apos;s size doesn&apos;t match this clip, so the outline is hidden.</p>}
    </div>
  );
}

export interface DrawerActions {
  canHide: boolean;
  canKeep: boolean;
  onHide: () => void;
  onKeep: () => void;
}

export function WhyDrawer({
  open,
  job,
  model,
  decision,
  badges,
  boxFor,
  actions,
  onClose,
  focusLocked,
  onKeyframeError,
}: {
  open: boolean;
  job: JobResponse;
  model: WhyModel | null;
  decision: keyof typeof STATE;
  badges: { locked: boolean; isNew: boolean; changedByYou: boolean };
  boxFor: (frame: number) => Box | null;
  actions: DrawerActions;
  onClose: () => void;
  /** Opened from the "Always hidden" help link: start at the explanation. */
  focusLocked?: boolean;
  /** The keyframe failed to load: its signed URL may have expired (§10.7). */
  onKeyframeError?: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const why = useRef<HTMLElement>(null);
  const actionBar = useRef<HTMLDivElement>(null);
  /**
   * Hide and Keep clear swap places after an edit, so the pressed button unmounts while the sheet
   * stays open and the chips behind it are inert: focus goes to the button that took its place
   * (or the sheet's heading if there's none).
   */
  const afterAction = (run: () => void) => {
    run();
    requestAnimationFrame(() => {
      if (!ref.current?.open || ref.current.contains(document.activeElement)) return;
      (actionBar.current?.querySelector("button") ?? heading.current)?.focus();
    });
  };
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const desktop = useMediaQuery(DESKTOP_QUERY);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      (focusLocked ? why.current : heading.current)?.focus();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open, focusLocked]);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const close = () => onClose();
    d.addEventListener("close", close);
    return () => d.removeEventListener("close", close);
  }, [onClose]);

  // An item with no keyframe shows only its origin's caption (§4.3), never a frame Muse Spark wasn't shown.
  const frames = model?.hasKeyframe ? model.evidenceFrames : [];
  const safeIndex = Math.min(index, Math.max(0, frames.length - 1));
  const frame = frames[safeIndex];
  const { Icon, word } = STATE[decision];
  const fps = job.job?.fps ?? 30;

  return (
    <dialog
      ref={ref}
      aria-labelledby="why-title"
      className={`fixed m-0 max-h-none max-w-none border-border bg-surface p-0 text-text shadow-[var(--shadow)] backdrop:bg-black/40
        inset-x-0 bottom-0 top-auto w-full rounded-t-2xl border-t ${expanded ? "h-[100dvh]" : "h-[85dvh]"}
        lg:inset-y-0 lg:left-auto lg:right-0 lg:h-full lg:w-[480px] lg:rounded-none lg:border-l lg:border-t-0
        [@media(max-height:36em)]:overflow-y-auto`}
    >
      {open && model && (
        // On a short screen (landscape, large text) the whole sheet scrolls: a fixed header and footer would leave the body a sliver.
        <div className="flex h-full flex-col [@media(max-height:36em)]:h-auto">
          <button type="button" className="mx-auto mt-1 flex min-h-11 w-24 items-center justify-center lg:hidden" aria-label={expanded ? "Collapse" : "Expand"} onClick={() => setExpanded((v) => !v)}>
            <span aria-hidden="true" className="h-1.5 w-12 rounded-full bg-border forced-colors:bg-[CanvasText]" />
          </button>
          {/* Wraps: at large text on a narrow phone, Close goes below a long title instead of squeezing it to a few letters a line. */}
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-3">
            <div>
              <h2 id="why-title" ref={heading} tabIndex={-1} className="text-lg font-semibold">
                {model.label} · {model.kindWord}
              </h2>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                <span className="inline-flex items-center gap-1">
                  <Icon size={14} /> {word}
                </span>
                {badges.locked && (
                  <span className="inline-flex items-center gap-1">
                    <LockIcon size={14} /> Always hidden
                  </span>
                )}
                {badges.isNew && <span className="rounded bg-needs-bg px-1.5 text-xs font-semibold text-needs-fg">NEW</span>}
                {badges.changedByYou && <span className="rounded bg-surface-2 px-1.5 text-xs">Changed by you</span>}
              </p>
            </div>
            <button type="button" className="flex min-h-11 items-center gap-1 rounded-lg border border-border px-3 text-sm lg:min-h-9" onClick={onClose}>
              Close <CloseIcon size={14} />
            </button>
          </div>

          <div data-drawer-body className="flex-1 overflow-y-auto px-5 py-4 [@media(max-height:36em)]:flex-none [@media(max-height:36em)]:overflow-visible">
            <section aria-label="Keyframe">
              {frame !== undefined ? (
                <div
                  tabIndex={0}
                  role="group"
                  aria-label="Keyframe viewer. Use the left and right arrow keys to step through the evidence frames."
                  onKeyDown={(e) => {
                    if (e.key === "ArrowRight") setIndex(Math.min(frames.length - 1, safeIndex + 1));
                    if (e.key === "ArrowLeft") setIndex(Math.max(0, safeIndex - 1));
                  }}
                >
                  <Keyframe job={job} model={model} frame={frame} boxFor={boxFor} onError={onKeyframeError} />
                </div>
              ) : (
                <p className="rounded-lg bg-surface-2 p-4 text-sm">
                  {/* By origin (§4.3); an item with no evidence frames for another reason (roles didn't run) claims neither. */}
                  {model.origin === "audit_patch"
                    ? "Added by the audit after rendering. There's no keyframe for it."
                    : model.origin === "static"
                      ? "Muse Spark spotted this, but SAM 3.1 couldn't follow it, so there's no keyframe for it."
                      : "There's no keyframe for this item."}
                </p>
              )}
              {frames.length > 1 && (
                <div className="mt-2 flex items-center gap-2 text-sm">
                  <button type="button" className="min-h-11 min-w-11 rounded-lg border border-border px-3 aria-disabled:opacity-40 lg:min-h-8 lg:min-w-8" aria-disabled={safeIndex === 0} onClick={() => safeIndex > 0 && setIndex(safeIndex - 1)} aria-label="Previous evidence frame">
                    ◀
                  </button>
                  <ol className="flex flex-wrap gap-2" aria-label="Evidence frames">
                    {frames.map((f, i) => (
                      <li key={f}>
                        <button type="button" aria-current={i === safeIndex ? "true" : undefined} className={`min-h-11 min-w-11 rounded-md px-2 tabular-nums lg:min-h-8 lg:min-w-8 ${i === safeIndex ? "bg-accent text-accent-text forced-color-adjust-none forced-colors:bg-[Highlight] forced-colors:text-[HighlightText]" : "bg-surface-2"}`} onClick={() => setIndex(i)}>
                          {formatFrame(f, fps)}
                        </button>
                      </li>
                    ))}
                  </ol>
                  <button type="button" className="min-h-11 min-w-11 rounded-lg border border-border px-3 aria-disabled:opacity-40 lg:min-h-8 lg:min-w-8" aria-disabled={safeIndex === frames.length - 1} onClick={() => safeIndex < frames.length - 1 && setIndex(safeIndex + 1)} aria-label="Next evidence frame">
                    ▶
                  </button>
                </div>
              )}
              {frame !== undefined && (
                <p className="mt-2 text-sm text-muted">Frame at {formatFrameTenths(frame, fps)}. This is the frame Muse Spark was shown. The labels are the objects SAM 3.1 tracked.</p>
              )}
              {frame !== undefined && model.primaryTrack && (
                <p className="mt-1 font-mono text-xs text-muted">
                  On the keyframe: {model.primaryTrack}
                  {model.otherTracks.map((t) => ` · also ${t}`).join("")}
                </p>
              )}
            </section>

            <section ref={why} tabIndex={-1} aria-labelledby="why-reason" className="mt-6">
              <h3 id="why-reason" className="font-semibold">
                {model.heading}
              </h3>
              {model.reason && <p className="mt-1">{model.reason}.</p>}
              <p className="mt-1 text-muted">{model.fixed}</p>
            </section>

            {model.votes.kind !== "none" && (
              <section aria-labelledby="why-votes" className="mt-6">
                <h3 id="why-votes" className="font-semibold">
                  What Muse Spark said{model.votes.kind === "votes" ? ` (${model.votes.count} ${model.votes.count === 1 ? "check" : "checks"})` : ""}
                </h3>
                {model.votes.kind === "not_run" && <p className="mt-1">{model.votes.line}</p>}
                {model.votes.kind === "object" && (
                  <div className="mt-1 space-y-1">
                    {model.votes.missedLine && <p>{model.votes.missedLine}</p>}
                    {model.votes.readAs && <p>{model.votes.readAs}</p>}
                    {model.votes.personal && <p>{model.votes.personal}</p>}
                    {model.votes.plateLine && <p className="text-muted">{model.votes.plateLine}</p>}
                  </div>
                )}
                {model.votes.kind === "votes" && (
                  <div className="mt-1 space-y-2">
                    <ul className="flex flex-wrap gap-2">
                      {model.votes.marks.map((m, i) => (
                        <li key={i} className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-1 text-sm">
                          <span aria-hidden="true">{m.agrees === null ? null : m.agrees ? <CheckIcon size={14} /> : <CrossIcon size={14} />}</span>
                          <span className="sr-only">{m.label}</span>
                          <span aria-hidden="true">{m.word}</span>
                        </li>
                      ))}
                    </ul>
                    {model.votes.failedLine && <p className="text-sm text-muted">{model.votes.failedLine}</p>}
                    {model.votes.evidence && <blockquote className="border-l-2 border-border pl-3 italic">{model.votes.evidence}</blockquote>}
                    {model.votes.escalation.map((line) => (
                      <p key={line} className={line.startsWith("“") ? "border-l-2 border-border pl-3 italic" : ""}>
                        {line}
                      </p>
                    ))}
                  </div>
                )}
              </section>
            )}

            <section aria-labelledby="why-speech" className="mt-6">
              {model.speech.kind === "no_sound" ? (
                <>
                  <h3 id="why-speech" className="font-semibold">
                    What was said
                  </h3>
                  <p className="mt-1">{model.speech.line}</p>
                </>
              ) : (
                <>
                  <h3 id="why-speech" className="font-semibold">
                    {model.speech.heading}
                  </h3>
                  <ul className="mt-1 space-y-1">
                    {model.speech.lines.map((l, i) => (
                      <li key={i} className="text-sm">
                        <span className="tabular-nums text-muted">{l.time}</span> <span className="font-medium">{l.speaker}</span> “{l.text}”
                        {l.saidBy && <span className="ml-1 text-muted">said by {model.label}</span>}
                      </li>
                    ))}
                  </ul>
                  {model.speech.footer && <p className="mt-1 text-sm text-muted">{model.speech.footer}</p>}
                </>
              )}
            </section>

            <details className="mt-6" open={desktop}>
              <summary className="min-h-11 cursor-pointer font-semibold lg:min-h-8">Details</summary>
              <ul className="mt-1 space-y-1 text-sm text-muted">
                <li>
                  {model.details.decidedBy} · {model.details.cover}
                </li>
                <li className="font-mono text-xs">{model.details.tracks}</li>
                {model.details.frames && <li className="font-mono text-xs">{model.details.frames}</li>}
                {model.details.museWords && <li>{model.details.museWords}</li>}
                <li>{model.details.models}</li>
              </ul>
            </details>
          </div>

          {(actions.canHide || actions.canKeep) && (
            <div ref={actionBar} className="flex gap-2 border-t border-border px-5 py-3 lg:hidden">
              {actions.canHide && (
                <button type="button" className="min-h-11 flex-1 rounded-lg border border-border font-medium" onClick={() => afterAction(actions.onHide)}>
                  Hide
                </button>
              )}
              {actions.canKeep && (
                <button type="button" className="min-h-11 flex-1 rounded-lg border border-border font-medium" onClick={() => afterAction(actions.onKeep)}>
                  Keep clear
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </dialog>
  );
}
