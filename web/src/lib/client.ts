/**
 * The app-wide API client: live when `NEXT_PUBLIC_SAFECUT_API` is set, the
 * in-browser mock backend otherwise.
 */
import { SafeCutClient, apiBaseUrl } from "./api";
import { MockBackend } from "./mock-backend";
import { liveTransport } from "./transport-live";

let client: SafeCutClient | null = null;

export const SAMPLE_MEDIA_BASE = "/sample";

export function getClient(): SafeCutClient {
  if (client) return client;
  const base = apiBaseUrl();
  client = new SafeCutClient({
    transport: base ? liveTransport(base) : new MockBackend({ sample: { job: "job-review-sample", mediaBase: SAMPLE_MEDIA_BASE } }),
  });
  return client;
}

/** Tests swap the client for one on a scripted backend. */
export function setClientForTests(next: SafeCutClient | null): void {
  client = next;
}
