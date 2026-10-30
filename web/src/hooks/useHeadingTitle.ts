"use client";
import { useEffect } from "react";

/**
 * The tab title follows the page's h1 (WCAG 2.4.2), for pages that show one of many states
 * (§10.4): its first sentence, then the site name. Before any h1 shows, `fallback` stands in.
 */
export function useHeadingTitle(fallback: string): void {
  useEffect(() => {
    const heading = document.querySelector("h1")?.textContent?.trim();
    const lead = heading ? (heading.split(/(?<=[.!?])\s/)[0] ?? heading).replace(/\.$/, "") : fallback;
    const title = `${lead} · Safe Cut`;
    if (document.title !== title) document.title = title;
  });
}
