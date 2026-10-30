/**
 * The landing page's results table. WP8 replaces `RESULTS` with the numbers
 * from a committed `eval/results/<run-id>/metrics.json` (AGENTS.md rule 9);
 * until then the page shows the placeholder line, never a made-up number.
 */
import type { ResultsTable } from "@/lib/contracts";

export const RESULTS: ResultsTable | null = null;
