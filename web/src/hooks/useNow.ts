"use client";
import { useEffect, useState } from "react";

/**
 * The current time, refreshed every `ms` and also right at each time in `wakeAt`, so a
 * button gated on `retry_at` or `Retry-After` re-enables when it says it will, not up to `ms` late.
 */
export function useNow(ms: number, wakeAt: readonly (number | null)[] = []): number {
  // Starts at 0 so nothing time-dependent is evaluated during a prerender; set right after mount.
  const [now, setNow] = useState(0);
  useEffect(() => {
    const first = setTimeout(() => setNow(Date.now()), 0);
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [ms]);
  const deadlines = wakeAt.filter((at): at is number => at !== null && Number.isFinite(at)).join(",");
  useEffect(() => {
    if (!deadlines) return;
    // A deadline already due (`Retry-After: 0`, a past date) wakes at once. Timers can fire a few
    // ms early: wake just after the deadline so `now >= at` holds.
    const timers = deadlines
      .split(",")
      .map(Number)
      .map((at) => setTimeout(() => setNow(Math.max(Date.now(), at)), Math.max(0, at - Date.now()) + 1));
    return () => timers.forEach(clearTimeout);
  }, [deadlines]);
  return now;
}
