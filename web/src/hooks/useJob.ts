"use client";
/**
 * Loads a job and keeps it fresh under the §10.3 polling rule. Pauses while the
 * tab is hidden, waits out a 429, and stops for good after a delete.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import type { JobResponse } from "@/lib/contracts";
import { FAST_MS, RATE_LIMIT_DEFAULT_MS, URL_REFRESH_MS, nextPollDelay } from "@/lib/polling";

export type JobLoad =
  | { kind: "loading" }
  | { kind: "ready"; job: JobResponse }
  | { kind: "expired" }
  | { kind: "not_found" }
  | { kind: "unreachable" }
  | { kind: "unexpected" }
  | { kind: "deleted" };

export function classifyLoadError(error: unknown): Exclude<JobLoad["kind"], "loading" | "ready" | "deleted"> {
  if (error instanceof ApiError) {
    if (error.kind === "http" && error.status === 404) return error.code === "expired" ? "expired" : "not_found";
    if (error.kind === "network" || error.kind === "timeout") return "unreachable";
  }
  return "unexpected";
}

/**
 * A job with another response's signed media URLs, and nothing else from it. Keyframes missing
 * from `fresh` keep the URLs `job` has.
 */
export function withFreshUrls(job: JobResponse, fresh: JobResponse): JobResponse {
  return {
    ...job,
    keyframe_urls: { ...job.keyframe_urls, ...fresh.keyframe_urls },
    ...(job.job && fresh.job?.prepared_url !== undefined && { job: { ...job.job, prepared_url: fresh.job.prepared_url } }),
    ...(job.result && fresh.result && { result: { ...job.result, video_url: fresh.result.video_url } }),
  };
}

/**
 * `pollCreated`: /try polls only after `POST /start` resolved, so a `created` answer there is a
 * start the API hasn't reflected yet; it polls like `processing` instead of stopping.
 */
export function useJob(jobId: string, { pollCreated = false }: { pollCreated?: boolean } = {}) {
  const [load, setLoad] = useState<JobLoad>({ kind: "loading" });
  const [tick, setTick] = useState(0);
  const viewStart = useRef<number | null>(null);
  const deleted = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Whether the last known status polls (§10.3); the tab-visible refetch only runs then. */
  const polling = useRef(true);
  /** Bumped by every local patch, so a GET that started before one can't overwrite it. */
  const patches = useRef(0);
  /** A job is on screen; one 5xx while polling it retries quietly instead of replacing the page. */
  const shown = useRef(false);
  const serverRetried = useRef(false);
  /** When the last GET answered, and whether the next one is a quiet signed-URL refresh. */
  const lastFetch = useRef(0);
  const quiet = useRef(false);
  /**
   * Whether the next GET's signed URLs replace the ones on screen. Otherwise a poll keeps them,
   * so a re-signed URL doesn't reload the video, its captions, thumbnails or the drawer's keyframe
   * every few seconds (§10.7: fresh URLs are fetched when one expires or is about to).
   */
  const fresh = useRef(false);

  useEffect(() => {
    if (deleted.current) return;
    viewStart.current ??= Date.now();
    const controller = new AbortController();
    const startedAt = patches.current;
    const quietGet = quiet.current;
    quiet.current = false;
    const freshGet = fresh.current;
    fresh.current = false;
    const schedule = (ms: number) => {
      timer.current = setTimeout(() => setTick((t) => t + 1), ms);
    };
    // Paused or stopped, a page still holds signed URLs (keyframes, "Download this version")
    // that expire after 15 min: refetch quietly before then (§10.7).
    const scheduleRefresh = () => {
      timer.current = setTimeout(() => {
        quiet.current = true;
        fresh.current = true;
        setTick((t) => t + 1);
      }, URL_REFRESH_MS);
    };
    getClient()
      .getJob(jobId, controller.signal)
      .then((job) => {
        if (deleted.current || controller.signal.aborted) return;
        const status = pollCreated && job.status === "created" ? "processing" : job.status;
        const delay = nextPollDelay(status, Date.now() - (viewStart.current ?? Date.now()), job.retry_at, Date.now());
        shown.current = true;
        serverRetried.current = false;
        lastFetch.current = Date.now();
        polling.current = delay !== null;
        // A review ack or action ack landed while this GET was in flight: it's newer, keep it.
        if (patches.current === startedAt) {
          setLoad((prev) => ({ kind: "ready", job: prev.kind === "ready" && !freshGet ? withFreshUrls(job, prev.job) : job }));
        } else if (freshGet) {
          // Its signed URLs are still the freshest, though: keep those (§10.7).
          setLoad((prev) => (prev.kind === "ready" ? { kind: "ready", job: withFreshUrls(prev.job, job) } : prev));
        }
        if (document.visibilityState === "visible") {
          if (delay !== null) schedule(delay);
          else scheduleRefresh();
        }
      })
      .catch((error: unknown) => {
        if (deleted.current || controller.signal.aborted) return;
        // A failed quiet refresh keeps the page as it is and tries again later.
        if (quietGet && shown.current) {
          scheduleRefresh();
          return;
        }
        if (error instanceof ApiError && error.status === 429) {
          // Rate limited while polling: silent; wait, then carry on (§10.3). A `Retry-After: 0`
          // still waits one fast poll, so it can't turn into a tight loop.
          schedule(Math.max(FAST_MS, (error.retryAfterS ?? RATE_LIMIT_DEFAULT_MS / 1000) * 1000));
          return;
        }
        if (shown.current && !serverRetried.current && error instanceof ApiError && (error.status ?? 0) >= 500) {
          serverRetried.current = true;
          schedule(FAST_MS);
          return;
        }
        console.error(`job ${jobId}: load failed (${error instanceof ApiError ? (error.status ?? error.kind) : "error"})`);
        setLoad({ kind: classifyLoadError(error) });
      });
    return () => {
      controller.abort();
      if (timer.current) clearTimeout(timer.current);
    };
  }, [jobId, tick, pollCreated]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        if (timer.current) clearTimeout(timer.current);
      } else if (polling.current) {
        setTick((t) => t + 1);
      } else if (shown.current) {
        // Hiding cleared the URL-refresh timer: re-arm it for whatever is left of the interval.
        const left = URL_REFRESH_MS - (Date.now() - lastFetch.current);
        timer.current = setTimeout(() => {
          quiet.current = true;
          fresh.current = true;
          setTick((t) => t + 1);
        }, Math.max(0, left));
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  /** Restart polling after an action (start, render, audit, Try again). */
  const resume = useCallback(() => {
    viewStart.current = Date.now();
    polling.current = true;
    setTick((t) => t + 1);
  }, []);

  /** Refetch for fresh signed URLs: one failed to load (§10.7). */
  const refreshUrls = useCallback(() => {
    fresh.current = true;
    setTick((t) => t + 1);
  }, []);

  /** Apply a response we already have (a review ack, an action ack) without a fetch. */
  const patch = useCallback((update: (job: JobResponse) => JobResponse) => {
    patches.current += 1;
    setLoad((prev) => (prev.kind === "ready" ? { kind: "ready", job: update(prev.job) } : prev));
  }, []);

  /** After this page's own DELETE: stop at once and ignore every later response (§10.4). */
  const markDeleted = useCallback(() => {
    deleted.current = true;
    if (timer.current) clearTimeout(timer.current);
    setLoad({ kind: "deleted" });
  }, []);

  return { load, resume, refreshUrls, patch, markDeleted };
}
