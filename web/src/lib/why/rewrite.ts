/**
 * Rewrites Muse Spark's frame references into prepared-clock times (UI-SPEC §4.3).
 * Works sentence by sentence; numbers that aren't valid frames stay as written.
 */
import { formatFrame } from "../time";

const ELEMENT = String.raw`\d+(?:\s*[–-]\s*\d+)?`;
const FRAME_LIST = new RegExp(String.raw`\bframes?\s+(${ELEMENT}(?:\s*(?:,\s*and|,|and)\s*${ELEMENT})*)`, "gi");
const F_LABEL = /\bF\s?0*(\d+)\b/gi;
const BARE_RANGE = /\b(\d+)\s*[–-]\s*(\d+)\b/g;
const ELEMENT_RE = new RegExp(ELEMENT, "g");
const MARK = "\u0000";

export interface FrameClock {
  fps: number;
  frames: number;
}

function convertElement(element: string, clock: FrameClock): string | null {
  const [a, b] = element.split(/\s*[–-]\s*/).map(Number);
  const valid = (n: number | undefined): n is number => n !== undefined && Number.isInteger(n) && n >= 0 && n < clock.frames;
  if (!valid(a)) return null;
  if (b === undefined) return formatFrame(a, clock.fps);
  if (!valid(b)) return null;
  return `${formatFrame(a, clock.fps)}–${formatFrame(b, clock.fps)}`;
}

function rewriteSentence(sentence: string, clock: FrameClock): string {
  const converted: string[] = [];
  const hold = (text: string) => `${MARK}${converted.push(text) - 1}${MARK}`;

  // Rule 1: "frame(s)" followed by a list of numbers or ranges; the word is dropped.
  let out = sentence.replace(FRAME_LIST, (whole, list: string) => {
    const parts = list.match(ELEMENT_RE) ?? [];
    const times = parts.map((p) => convertElement(p, clock));
    if (times.some((t) => t === null)) return whole;
    let i = 0;
    return list.replace(ELEMENT_RE, () => hold(times[i++] as string));
  });
  // Rule 2: burned-in labels, "F 000090" or "F90".
  out = out.replace(F_LABEL, (whole, digits: string) => {
    const time = convertElement(String(Number(digits)), clock);
    return time === null ? whole : hold(time);
  });
  // Rule 3: after a converted reference, later bare ranges whose ends are both ≥ 10.
  const first = out.indexOf(MARK);
  if (first >= 0) {
    const head = out.slice(0, first);
    const tail = out.slice(first).replace(BARE_RANGE, (whole, a: string, b: string) => {
      if (Number(a) < 10 || Number(b) < 10) return whole;
      const time = convertElement(`${a}-${b}`, clock);
      return time === null ? whole : hold(time);
    });
    out = head + tail;
  }
  return out.replace(new RegExp(`${MARK}(\\d+)${MARK}`, "g"), (_, i: string) => converted[Number(i)] ?? "");
}

export function rewriteFrameRefs(text: string, clock: FrameClock): string {
  return text
    .split(/(?<=[.;])/)
    .map((sentence) => rewriteSentence(sentence, clock))
    .join("");
}
