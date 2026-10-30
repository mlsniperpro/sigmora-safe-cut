/**
 * Item labels, kinds and the shared vocabulary (UI-SPEC §0).
 */
import type { DecidedBy, Decision, Item, Kind, Role, Style, Track } from "./contracts";

const CONCEPT_WORDS: Readonly<Record<string, string>> = {
  face: "Face",
  person: "Person",
  "license plate": "Plate",
  screen: "Screen",
  phone: "Phone",
  document: "Document",
  "name badge": "Badge",
};

const TRACK_ID = /^(.+):(\d+)$/;

/** `face:7` → "Face 7"; any other concept → its phrase capitalised. Malformed IDs are shown raw. */
export function trackLabel(trackId: string): string {
  const match = TRACK_ID.exec(trackId);
  if (!match) {
    console.warn(`track ID "${trackId}" isn't <concept>:<n>; showing it raw`);
    return trackId;
  }
  const concept = match[1] ?? "";
  const n = match[2] ?? "";
  const word = CONCEPT_WORDS[concept] ?? concept.charAt(0).toUpperCase() + concept.slice(1);
  return `${word} ${n}`;
}

/** The item's primary track: its first `face:*` track if it has one, otherwise its first track. */
export function primaryTrackId(trackIds: readonly string[]): string | null {
  return trackIds.find((t) => t.startsWith("face:")) ?? trackIds[0] ?? null;
}

/** Display label for an item; audit-added items use their server label (A1…). */
export function itemLabel(item: Pick<Item, "track_ids" | "audit_label" | "item_id">): string {
  if (item.audit_label) return item.audit_label;
  const primary = primaryTrackId(item.track_ids);
  return primary ? trackLabel(primary) : item.item_id;
}

export const KIND_WORD: Readonly<Record<Kind, string>> = {
  person: "Person",
  child: "Child",
  plate: "Number plate",
  screen: "Screen",
  document: "Document",
  other: "Other item",
};

export const KIND_PLURAL: Readonly<Record<Kind, string>> = {
  person: "people",
  child: "children",
  plate: "number plates",
  screen: "screens",
  document: "documents",
  other: "items like this",
};

export const OBJECT_KINDS: ReadonlySet<Kind> = new Set<Kind>(["plate", "screen", "document", "other"]);

export function isObjectKind(kind: Kind): boolean {
  return OBJECT_KINDS.has(kind);
}

export const DECISION_WORD: Readonly<Record<Decision, string>> = {
  hide: "Hidden",
  keep: "Kept clear",
  needs_you: "Needs you",
};

export const ROLE_WORD: Readonly<Record<Role, string>> = {
  participant: "Part of the story",
  bystander: "Not part of the story",
  child: "Child",
  unsure: "Not sure",
};

export const DECIDED_BY_WORD: Readonly<Record<DecidedBy, string>> = {
  policy: "Safe Cut's rules",
  model: "Muse Spark",
  creator: "You",
};

export const STYLE_WORD: Readonly<Record<Style, string>> = {
  solid: "Solid cover",
  pixelate: "Coarse pixels",
  person_solid: "Whole person covered",
};

/** Pluralise a count: `plural(2, "leak")` → "2 leaks". */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** First letter capitalised, nothing else touched (reasons arrive lowercase-first). */
export function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The item's frame span: union of its tracks' spans, or its own span for audit-added items. */
export function itemSpan(
  item: Pick<Item, "track_ids" | "first" | "last">,
  tracksById: ReadonlyMap<string, Pick<Track, "first" | "last">>,
): { first: number; last: number } | null {
  let first = Number.POSITIVE_INFINITY;
  let last = Number.NEGATIVE_INFINITY;
  for (const id of item.track_ids) {
    const t = tracksById.get(id);
    if (!t) continue;
    first = Math.min(first, t.first);
    last = Math.max(last, t.last);
  }
  if (Number.isFinite(first)) return { first, last };
  if (item.first != null && item.last != null) return { first: item.first, last: item.last };
  return null;
}

/** Ends text as a sentence, without doubling a full stop the API text already has. */
export function asSentence(text: string): string {
  const trimmed = text.trimEnd();
  return /[.!?…]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}
