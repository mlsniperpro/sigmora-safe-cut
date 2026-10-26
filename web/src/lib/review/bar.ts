/**
 * Which bottom-bar row applies (UI-SPEC §3.5): the first matching rule wins.
 */
import { effectiveDecision, uncoveredSpots, visibleItems, type ReviewState } from "./reducer";

export type BarRow =
  | { row: 0; kind: "refused"; code: string }
  | { row: 1; kind: "rendering" }
  | { row: 2; kind: "audit_blocked" }
  | { row: 3; kind: "saving" }
  | { row: 4; kind: "unfixed"; count: number }
  | { row: 5; kind: "unchanged" }
  | { row: 6; kind: "edited_after_render" }
  | { row: 7; kind: "needs_you"; count: number }
  | { row: 8; kind: "all_decided" };

export function needsYouCount(state: Pick<ReviewState, "items">): number {
  return visibleItems(state).filter(([id]) => effectiveDecision(state, id) === "needs_you").length;
}

export function selectBar(
  state: Pick<ReviewState, "refusal" | "status" | "pending" | "spots" | "has_render" | "items">,
  viewReview: boolean,
): BarRow {
  if (state.refusal) return { row: 0, kind: "refused", code: state.refusal.code };
  if (state.status === "rendering") return { row: 1, kind: "rendering" };
  if (state.status === "needs_you") return { row: 2, kind: "audit_blocked" };
  if (Object.keys(state.pending).length > 0) return { row: 3, kind: "saving" };
  const reviewing = state.status === "review" || (state.status === "done" && viewReview);
  const unfixed = uncoveredSpots(state).length;
  if (reviewing && unfixed > 0) return { row: 4, kind: "unfixed", count: unfixed };
  if (state.status === "done") return { row: 5, kind: "unchanged" };
  if (state.status === "review" && state.has_render) return { row: 6, kind: "edited_after_render" };
  const k = needsYouCount(state);
  if (k > 0) return { row: 7, kind: "needs_you", count: k };
  return { row: 8, kind: "all_decided" };
}
