"use client";
import { useMediaQuery } from "./useMediaQuery";

/** True when the viewer asked for reduced motion (no autoplay, no sliding drawers). */
export function useReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}
