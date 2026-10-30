/**
 * Where the Safe Cut API lives (`NEXT_PUBLIC_SAFECUT_API`, inlined at build time). Shared by the client and the
 * response schemas, which accept plain-http media only from a loopback API (a local run or the e2e check).
 */
export function apiBaseUrl(): string | null {
  const raw = process.env.NEXT_PUBLIC_SAFECUT_API?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

/** The API's origin when it is plain http on loopback (`http://127.0.0.1:…`, `http://localhost:…`), else null. */
export function localApiOrigin(base: string | null = apiBaseUrl()): string | null {
  if (!base) return null;
  try {
    const url = new URL(base);
    return url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost") ? url.origin : null;
  } catch {
    return null;
  }
}
