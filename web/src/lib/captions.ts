/**
 * WebVTT captions from the job's transcript (UI-SPEC §9: captions on every video with speech).
 * Turn times are on the prepared clock, the same clock the player uses.
 */
import type { Transcript } from "./contracts";

function stamp(seconds: number): string {
  const ms = Math.max(0, Math.round(seconds * 1000));
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  const r = ms % 1000;
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${p(h)}:${p(m)}:${p(s)}.${p(r, 3)}`;
}

/** Cue text can't contain "-->" or blank lines, and "<" or "&" would be read as markup. */
function cueText(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/-->/g, "→").replace(/\s*\n\s*/g, " ").trim();
}

export function transcriptToVtt(transcript: Transcript | undefined): string | null {
  if (!transcript || transcript.status !== "ok") return null;
  const turns = transcript.turns.filter((t) => Number.isFinite(t.start) && Number.isFinite(t.end) && t.end > t.start && t.text.trim());
  if (turns.length === 0) return null;
  const cues = turns.map((t, i) => `${i + 1}\n${stamp(t.start)} --> ${stamp(t.end)}\n<v Voice ${cueText(t.speaker)}>${cueText(t.text)}`);
  return `WEBVTT\n\n${cues.join("\n\n")}\n`;
}
