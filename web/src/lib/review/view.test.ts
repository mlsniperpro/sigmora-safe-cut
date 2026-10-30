import { describe, expect, it } from "vitest";
import heroMock from "../../../mocks/job-review-hero1.json";
import bystanderMock from "../../../mocks/job-review-reentry-bystander.json";
import reentryMock from "../../../mocks/job-review-reentry.json";
import sampleMock from "../../../mocks/job-review-sample.json";
import unresolvedMock from "../../../mocks/result-unresolved-review.json";
import auditFailedLeak from "../../../mocks/result-audit-failed-with-leak.json";
import { jobResponseSchema, type JobResponse } from "../contracts";
import { initialState, step } from "./reducer";
import { buildChips, columnsOf, headerCounts, mergeTargets, spotKind } from "./view";

const load = (raw: unknown) => {
  const job: JobResponse = jobResponseSchema.parse(raw);
  const state = initialState({ items: job.items, plan: job.plan!, status: job.status, has_render: job.has_render, spots: job.audit?.spots ?? [] }, { tracks: job.tracks, roles: job.roles });
  return { job, state };
};

describe("review view model (UI-SPEC §3.3, §3.9)", () => {
  it("puts hero chips in their columns with labels, kinds, ranges and buttons", () => {
    const { job, state } = load(heroMock);
    const cols = columnsOf(buildChips(state, job));
    expect(cols.hide.map((c) => c.label)).toEqual(["Plate 1", "Face 4"]);
    expect(cols.keep.map((c) => c.label)).toEqual(["Face 2"]);
    expect(cols.needs_you.map((c) => c.label)).toEqual(["Face 6"]);
    const child = cols.hide.find((c) => c.label === "Face 4")!;
    expect(child).toMatchObject({ locked: true, kindWord: "Child", buttons: { hide: false, keep: false, menu: { remove: true } } });
    expect(child.accessibleName).toBe("Face 4, Child, hidden, always hidden. Child in the background, not addressed. 0:00 to 0:00");
    expect(cols.needs_you[0]!.buttons).toMatchObject({ hide: true, keep: true, why: true });
    expect(headerCounts(cols)).toBe("2 hidden · 1 kept clear · 1 needs you");
    expect(headerCounts({ hide: [], keep: [], needs_you: [] })).toBe("0 hidden · 0 kept clear · 0 need you");
    expect(headerCounts({ ...cols, needs_you: [...cols.needs_you, ...cols.needs_you] })).toBe("2 hidden · 1 kept clear · 2 need you");
  });

  it("gives every chip whose evidence frame is a keyframe a thumbnail", () => {
    for (const raw of [heroMock, sampleMock, reentryMock]) {
      const { job, state } = load(raw);
      for (const chip of buildChips(state, job)) expect(chip.thumb, chip.label).not.toBeNull();
    }
  });

  it("offers a merge only for a re-entry of a kept participant", () => {
    const r = load(reentryMock);
    const chip = buildChips(r.state, r.job).find((c) => c.label === "Face 9")!;
    expect(chip).toMatchObject({ isNew: true, newLine: "Might be Face 2: the tracker lost them and found them again.", buttons: { merge: { target: "i_1", targetLabel: "Face 2" } } });
    expect(mergeTargets(r.state, "i_9").map((t) => t.label)).toEqual(["Face 2"]);
    const b = load(bystanderMock);
    const van = buildChips(b.state, b.job).find((c) => c.label === "Face 8")!;
    expect(van).toMatchObject({ isNew: true, newLine: "The tracker lost this person and found them again. They stay hidden.", buttons: { merge: null } });
  });

  it("hides the merged item and shows its tracks under the target", () => {
    const r = load(reentryMock);
    const merged = step(r.state, { type: "MERGE", src: "i_9", dst: "i_1", edit_id: "m" }).state;
    const chips = buildChips(merged, r.job);
    expect(chips.map((c) => c.label)).toEqual(["Face 2"]);
    expect(chips[0]!.range).toBe("0:00–0:00");
    expect(chips[0]!.span).toEqual({ first: 0, last: 11 });
  });

  it("two unfixed spots that start on the same frame take their kinds from their own leaks", () => {
    const audit = unresolvedMock.audit;
    const two = {
      ...unresolvedMock,
      audit: {
        ...audit,
        unresolved: 2,
        spots: [audit.spots[0]!, { spot_id: "s2", first: 7, last: 7, boxes: { "7": [100, 600, 180, 640] }, covered_by: null }],
        leaks: [audit.leaks[0]!, { frame: 7, box: [100, 600, 180, 640], kind: "plate", detector: "egoblur", patched_item: null, unresolved: true }],
      },
    };
    const u = load(two);
    const spots = buildChips(u.state, u.job).filter((c) => c.type === "spot");
    expect(spots.map((c) => [c.label, c.kindWord])).toEqual([
      ["Unfixed spot U1", "Person"],
      ["Unfixed spot U2", "Number plate"],
    ]);
  });

  it("shows an unfixed spot as a U chip with Cover it, read-only in needs_you", () => {
    const u = load(unresolvedMock);
    const spot = columnsOf(buildChips(u.state, u.job)).needs_you.find((c) => c.type === "spot")!;
    expect(spot).toMatchObject({ label: "Unfixed spot U1", kindWord: "Person", buttons: { cover: true, why: false, menu: { remove: false, jump: true } } });
    const ro = load(auditFailedLeak);
    const roSpot = buildChips(ro.state, ro.job).find((c) => c.type === "spot")!;
    expect(roSpot.buttons.cover).toBe(false);
    expect(buildChips(ro.state, ro.job).every((c) => !c.buttons.hide && !c.buttons.keep)).toBe(true);
  });
});

describe("an unfixed spot's kind follows its own leak rows (§0)", () => {
  const leaks = [
    { frame: 15, box: [10, 10, 60, 60] as [number, number, number, number], kind: "face" },
    { frame: 15, box: [400, 300, 480, 340] as [number, number, number, number], kind: "plate" },
  ];
  it("two spots on the same first frame keep their own kinds", () => {
    expect(spotKind({ first: 15, last: 20, boxes: { "15": [12, 12, 58, 58] } }, leaks)).toBe("person");
    expect(spotKind({ first: 15, last: 20, boxes: { "15": [405, 305, 470, 335] } }, leaks)).toBe("plate");
  });
  it("a spot no leak row overlaps is other", () => {
    expect(spotKind({ first: 15, last: 20, boxes: { "15": [700, 10, 760, 60] } }, leaks)).toBe("other");
  });
});
