"use client";
/**
 * "Waking Safe Cut up…" (UI-SPEC §10.3 "Cold start"): shown while the API is coming out of a cold start, and
 * gone as soon as it answers. One calm line, announced politely; it is a state of the page, not an error.
 * The live region is always in the page and only its text comes and goes, so screen readers announce it.
 */
import { COPY } from "@/lib/copy";
import { useServiceWaking } from "@/hooks/useServiceWaking";

export function WakingNotice({ className = "mt-4 text-sm text-muted" }: { className?: string }) {
  const waking = useServiceWaking();
  return <div role="status">{waking && <p className={className}>{COPY.waking}</p>}</div>;
}
