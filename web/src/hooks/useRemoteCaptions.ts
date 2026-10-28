"use client";
import { useEffect, useState } from "react";
import { REQUEST_TIMEOUT_MS } from "@/lib/api";

/** One blob URL per captions text, kept for the page's life (see `useCaptions`). */
const urls = new Map<string, string>();

/**
 * A `<track>` src for captions at `url`. Same-origin paths are used as they are. A track from
 * another origin (the storage host's signed URL) only loads on a `crossorigin` video, which
 * would make the video itself depend on the bucket's CORS; so its WebVTT is fetched here and
 * handed over as a blob URL. If that fails, the video still plays, just without captions.
 */
export function useRemoteCaptions(url: string | null | undefined): string | null {
  const local = !!url && url.startsWith("/");
  const [fetched, setFetched] = useState<{ url: string; blob: string } | null>(null);
  useEffect(() => {
    if (!url || local || typeof URL.createObjectURL !== "function") return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    fetch(url, { signal: controller.signal, credentials: "omit" })
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error(`captions ${res.status}`))))
      .then((text) => {
        if (!text.startsWith("WEBVTT")) throw new Error("not WebVTT");
        let blob = urls.get(text);
        if (!blob) {
          blob = URL.createObjectURL(new Blob([text], { type: "text/vtt" }));
          urls.set(text, blob);
        }
        setFetched({ url, blob });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) console.warn(`captions didn't load (${error instanceof Error ? error.message : "error"})`);
      })
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [url, local]);
  if (!url) return null;
  if (local) return url;
  // A re-signed URL for the same captions keeps the blob on show until the new one is in (and
  // identical text gives the same blob), so the <track> isn't remounted and switched back on.
  return fetched?.blob ?? null;
}
