"use client";
/**
 * Loads a job and keeps it fresh under the §10.3 polling rule. Pauses while the
 * tab is hidden, waits out a 429, and stops for good after a delete.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import type { JobResponse } from "@/lib/contracts";
import { FAST_MS, RATE_LIMIT_DEFAULT_MS, nextPollDelay } from "@/lib/polling";

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

  useEffect(() => {
    if (deleted.current) return;
    viewStart.current ??= Date.now();
    const controller = new AbortController();
    const startedAt = patches.current;
    const schedule = (ms: number) => {
      timer.current = setTimeout(() => setTick((t) => t + 1), ms);
    };
    getClient()
      .getJob(jobId, controller.signal)
      .then((job) => {
        if (deleted.current || controller.signal.aborted) return;
        const status = pollCreated && job.status === "created" ? "processing" : job.status;
        const delay = nextPollDelay(status, Date.now() - (viewStart.current ?? Date.now()), job.retry_at, Date.now());
        shown.current = true;
        serverRetried.current = false;
        polling.current = delay !== null;
        // A review ack or action ack landed while this GET was in flight: it's newer, keep it.
        if (patches.current === startedAt) setLoad({ kind: "ready", job });
        if (delay !== null && document.visibilityState === "visible") schedule(delay);
      })
      .catch((error: unknown) => {
        if (deleted.current || controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 429) {
          // Rate limited while polling: silent; wait, then carry on (§10.3).
          schedule((error.retryAfterS ?? RATE_LIMIT_DEFAULT_MS / 1000) * 1000);
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

  return { load, resume, patch, markDeleted };
}
