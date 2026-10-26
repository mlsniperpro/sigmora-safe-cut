"use client";
import { useEffect, useState } from "react";

/** The current time, refreshed every `ms` so time-gated buttons re-enable on their own. */
export function useNow(ms: number): number {
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
  return now;
}
