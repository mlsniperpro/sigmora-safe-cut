"use client";
import { useCallback, useEffect, useState } from "react";
import { RATE_LIMIT_DEFAULT_MS } from "@/lib/polling";

/**
 * A control a `429` put on hold (UI-SPEC §10.3): `coolingDown` until `Retry-After` (or 60 s
 * without one) has passed, then the control works again.
 */
export function useCooldown(): { coolingDown: boolean; coolDown: (retryAfterS: number | null) => void } {
  const [until, setUntil] = useState<number | null>(null);
  useEffect(() => {
    if (until === null) return;
    const t = setTimeout(() => setUntil(null), Math.max(0, until - Date.now()));
    return () => clearTimeout(t);
  }, [until]);
  const coolDown = useCallback((retryAfterS: number | null) => {
    setUntil(Date.now() + (retryAfterS !== null ? retryAfterS * 1000 : RATE_LIMIT_DEFAULT_MS));
  }, []);
  return { coolingDown: until !== null, coolDown };
}
