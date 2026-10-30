/**
 * The app-wide API client, always the live Safe Cut API at `NEXT_PUBLIC_SAFECUT_API`. Without one configured,
 * every call fails as a network error, so each page shows its "service isn't responding" state rather than
 * made-up data. (The in-browser mock backend is test support only: `src/test/mock-backend.ts`.)
 */
import { ApiError, SafeCutClient, apiBaseUrl, type Transport } from "./api";
import { liveTransport } from "./transport-live";

let client: SafeCutClient | null = null;

/** A transport for a build with no API configured: every request fails loudly, nothing is faked. */
export function unconfiguredTransport(): Transport {
  const fail = () => Promise.reject(new ApiError({ kind: "network", message: "NEXT_PUBLIC_SAFECUT_API is not set" }));
  return { request: fail, upload: fail };
}

export function getClient(): SafeCutClient {
  if (client) return client;
  const base = apiBaseUrl();
  client = new SafeCutClient({ transport: base ? liveTransport(base) : unconfiguredTransport() });
  return client;
}

/** Tests swap the client for one on a scripted backend. */
export function setClientForTests(next: SafeCutClient | null): void {
  client = next;
}
