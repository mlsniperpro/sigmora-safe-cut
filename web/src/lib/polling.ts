/**
 * The one polling rule (UI-SPEC §10.3): how long to wait before the next
 * `GET /v1/jobs/{id}`, or null when polling should stop or pause.
 */
import type { JobStatus } from "./contracts";

export const FAST_MS = 2_000;
export const SLOW_MS = 5_000;
export const FAST_WINDOW_MS = 60_000;
export const BUSY_MS = 30_000;
export const RATE_LIMIT_DEFAULT_MS = 60_000;
/** Signed media URLs live 15 min (§10.7): a page that isn't polling refetches before they expire. */
export const URL_REFRESH_MS = 10 * 60_000;

export function nextPollDelay(status: JobStatus, msSincePageView: number, retryAt: string | null | undefined, now: number): number | null {
  switch (status) {
    case "processing":
    case "rendering":
      return msSincePageView < FAST_WINDOW_MS ? FAST_MS : SLOW_MS;
    case "retry_later": {
      if (retryAt) {
        const until = Date.parse(retryAt) - now;
        if (Number.isFinite(until) && until > 0) return Math.min(until, BUSY_MS);
      }
      return BUSY_MS;
    }
    default:
      // review and needs_you pause; done, failed and created stop until an action restarts polling
      return null;
  }
}
