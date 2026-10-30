"use client";
import { useCallback, useSyncExternalStore } from "react";

/**
 * The desktop layout, in em like Tailwind's `lg:` (64rem): a larger default text size moves both
 * together, so JS and CSS never disagree on which layout is showing.
 */
export const DESKTOP_QUERY = "(min-width: 64em)";

/** A media query as React state; false on the server. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false);
}
