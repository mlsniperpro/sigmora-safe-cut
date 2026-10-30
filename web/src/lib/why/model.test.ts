import { describe, expect, it } from "vitest";
import cafeMock from "../../../mocks/job-review-cafe.json";
import heroMock from "../../../mocks/job-review-hero1.json";
import noAudioMock from "../../../mocks/job-review-no-audio.json";
import limitedMock from "../../../mocks/job-review-speech-limited.json";
import speechMock from "../../../mocks/job-review-speech-fallback.json";
import whyMock from "../../../mocks/job-review-why-rows.json";
import { jobResponseSchema, type JobResponse } from "../contracts";
import { buildWhy, type LocalItemState } from "./model";
import { speechSection } from "./why";

const parse = (raw: unknown): JobResponse => jobResponseSchema.parse(raw);
const localOf = (job: JobResponse, id: string, over: Partial<LocalItemState> = {}): LocalItemState => {
  const item = job.items.find((i) => i.item_id === id)!;
  return { decision: item.decision, decided_by: item.decided_by, removed: item.removed_by_creator, locked: item.locked, isReentry: false, track_ids: item.track_ids, ...over };
};
const why = (raw: unknown, id: string, over: Partial<LocalItemState> = {}) => {
  const job = parse(raw);
  return buildWhy(job, id, localOf(job, id, over))!;
};

describe("Why drawer (UI-SPEC §4.3)", () => {
  it.each([
    ["i_10", "Safe Cut's checks couldn't run on this, so it stays hidden until you decide."],
    ["i_11", "The scene check didn't run, so we didn't keep anyone clear automatically."],
    ["i_12", "The speech check didn't work for this clip, so we didn't keep anyone clear automatically."],
    ["i_13", "A child may be in this video and we couldn't tell who, so we didn't keep this person clear automatically. Keep them clear if they're part of the story."],
    ["i_14", "All three checks said part of the story, but Safe Cut couldn't link them to anyone speaking or introduced, so it's your call."],
    ["i_15", "Muse Spark spotted something here that SAM 3.1 couldn't follow, so Safe Cut covered the area. Keep it clear if it's harmless."],
    ["i_16", "Things Safe Cut found on a second look stay hidden unless you keep them clear."],
    ["i_17", "Children are always hidden. You can't change this, because Safe Cut can't check a parent's consent."],
    ["i_18", "The checks didn't all agree, so Safe Cut couldn't decide on its own. It stays hidden unless you keep it clear."],
    ["i_19", "All three checks said part of the story, but on only one keyframe, so Safe Cut wants you to confirm. It stays hidden unless you keep it clear."],
    ["i_20", "You asked to remove this person. They're fully covered everywhere they appear."],
    ["i_21", "You chose to keep this clear."],
    ["i_22", "You chose to hide this."],
    ["i_23", "People who aren't part of the story are hidden by default."],
  ])("%s gets its fixed sentence", (id, sentence) => {
    expect(why(whyMock, id).fixed).toBe(sentence);
  });

  it("hero items: kept participant, locked child, plate, disagreed", () => {
    expect(why(heroMock, "i_1").fixed).toBe("All three checks agreed this person is part of the story, on at least two keyframes.");
    expect(why(heroMock, "i_2").fixed).toMatch(/^Children are always hidden/);
    expect(why(heroMock, "i_3").fixed).toBe("Number plates, private screens and documents are hidden unless you decide otherwise.");
    expect(why(heroMock, "i_4").fixed).toMatch(/^The checks didn't all agree/);
    expect(why(heroMock, "i_4", { isReentry: true, decision: "hide" }).fixed).toMatch(/^The tracker lost this person/);
  });

  it("a removed person kept clear again says 'kept clear by you', never the removed sentence", () => {
    expect(why(whyMock, "i_20", { decision: "keep", removed: false }).fixed).toBe("You chose to keep this clear.");
  });

  it("the harmless café menu needs you with the plural kind word", () => {
    expect(why(cafeMock, "i_6").fixed).toBe("Muse Spark read this as nothing personal, but screens are only kept clear when you confirm.");
    const v = why(cafeMock, "i_6").votes;
    expect(v).toMatchObject({ kind: "object", readAs: "Muse Spark read it as: café menu", personal: "Personal: no", plateLine: null });
  });

  it("rewrites frame references in reasons and quoted evidence, keeping Muse Spark's words in Details", () => {
    const w = why(heroMock, "i_1");
    expect(w.reason).toBe("The guest: introduced at the start, speaks to camera");
    expect(w.votes).toMatchObject({ kind: "votes", evidence: "“introduced at 0:00, speaks to camera at 0:00 and 0:00”" });
    expect(w.details.museWords).toContain("F 000003");
    expect(why(whyMock, "i_15").reason).toBe("Possible missed object at 0:00");
  });

  it("marks votes against the majority, with text for screen readers", () => {
    const v = why(heroMock, "i_4").votes;
    if (v.kind !== "votes") throw new Error("expected votes");
    expect(v.marks.map((m) => m.agrees)).toEqual([true, false, true]);
    expect(v.marks[1]?.label).toBe("Check 2: Part of the story, disagrees with the majority");
    expect(v.escalation).toEqual([
      "The checks disagreed, so Muse Spark took a longer, closer look once.",
      "A longer, closer look suggests: Not part of the story. You decide.",
      "“faces the lens at 0:00 but is never addressed and never speaks”",
    ]);
  });

  it("shows no marks when all three checks differ, and 'couldn't settle it' without a suggestion", () => {
    const v = why(whyMock, "i_18").votes;
    if (v.kind !== "votes") throw new Error("expected votes");
    expect(v.marks.every((m) => m.agrees === null)).toBe(true);
    expect(v.escalation).toContain("A longer, closer look couldn't settle it.");
  });

  it("an escalated child gets only the under-18 line and its evidence", () => {
    const v = why(whyMock, "i_17").votes;
    if (v.kind !== "votes") throw new Error("expected votes");
    expect(v.escalation[0]).toBe("A longer, closer look found they may be under 18, so Safe Cut keeps them hidden.");
    expect(v.escalation).toHaveLength(2);
  });

  it("drops failure placeholders from the marks and says how many didn't run", () => {
    const v = why(whyMock, "i_23").votes;
    if (v.kind !== "votes") throw new Error("expected votes");
    expect(v.count).toBe(2);
    expect(v.failedLine).toBe("1 of the 3 checks didn't run.");
    expect(why(whyMock, "i_10").votes).toEqual({ kind: "not_run", line: "3 of the 3 checks didn't run." });
  });

  it("says when a check didn't run and the rest agree, in the sentence and the escalation", () => {
    const job = parse(whyMock);
    const track = job.roles!.tracks.find((t) => t.track_id === "face:23")!;
    track.votes = ["participant", "participant", "unsure"];
    track.escalated = true;
    track.suggested_role = "participant";
    const item = job.items.find((i) => i.item_id === "i_23")!;
    item.decision = "needs_you";
    const w = buildWhy(job, "i_23", localOf(job, "i_23"))!;
    expect(w.fixed).toBe("1 of the 3 checks didn't run, so Safe Cut couldn't decide on its own. It stays hidden unless you keep it clear.");
    if (w.votes.kind !== "votes") throw new Error("expected votes");
    expect(w.votes.count).toBe(2);
    expect(w.votes.escalation[0]).toBe("1 of the 3 checks didn't run, so Muse Spark took a longer, closer look once.");
  });

  it("names what the miss loop found for an other item", () => {
    expect(why(whyMock, "i_16").votes).toMatchObject({ kind: "object", missedLine: "Found when Muse Spark looked again for anything missed: addressed envelope" });
  });

  it("links the guest's lines through matches_participant", () => {
    const s = why(heroMock, "i_1").speech;
    expect(s).toMatchObject({ kind: "lines", heading: "What was said while Face 2 was on screen", footer: null });
    if (s.kind !== "lines") throw new Error("expected lines");
    expect(s.lines.map((l) => [l.time, l.speaker, l.saidBy])).toEqual([
      ["0:00", "Voice S1", false],
      ["0:00", "Voice S2", true],
    ]);
  });

  it("widens the window by 1.5 s only for a fallback transcript", () => {
    const fallback = why(speechMock, "i_4").speech;
    expect(fallback).toMatchObject({ kind: "lines", heading: "What was probably said (speech check was limited)" });
    if (fallback.kind !== "lines") throw new Error("expected lines");
    expect(fallback.lines.map((l) => l.time)).toEqual(["about 0:01"]);
    const primary = why({ ...speechMock, transcript: { ...speechMock.transcript, source_kind: "primary" } }, "i_4").speech;
    if (primary.kind !== "lines") throw new Error("expected lines");
    expect(primary.lines).toEqual([]);
    expect(primary.footer).toBe("No speech is linked to Face 4.");
    const host = why({ ...speechMock, transcript: { ...speechMock.transcript, source_kind: "primary" } }, "i_1").speech;
    if (host.kind !== "lines") throw new Error("expected lines");
    expect(host.lines).toHaveLength(1);
  });

  it("covers no sound, limited and empty transcripts", () => {
    expect(why(noAudioMock, "i_1").speech).toEqual({ kind: "no_sound", line: "This clip has no sound." });
    expect(why(limitedMock, "i_1").speech).toMatchObject({ footer: "Speech couldn't be checked reliably for this clip." });
    const empty = why({ ...heroMock, transcript: { ...heroMock.transcript, turns: [] } }, "i_1").speech;
    expect(empty).toMatchObject({ footer: "No speech was transcribed. Safe Cut's speech check covers 25 languages, not including Swahili." });
  });

  it("fills Details with words, not codes", () => {
    const d = why(heroMock, "i_4").details;
    expect(d).toMatchObject({ decidedBy: "Decided by Muse Spark", cover: "Cover: Coarse pixels", tracks: "Tracks: face:6", frames: "Frames 8–11" });
    expect(why(heroMock, "i_1").details.cover).toBe("Cover: none (kept clear)");
    expect(d.models).toBe("Models: Muse Spark 1.3 · SAM 3.1 · Muse Voice Transcribe");
  });
});

describe("speech lines and footer (§4.3, §4.6)", () => {
  const turn = (speaker: string, start: number, text: string) => ({ speaker, start, end: start + 0.5, text });
  const transcript = (turns: ReturnType<typeof turn>[]) => ({ status: "ok", source: null, source_kind: "primary" as const, degraded: false, turns });

  it("a linked speaker with no lines on screen gets no 'No speech is linked' footer", () => {
    const s = speechSection("Face 2", { first: 0, last: 9 }, 10, true, transcript([turn("S1", 0.1, "hello"), turn("S2", 5, "later")]), "S2");
    expect(s).toMatchObject({ kind: "lines", footer: null });
    if (s.kind !== "lines") throw new Error("expected lines");
    expect(s.lines.map((l) => l.speaker)).toEqual(["Voice S1"]);
  });

  it("the footer shows when no speaker is linked, even with no span", () => {
    expect(speechSection("Face 4", null, 10, true, transcript([turn("S1", 0, "hi")]), null)).toMatchObject({ footer: "No speech is linked to Face 4." });
    expect(speechSection("Face 4", null, 10, true, transcript([turn("S1", 0, "hi")]), "S1")).toMatchObject({ footer: null });
  });

  it("within the four-line cap the linked speaker's lines come first, shown in time order", () => {
    const turns = [turn("S1", 0, "a"), turn("S1", 0.1, "b"), turn("S1", 0.2, "c"), turn("S1", 0.3, "d"), turn("S2", 0.4, "mine")];
    const s = speechSection("Face 2", { first: 0, last: 9 }, 10, true, transcript(turns), "S2");
    if (s.kind !== "lines") throw new Error("expected lines");
    expect(s.lines.map((l) => [l.text, l.saidBy])).toEqual([
      ["a", false],
      ["b", false],
      ["c", false],
      ["mine", true],
    ]);
  });
});
