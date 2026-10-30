/**
 * The review panel's view model: chips per column (UI-SPEC §3.3, §3.9),
 * header counts and the item index the overlay and drawer share.
 */
import type { Box, Item, JobResponse, Spot, Track } from "../contracts";
import { KIND_WORD, asSentence, capitalise, isObjectKind, itemSpan, primaryTrackId } from "../labels";
import { formatFrameRange, spokenFrameRange } from "../time";
import { rewriteFrameRefs } from "../why/rewrite";
import { effectiveDecision, spotLabels, tracksShown, visibleItems, type ReviewState } from "./reducer";

export type Column = "hide" | "keep" | "needs_you";

export interface ChipButtons {
  why: boolean;
  hide: boolean;
  keep: boolean;
  merge: { target: string; targetLabel: string } | null;
  cover: boolean;
  menu: { remove: boolean; jump: boolean };
}

export interface Chip {
  id: string;
  /** "item" for decisions, "spot" for unfixed audit spots (U chips). */
  type: "item" | "spot";
  label: string;
  kindWord: string;
  kind: Item["kind"];
  column: Column;
  reason: string;
  range: string;
  spokenRange: string;
  span: { first: number; last: number } | null;
  locked: boolean;
  isNew: boolean;
  changedByYou: boolean;
  removed: boolean;
  newLine: string | null;
  buttons: ChipButtons;
  /** First frame to seek to when selected. */
  seekFrame: number;
  thumb: { frame: number; box: Box } | null;
  pending: boolean;
  accessibleName: string;
}

const DECISION_STATE: Record<Column, string> = { hide: "hidden", keep: "kept clear", needs_you: "needs you" };

/** The first frame (from `frames`) where one of the item's tracks has a box, primary track first. */
function boxOnFrame(trackIds: readonly string[], frame: number, tracks: ReadonlyMap<string, Track>): Box | null {
  const primary = primaryTrackId(trackIds);
  const order = primary ? [primary, ...trackIds.filter((t) => t !== primary)] : [...trackIds];
  for (const id of order) {
    const box = tracks.get(id)?.boxes[String(frame)];
    if (box) return box;
  }
  return null;
}

export function buildChips(state: ReviewState, job: JobResponse): Chip[] {
  const fps = job.job?.fps ?? 30;
  const frames = job.job?.frames ?? 1;
  const clock = { fps, frames };
  const tracks = new Map(job.tracks.map((t) => [t.track_id, t]));
  const serverItems = new Map(state.server.items.map((i) => [i.item_id, i]));
  const keyframes = new Set(Object.keys(job.keyframe_urls));
  const pendingItems = new Set(Object.values(state.pending).flatMap((p) => p.touches));
  const readOnly = state.status === "rendering" || state.status === "needs_you";
  const chips: Chip[] = [];

  for (const [id, item] of visibleItems(state)) {
    const server = serverItems.get(id);
    const decision = effectiveDecision(state, id) ?? item.decision;
    const column: Column = decision;
    const shownTracks = tracksShown(state, id);
    const span = itemSpan({ track_ids: shownTracks, first: server?.first ?? null, last: server?.last ?? null }, tracks);
    const auditAdded = server?.origin === "audit_patch" || (item.track_ids.length === 0 && !!item.spot_id);
    const reentryTarget = item.reentry_target ? state.items[item.reentry_target] : undefined;
    const isNew = item.reentry_target !== null;
    const reacquiredHidden = isNew && decision !== "keep";
    const targetIsKeptParticipant = !!reentryTarget && reentryTarget.kind === "person" && reentryTarget.decision === "keep" && reentryTarget.role === "participant" && reentryTarget.merged_into === null;
    const offerMerge = reacquiredHidden && targetIsKeptParticipant && item.kind === "person" && !item.locked;
    const person = item.kind === "person" || item.kind === "child";
    const reason = auditAdded ? "Added by the audit: the final check found this after rendering and covered it." : capitalise(rewriteFrameRefs(server?.reason ?? "", clock));
    const newLine = !reacquiredHidden ? null : offerMerge ? `Might be ${reentryTarget?.label}: the tracker lost them and found them again.` : "The tracker lost this person and found them again. They stay hidden.";
    const evidence = server?.evidence_frames ?? [];
    const seekFrame = evidence[0] ?? span?.first ?? 0;
    const thumbFrame = evidence[0];
    let thumb: Chip["thumb"] = null;
    if (thumbFrame !== undefined && keyframes.has(String(thumbFrame))) {
      const box = auditAdded ? server?.box ?? null : boxOnFrame(shownTracks, thumbFrame, tracks);
      if (box) thumb = { frame: thumbFrame, box };
    }
    const range = span ? formatFrameRange(span.first, span.last, fps) : "";
    const kindWord = KIND_WORD[item.kind];
    const lockedText = item.locked ? ", always hidden" : "";
    const chip: Chip = {
      id,
      type: "item",
      label: item.label,
      kindWord,
      kind: item.kind,
      column,
      reason,
      range,
      spokenRange: span ? spokenFrameRange(span.first, span.last, fps) : "",
      span,
      locked: item.locked,
      isNew,
      changedByYou: item.decided_by === "creator",
      removed: item.removed,
      newLine,
      buttons: {
        why: !id.startsWith("pending:"),
        hide: !readOnly && !item.locked && decision !== "hide",
        keep: !readOnly && !item.locked && decision !== "keep",
        merge: !readOnly && offerMerge && reentryTarget && item.reentry_target ? { target: item.reentry_target, targetLabel: reentryTarget.label } : null,
        cover: false,
        menu: { remove: !readOnly && person && !auditAdded && item.track_ids.length > 0, jump: true },
      },
      seekFrame,
      thumb,
      pending: pendingItems.has(id),
      accessibleName: `${item.label}, ${kindWord}, ${DECISION_STATE[column]}${lockedText}. ${asSentence(reason)} ${span ? spokenFrameRange(span.first, span.last, fps) : ""}`.trim(),
    };
    chips.push(chip);
  }

  // Unfixed audit spots (U chips): Needs you while uncovered.
  const labels = spotLabels(state.spots);
  const unresolvedLeaks = (job.audit?.leaks ?? []).filter((l) => l.unresolved);
  for (const [spotId, spot] of Object.entries(state.spots)) {
    if (spot.covered_by !== null) continue;
    const kind = spotKind(spot, unresolvedLeaks);
    const box = spot.boxes[String(spot.first)];
    const label = labels[spotId] ?? spotId;
    const reason = "The final check found this and couldn't cover it automatically";
    chips.push({
      id: `spot:${spotId}`,
      type: "spot",
      label: `Unfixed spot ${label}`,
      kindWord: KIND_WORD[kind],
      kind,
      column: "needs_you",
      reason,
      range: formatFrameRange(spot.first, spot.last, fps),
      spokenRange: spokenFrameRange(spot.first, spot.last, fps),
      span: { first: spot.first, last: spot.last },
      locked: false,
      isNew: false,
      changedByYou: false,
      removed: false,
      newLine: null,
      buttons: { why: false, hide: false, keep: false, merge: null, cover: !readOnly, menu: { remove: false, jump: true } },
      seekFrame: spot.first,
      thumb: box && keyframes.has(String(spot.first)) ? { frame: spot.first, box } : null,
      pending: false,
      accessibleName: `Unfixed spot ${label}, ${KIND_WORD[kind]}, needs you. ${asSentence(reason)} ${spokenFrameRange(spot.first, spot.last, fps)}`,
    });
  }
  return chips;
}

export function columnsOf(chips: readonly Chip[]): Record<Column, Chip[]> {
  const byStart = (a: Chip, b: Chip) => (a.span?.first ?? 0) - (b.span?.first ?? 0) || a.label.localeCompare(b.label, undefined, { numeric: true });
  return {
    hide: chips.filter((c) => c.column === "hide").sort(byStart),
    keep: chips.filter((c) => c.column === "keep").sort(byStart),
    needs_you: chips.filter((c) => c.column === "needs_you").sort(byStart),
  };
}

/** "8 hidden · 2 kept clear · 1 needs you" (§3.9: each item once; U chips count as needing you). */
export function headerCounts(columns: Record<Column, Chip[]>): string {
  const n = columns.needs_you.length;
  return `${columns.hide.length} hidden · ${columns.keep.length} kept clear · ${n} ${n === 1 ? "needs" : "need"} you`;
}

/** Kept participants offered as merge targets, the suggested one first (§3.4). */
export function mergeTargets(state: ReviewState, srcId: string): Array<{ id: string; label: string }> {
  const src = state.items[srcId];
  const out = visibleItems(state)
    .filter(([id, i]) => id !== srcId && i.kind === "person" && i.decision === "keep" && i.role === "participant" && !i.locked)
    .map(([id, i]) => ({ id, label: i.label }));
  return out.sort((a, b) => (a.id === src?.reentry_target ? -1 : b.id === src?.reentry_target ? 1 : 0));
}

export function isObjectChip(chip: Chip): boolean {
  return isObjectKind(chip.kind);
}

/**
 * A U chip's kind, by the audit-item rule over its spot's leak rows (§0, PRE-A §12): the unresolved
 * leaks inside the spot's span whose box overlaps the spot's box on that frame. Any face or person
 * row makes it a person, else any plate a plate, else other. Two spots on one frame keep their own.
 */
export function spotKind(spot: Pick<Spot, "first" | "last" | "boxes">, leaks: ReadonlyArray<{ frame: number; box: Box; kind: string }>): Item["kind"] {
  const overlaps = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
  const rows = leaks.filter((l) => {
    const box = spot.boxes[String(l.frame)];
    return l.frame >= spot.first && l.frame <= spot.last && box !== undefined && overlaps(l.box, box);
  });
  if (rows.some((l) => l.kind === "face" || l.kind === "person")) return "person";
  if (rows.some((l) => l.kind === "plate")) return "plate";
  return "other";
}
