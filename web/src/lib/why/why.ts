/**
 * What the "Why?" drawer says (UI-SPEC §4.3, §4.6), as plain data the
 * component renders. Every string here is from the UI-SPEC copy deck.
 */
import type { Decision, Item, Role, RoleObject, RoleTrack, Roles, Scene, Transcript } from "../contracts";
import { KIND_PLURAL, ROLE_WORD, isObjectKind } from "../labels";
import { formatSeconds } from "../time";
import { rewriteFrameRefs, type FrameClock } from "./rewrite";

/** The item as the drawer sees it: the server item with the creator's local edits applied. */
export interface WhyItem {
  item: Pick<Item, "kind" | "origin" | "hold" | "track_ids" | "reason">;
  decision: Decision;
  decidedByCreator: boolean;
  removed: boolean;
  locked: boolean;
  /** The NEW badge: one of its tracks re-enters a track owned by another item. */
  isReentry: boolean;
}

export const WHY_HEADING: Readonly<Record<Decision, string>> = {
  hide: "Why it's hidden",
  keep: "Why it's kept clear",
  needs_you: "Why it needs you",
};

/** The fixed sentence, by the §4.3 precedence list (first match wins). */
export function fixedSentence(w: WhyItem, primary: RoleTrack | undefined, object: RoleObject | undefined): string {
  const { item, decision } = w;
  const hidden = decision === "hide";
  if (item.origin === "audit_patch") return "The final check found this after rendering and covered it.";
  if (w.removed && hidden) return "You asked to remove this person. They're fully covered everywhere they appear.";
  if (hidden && w.locked && item.kind === "child") return "Children are always hidden. You can't change this, because Safe Cut can't check a parent's consent.";
  if (w.decidedByCreator && decision === "keep") return "You chose to keep this clear.";
  if (w.decidedByCreator && hidden) return "You chose to hide this.";
  if (item.origin === "static") return "Muse Spark spotted something here that SAM 3.1 couldn't follow, so Safe Cut covered the area. Keep it clear if it's harmless.";
  if (hidden && item.kind === "other") return "Things Safe Cut found on a second look stay hidden unless you keep them clear.";
  if (hidden && w.isReentry) return "The tracker lost this person and found them again. Anyone found again starts hidden until you say who they are.";
  if (hidden && isObjectKind(item.kind)) return "Number plates, private screens and documents are hidden unless you decide otherwise.";
  if (hidden) return "People who aren't part of the story are hidden by default.";
  if (decision === "keep") return "All three checks agreed this person is part of the story, on at least two keyframes.";
  if (isObjectKind(item.kind) && (object?.sensitive === false || item.kind === "other")) {
    return `Muse Spark read this as nothing personal, but ${KIND_PLURAL[item.kind]} are only kept clear when you confirm.`;
  }
  switch (item.hold) {
    case "no_roles":
      return "Safe Cut's checks couldn't run on this, so it stays hidden until you decide.";
    case "no_scene":
      return "The scene check didn't run, so we didn't keep anyone clear automatically.";
    case "no_speech":
      return "The speech check didn't work for this clip, so we didn't keep anyone clear automatically.";
    case "unmatched_child":
      return "A child may be in this video and we couldn't tell who, so we didn't keep this person clear automatically. Keep them clear if they're part of the story.";
    case "no_speech_link":
      return "All three checks said part of the story, but Safe Cut couldn't link them to anyone speaking or introduced, so it's your call.";
    default:
      break;
  }
  if (primary && primary.role === "unsure" && primary.votes.length === 3 && primary.votes.every((v) => v === "participant")) {
    return "All three checks said part of the story, but on only one keyframe, so Safe Cut wants you to confirm. It stays hidden unless you keep it clear.";
  }
  const failed = primary ? Math.min(primary.failed_votes, 3) : 0;
  if (primary && failed > 0 && remainingAgree(primary)) {
    return `${failed} of the 3 checks didn't run, so Safe Cut couldn't decide on its own. It stays hidden unless you keep it clear.`;
  }
  return "The checks didn't all agree, so Safe Cut couldn't decide on its own. It stays hidden unless you keep it clear.";
}

/** The votes left after dropping `failed_votes` placeholders (`unsure` entries), in order. */
export function realVotes(track: Pick<RoleTrack, "votes" | "failed_votes">): Role[] {
  const real = [...track.votes];
  for (let k = 0; k < Math.min(track.failed_votes, real.length); k += 1) {
    const at = real.lastIndexOf("unsure");
    if (at >= 0) real.splice(at, 1);
  }
  return real;
}

function remainingAgree(track: Pick<RoleTrack, "votes" | "failed_votes">): boolean {
  const real = realVotes(track);
  return real.length > 0 && real.every((v) => v === real[0]);
}

export interface VoteMark {
  role: Role;
  word: string;
  agrees: boolean | null;
  /** The accessible text ("Check 1: Child, agrees with the majority"). */
  label: string;
}

export type VotesSection =
  | { kind: "none" }
  | { kind: "not_run"; line: string }
  | { kind: "object"; readAs: string | null; personal: string | null; plateLine: string | null; missedLine: string | null }
  | { kind: "votes"; count: number; failedLine: string | null; marks: VoteMark[]; evidence: string | null; escalation: string[] };

function majority(votes: readonly Role[]): Role | null {
  const counts = new Map<Role, number>();
  for (const v of votes) counts.set(v, (counts.get(v) ?? 0) + 1);
  for (const [role, n] of counts) if (n >= 2) return role;
  return null;
}

/** "What Muse Spark said (n checks)". */
export function votesSection(
  w: WhyItem,
  roles: Roles | undefined,
  primary: RoleTrack | undefined,
  object: RoleObject | undefined,
  missedWhat: string | null,
  clock: FrameClock,
): VotesSection {
  if (w.item.origin === "audit_patch" || w.item.origin === "static") return { kind: "none" };
  if (isObjectKind(w.item.kind)) {
    const has = object && object.content !== "";
    return {
      kind: "object",
      readAs: has ? `Muse Spark read it as: ${object.content}` : null,
      personal: has ? `Personal: ${object.sensitive ? "yes" : "no"}` : null,
      plateLine: w.item.kind === "plate" ? "Number plates are hidden by default. Only you can keep one clear." : null,
      missedLine: w.item.kind === "other" && missedWhat ? `Found when Muse Spark looked again for anything missed: ${missedWhat}` : null,
    };
  }
  if (!primary) return { kind: "none" };
  const failed = Math.min(primary.failed_votes, primary.votes.length);
  if (!roles || roles.status !== "ok" || failed >= 3) {
    return { kind: "not_run", line: "3 of the 3 checks didn't run." };
  }
  // `failed_votes` of the `unsure` entries are placeholders, not judgements.
  const real = realVotes(primary);
  const top = majority(real);
  const marks = real.map((role, i) => {
    const agrees = top === null ? null : role === top;
    const verdict = agrees === null ? "" : agrees ? ", agrees with the majority" : ", disagrees with the majority";
    return { role, word: ROLE_WORD[role], agrees, label: `Check ${i + 1}: ${ROLE_WORD[role]}${verdict}` };
  });
  const escalation: string[] = [];
  if (primary.escalated) {
    const quote = (text: string | null | undefined) => (text ? `“${rewriteFrameRefs(text, clock)}”` : null);
    if (primary.role === "child") {
      escalation.push("A longer, closer look found they may be under 18, so Safe Cut keeps them hidden.");
      const q = quote(primary.escalation_evidence);
      if (q) escalation.push(q);
    } else {
      const allParticipant = primary.votes.length === 3 && primary.votes.every((v) => v === "participant");
      escalation.push(
        allParticipant
          ? "Because it was seen on only one keyframe, Muse Spark took a longer, closer look once."
          : failed > 0 && remainingAgree(primary)
            ? `${failed} of the 3 checks didn't run, so Muse Spark took a longer, closer look once.`
            : "The checks disagreed, so Muse Spark took a longer, closer look once.",
      );
      if (primary.suggested_role) {
        escalation.push(`A longer, closer look suggests: ${ROLE_WORD[primary.suggested_role]}. You decide.`);
        const q = quote(primary.escalation_evidence);
        if (q) escalation.push(q);
      } else {
        escalation.push("A longer, closer look couldn't settle it.");
      }
    }
  }
  return {
    kind: "votes",
    count: real.length,
    failedLine: failed > 0 ? `${failed} of the 3 checks didn't run.` : null,
    marks,
    evidence: primary.evidence ? `“${rewriteFrameRefs(primary.evidence, clock)}”` : null,
    escalation,
  };
}

export interface SpeechLine {
  time: string;
  speaker: string;
  text: string;
  saidBy: boolean;
}

export type SpeechSection =
  | { kind: "no_sound"; line: string }
  | { kind: "lines"; heading: string; lines: SpeechLine[]; footer: string | null };

const MAX_LINES = 4;
const MAX_CHARS = 140;
const FALLBACK_SLACK_S = 1.5;

/** "What was said while {label} was on screen" (§4.3, overlap rule §4.6). */
export function speechSection(
  label: string,
  span: { first: number; last: number } | null,
  fps: number,
  audio: boolean,
  transcript: Transcript | undefined,
  speakerOfItem: string | null,
): SpeechSection {
  if (!audio) return { kind: "no_sound", line: "This clip has no sound." };
  const limited = !!transcript && (transcript.degraded || transcript.source_kind === "fallback");
  const heading = limited ? "What was probably said (speech check was limited)" : `What was said while ${label} was on screen`;
  const turns = transcript?.status === "ok" ? transcript.turns : [];
  if (turns.length === 0) {
    return {
      kind: "lines",
      heading,
      lines: [],
      footer: limited ? "Speech couldn't be checked reliably for this clip." : "No speech was transcribed. Safe Cut's speech check covers 25 languages, not including Swahili.",
    };
  }
  if (!span) return { kind: "lines", heading, lines: [], footer: `No speech is linked to ${label}.` };
  const slack = limited ? FALLBACK_SLACK_S : 0;
  const from = span.first / fps - slack;
  const to = (span.last + 1) / fps + slack;
  const lines = turns
    .filter((t) => t.start < to && t.end >= from)
    .slice(0, MAX_LINES)
    .map((t) => ({
      time: `${limited ? "about " : ""}${formatSeconds(t.start)}`,
      speaker: `Voice ${t.speaker}`,
      text: t.text.length > MAX_CHARS ? `${t.text.slice(0, MAX_CHARS)}…` : t.text,
      saidBy: speakerOfItem !== null && t.speaker === speakerOfItem,
    }));
  const linked = speakerOfItem !== null && lines.some((l) => l.saidBy);
  return { kind: "lines", heading, lines, footer: linked ? null : `No speech is linked to ${label}.` };
}

/** The speaker linked to an item through `matches_participant` → `scene.participants[k].speaker`. */
export function linkedSpeaker(primary: RoleTrack | undefined, scene: Scene | undefined): string | null {
  const k = primary?.matches_participant;
  if (k === null || k === undefined || !scene) return null;
  return scene.participants[k]?.speaker ?? null;
}

