"use client";
/**
 * The results table, plus the hero's audit when the table has numbers: once the open-weight
 * second opinion runs on the hero, the footnote says the test split was measured without it (§1.3).
 */
import { useEffect, useState } from "react";
import { getClient } from "@/lib/client";
import type { ResultsTable as Results } from "@/lib/contracts";
import { SITE } from "@/lib/site";
import { ResultsTable } from "./ResultsTable";

export function ResultsSection({ results }: { results: Results | null }) {
  const [heroOpenWeight, setHeroOpenWeight] = useState(false);
  useEffect(() => {
    if (!results) return;
    const controller = new AbortController();
    getClient()
      .getDemo(SITE.heroId, controller.signal)
      .then((d) => setHeroOpenWeight(d.audit?.open_weight?.status === "ok"))
      // Without the hero's audit the clause stays off: it's only ever added, never assumed.
      .catch(() => undefined);
    return () => controller.abort();
  }, [results]);
  return <ResultsTable results={results} heroOpenWeight={heroOpenWeight} />;
}
