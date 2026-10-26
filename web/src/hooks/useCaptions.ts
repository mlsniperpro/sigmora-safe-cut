"use client";
import { useEffect, useMemo } from "react";
import type { Transcript } from "@/lib/contracts";
import { transcriptToVtt } from "@/lib/captions";

/** A blob URL of captions built from the transcript, revoked when it changes or unmounts. */
export function useCaptions(transcript: Transcript | undefined, audio: boolean): string | null {
  const url = useMemo(() => {
    const vtt = audio ? transcriptToVtt(transcript) : null;
    return vtt && typeof URL.createObjectURL === "function" ? URL.createObjectURL(new Blob([vtt], { type: "text/vtt" })) : null;
  }, [transcript, audio]);
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);
  return url;
}
