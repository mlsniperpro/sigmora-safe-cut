"use client";
import { useMemo } from "react";
import type { Transcript } from "@/lib/contracts";
import { transcriptToVtt } from "@/lib/captions";

/**
 * One blob URL per distinct captions text, kept for the page's life. A poll hands over a new
 * transcript object with the same text, and StrictMode remounts effects in dev: neither may revoke
 * a URL the `<track>` still uses. A page shows one transcript, so the cache stays tiny.
 */
const urls = new Map<string, string>();

/** A blob URL of WebVTT captions built from the transcript, or null without speech or audio. */
export function useCaptions(transcript: Transcript | undefined, audio: boolean): string | null {
  const vtt = useMemo(() => (audio ? transcriptToVtt(transcript) : null), [transcript, audio]);
  return useMemo(() => {
    if (!vtt || typeof URL.createObjectURL !== "function") return null;
    let url = urls.get(vtt);
    if (!url) {
      url = URL.createObjectURL(new Blob([vtt], { type: "text/vtt" }));
      urls.set(vtt, url);
    }
    return url;
  }, [vtt]);
}
