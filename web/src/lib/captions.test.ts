import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { transcriptToVtt } from "./captions";

const t = (turns: Array<{ speaker: string; start: number; end: number; text: string }>) => ({ status: "ok", source: "x", source_kind: "primary" as const, degraded: false, turns });

describe("transcriptToVtt", () => {
  it("builds cues on the prepared clock with the speaker as a voice", () => {
    expect(transcriptToVtt(t([{ speaker: "S2", start: 1.8, end: 4.4, text: "Hi, I'm Amina." }]))).toBe("WEBVTT\n\n1\n00:00:01.800 --> 00:00:04.400\n<v Voice S2>Hi, I'm Amina.\n");
  });
  it("returns null with no usable turns or a failed transcript", () => {
    expect(transcriptToVtt(undefined)).toBeNull();
    expect(transcriptToVtt(t([]))).toBeNull();
    expect(transcriptToVtt({ ...t([{ speaker: "S1", start: 0, end: 1, text: "a" }]), status: "failed" })).toBeNull();
    expect(transcriptToVtt(t([{ speaker: "S1", start: 2, end: 1, text: "backwards" }]))).toBeNull();
  });
  it("escapes markup and the cue arrow so a transcript can't break the file", () => {
    fc.assert(
      fc.property(fc.string(), (text) => {
        const vtt = transcriptToVtt(t([{ speaker: "S1", start: 0, end: 1, text: `${text}x` }])) ?? "";
        const body = vtt.split("\n").slice(4).join("\n");
        return !body.includes("-->") && !/<(?!v Voice)/.test(body) && body.split("\n").filter(Boolean).length <= 1;
      }),
      { numRuns: 2000 },
    );
  });
});
