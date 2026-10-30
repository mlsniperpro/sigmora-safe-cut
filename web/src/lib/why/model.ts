/**
 * Assembles everything the Why drawer shows for one item from the job response
 * and the creator's local edits.
 */
import type { Decision, JobResponse } from "../contracts";
import { DECIDED_BY_WORD, KIND_WORD, STYLE_WORD, capitalise, itemLabel, itemSpan, primaryTrackId } from "../labels";
import { rewriteFrameRefs } from "./rewrite";
import { WHY_HEADING, fixedSentence, linkedSpeaker, speechSection, votesSection, type SpeechSection, type VotesSection, type WhyItem } from "./why";

export interface LocalItemState {
  decision: Decision;
  decided_by: "policy" | "model" | "creator";
  removed: boolean;
  locked: boolean;
  isReentry: boolean;
  /** Track IDs shown under the item, including merged ones. */
  track_ids: string[];
}

export interface WhyModel {
  label: string;
  origin: "sam" | "static" | "audit_patch" | null;
  kindWord: string;
  heading: string;
  reason: string | null;
  fixed: string;
  votes: VotesSection;
  speech: SpeechSection;
  primaryTrack: string | null;
  otherTracks: string[];
  evidenceFrames: number[];
  /** False for items with no SoM keyframe (§4.3): added by the audit, or static areas SAM 3.1 couldn't track. */
  hasKeyframe: boolean;
  details: { decidedBy: string; cover: string; tracks: string; frames: string | null; museWords: string | null; models: string | null };
}

const MODEL_NAMES: Readonly<Record<string, string>> = {
  "muse-spark-1.3": "Muse Spark 1.3",
  "muse-spark-1.2": "Muse Spark 1.2",
  "muse-wonder-1.0": "Muse Wonder 1.0",
  "sam-3.1": "SAM 3.1",
  "muse-voice-transcribe-1.0": "Muse Voice Transcribe",
};

/**
 * The receipt-style model list (§4.3 Details): the job's `models`, or else the models its own
 * passes name. Null when the response names none, so no list is made up.
 */
export function modelList(job: Pick<JobResponse, "models" | "roles" | "scene" | "transcript" | "tracks">): string | null {
  // Tracks come only from SAM 3.1 (the model §4.3's own copy names); the rest name their model.
  const named = job.models ? Object.values(job.models) : [job.roles?.model, job.scene?.model, job.tracks.length ? "sam-3.1" : null, job.transcript?.source];
  const ids = [...new Set(named.filter((id): id is string => !!id))];
  return ids.length ? ids.map((id) => MODEL_NAMES[id] ?? id).join(" · ") : null;
}

export function buildWhy(job: JobResponse, itemId: string, local: LocalItemState): WhyModel | null {
  const item = job.items.find((i) => i.item_id === itemId);
  if (!item || !job.job) return null;
  const clock = { fps: job.job.fps, frames: job.job.frames };
  const label = itemLabel(item);
  const primaryId = primaryTrackId(local.track_ids);
  const primary = job.roles?.tracks.find((t) => t.track_id === primaryId);
  const object = job.roles?.objects.find((o) => o.track_id === primaryId);
  const missed = job.roles?.missed.find((m) => m.track_ids?.some((t) => local.track_ids.includes(t)));
  const w: WhyItem = {
    item,
    decision: local.decision,
    decidedByCreator: local.decided_by === "creator",
    removed: local.removed,
    locked: local.locked,
    isReentry: local.isReentry,
  };
  const tracksById = new Map(job.tracks.map((t) => [t.track_id, t]));
  const span = itemSpan({ track_ids: local.track_ids, first: item.first ?? null, last: item.last ?? null }, tracksById);
  const evidence = item.evidence_frames.length > 0 ? item.evidence_frames : primary?.frames ?? [];
  const escalationFrames = primary?.escalated ? primary.escalation_frames ?? [] : [];
  // A cover the creator added in review has no track, only its spot: it is the audit's too.
  const origin = item.origin ?? (item.track_ids.length === 0 && item.spot_id ? "audit_patch" : null);
  const evidenceFrames = [...new Set([...evidence, ...escalationFrames])].sort((a, b) => a - b);
  return {
    label,
    origin,
    kindWord: KIND_WORD[item.kind],
    heading: WHY_HEADING[local.decision],
    reason: item.origin === "audit_patch" ? null : capitalise(rewriteFrameRefs(item.reason, clock)),
    fixed: fixedSentence(w, primary, object),
    votes: votesSection(w, job.roles, primary, object, missed?.what ?? null, clock),
    speech: speechSection(label, span, clock.fps, job.job.audio, job.transcript, linkedSpeaker(primary, job.scene)),
    primaryTrack: primaryId,
    otherTracks: local.track_ids.filter((t) => t !== primaryId),
    evidenceFrames,
    hasKeyframe: origin !== "audit_patch" && origin !== "static" && evidenceFrames.length > 0,
    details: {
      decidedBy: `Decided by ${DECIDED_BY_WORD[local.decided_by]}`,
      cover: local.decision === "keep" || item.style === null ? "Cover: none (kept clear)" : `Cover: ${STYLE_WORD[local.removed ? "person_solid" : item.style]}`,
      tracks: `Tracks: ${local.track_ids.length ? local.track_ids.join(" · ") : "none"}`,
      frames: span ? `Frames ${span.first}–${span.last}` : null,
      museWords: primary?.evidence ? `Muse Spark's words: “${primary.evidence}”` : null,
      models: (() => {
        const list = modelList(job);
        return list ? `Models: ${list}` : null;
      })(),
    },
  };
}
