/**
 * The client's schemas accept what WP0's contracts produce. The JSON under `__fixtures__/wp0-j-example`
 * is WP0's own `fixtures/contracts/j_example` (origin/wp0-foundation 9003bad), copied as is: the
 * API embeds these files in its responses (UI-SPEC §8), so a field WP0 allows to be null or absent
 * must not fail the whole page here.
 */
import { describe, expect, it } from "vitest";
import audit from "./__fixtures__/wp0-j-example/audit.json";
import decisions from "./__fixtures__/wp0-j-example/decisions.json";
import job from "./__fixtures__/wp0-j-example/job.json";
import plan from "./__fixtures__/wp0-j-example/plan.json";
import roles from "./__fixtures__/wp0-j-example/roles.json";
import scene from "./__fixtures__/wp0-j-example/scene.json";
import tracks from "./__fixtures__/wp0-j-example/tracks.json";
import transcript from "./__fixtures__/wp0-j-example/transcript.json";
import { auditSchema, itemSchema, jobResponseSchema, missedSchema, planSchema, rolesSchema, sceneSchema, spotSchema, trackSchema, transcriptSchema } from "./contracts";

describe("WP0 contracts (j_example) parse with the client's schemas", () => {
  it.each([
    ["audit.json", auditSchema, audit],
    ["roles.json", rolesSchema, roles],
    ["plan.json", planSchema, plan],
    ["transcript.json", transcriptSchema, transcript],
    ["scene.json", sceneSchema, scene],
  ] as const)("%s", (_name, schema, data) => {
    const parsed = schema.safeParse(data);
    expect(parsed.error?.issues ?? []).toEqual([]);
  });

  it("decisions.json items and tracks.json tracks", () => {
    for (const item of decisions.items) expect(itemSchema.safeParse(item).error?.issues ?? []).toEqual([]);
    for (const track of tracks.tracks) expect(trackSchema.safeParse(track).error?.issues ?? []).toEqual([]);
  });

  it("a whole job response built from them, as the API embeds the files", () => {
    const body = {
      job_id: job.job_id,
      mode: "live",
      status: "needs_you",
      deletes_at: "2026-10-28T10:00:00Z",
      job: { fps: job.fps, width: job.width, height: job.height, frames: job.frames, times: Array.from({ length: job.frames }, (_, i) => i / job.fps) },
      items: decisions.items,
      tracks: tracks.tracks,
      roles,
      plan,
      transcript,
      scene,
      audit,
    };
    expect(jobResponseSchema.safeParse(body).error?.issues ?? []).toEqual([]);
  });
});

describe("WP0 values the j_example happens not to use", () => {
  it("the audit.json example from ARCHITECTURE §3.8: the second opinion off, with no model", () => {
    const example = {
      frames_scanned: 900,
      egoblur: { model: "egoblur-gen2", faces: 1, plates: 0 },
      leaks: [{ frame: 401, box: [10, 10, 60, 60], kind: "face", detector: "egoblur", patched_item: "p_1" }],
      redteam: [{ frame: 0, finding: "none" }],
      unresolved: 0,
      passes: 2,
      sample_step: 30,
      spots: [],
      blocked_reason: null,
      audit_budget_cause: null,
      open_weight: { model: null, status: "off", frames: 0, findings: 0 },
      redteam_open: [],
    };
    const parsed = auditSchema.parse(example);
    expect(parsed.open_weight).toEqual({ model: null, status: "off", frames: 0, findings: 0 });
  });

  it("an open_weight it can't read counts as absent: the second opinion never blocks a job", () => {
    const base = auditSchema.parse(audit);
    expect(auditSchema.parse({ ...audit, open_weight: { status: "later" } }).open_weight).toBeNull();
    expect(base.open_weight).toBeUndefined();
  });

  it("a box-only miss (point null) and a spot with no covered_by key", () => {
    expect(missedSchema.parse({ what: "addressed envelope", sam_phrase: "envelope", frame: 9, point: null, box: [300, 500, 380, 560], track_ids: ["envelope:1"] }).point).toBeNull();
    expect(spotSchema.parse({ spot_id: "s1", first: 3, last: 5, boxes: { "3": [1, 2, 3, 4] } }).covered_by).toBeNull();
  });
});
