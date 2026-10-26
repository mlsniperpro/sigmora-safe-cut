import { describe, expect, it } from "vitest";
import heroMock from "../../../mocks/job-review-hero1.json";
import bystanderMock from "../../../mocks/job-review-reentry-bystander.json";
import reentryMock from "../../../mocks/job-review-reentry.json";
import sampleMock from "../../../mocks/job-review-sample.json";
import unresolvedMock from "../../../mocks/result-unresolved-review.json";
import auditFailedLeak from "../../../mocks/result-audit-failed-with-leak.json";
import { jobResponseSchema, type JobResponse } from "../contracts";
import { initialState, step } from "./reducer";
import { buildChips, columnsOf, headerCounts, mergeTargets } from "./view";

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

  it("shows an unfixed spot as a U chip with Cover it, read-only in needs_you", () => {
    const u = load(unresolvedMock);
    const spot = columnsOf(buildChips(u.state, u.job)).needs_you.find((c) => c.type === "spot")!;
    expect(spot).toMatchObject({ label: "Unfixed spot U1", kindWord: "Person", buttons: { cover: true, why: false } });
    const ro = load(auditFailedLeak);
    const roSpot = buildChips(ro.state, ro.job).find((c) => c.type === "spot")!;
    expect(roSpot.buttons.cover).toBe(false);
    expect(buildChips(ro.state, ro.job).every((c) => !c.buttons.hide && !c.buttons.keep)).toBe(true);
  });
});
