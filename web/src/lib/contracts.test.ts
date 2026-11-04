import { describe, expect, it } from "vitest";
import auditAck from "../../mocks/audit-ack.json";
import demoHero from "../../mocks/demo-hero.json";
import renderAck from "../../mocks/render-ack.json";
import resultClean from "../../mocks/result-clean.json";
import reviewAck from "../../mocks/review-ack.json";
import { actionAckSchema, demoResponseSchema, planSchema, resultResponseSchema, reviewAckSchema, trackSchema } from "./contracts";

/** The fixture without the fields the spec doesn't give that response. */
function without(fixture: object, ...keys: string[]): Record<string, unknown> {
  const out: Record<string, unknown> = { ...fixture };
  for (const key of keys) delete out[key];
  return out;
}

describe("contracts", () => {
  it("a track without reentry_of (WP0's default None, key left out) parses as null", () => {
    const track = trackSchema.parse({ track_id: "face:1", concept: "face", first: 0, last: 3, boxes: { "0": [1, 2, 3, 4] } });
    expect(track.reentry_of).toBeNull();
    expect(trackSchema.parse({ ...track, reentry_of: "face:2" }).reentry_of).toBe("face:2");
  });

  it("a plan with or without the camera (left out while there is none) parses", () => {
    const frames = { "3": [{ item_id: "i_1", shape: "box", box: [1, 2, 30, 40], style: "solid" }] };
    expect(planSchema.parse({ frames }).camera).toBeUndefined();
    expect(planSchema.parse({ frames, camera: [[0, 0], [5, -2]] }).camera).toEqual([[0, 0], [5, -2]]);
  });

  it("a 202 ack without job_id parses (render-ack, audit-ack: status and stage, §8)", () => {
    expect(actionAckSchema.parse(without(renderAck.body, "job_id"))).toMatchObject({ status: "rendering", stage: "render" });
    expect(actionAckSchema.parse(without(auditAck.body, "job_id"))).toMatchObject({ status: "rendering", stage: "audit" });
  });

  it("a review ack without edit_id parses (§8 Edits)", () => {
    expect(reviewAckSchema.parse(without(reviewAck.body, "edit_id")).items.length).toBeGreaterThan(0);
  });

  it("a /result without job_id, status or frames parses (§8, §5.6)", () => {
    expect(resultResponseSchema.parse(without(resultClean, "job_id", "status", "frames")).audit).toBeDefined();
  });

  it("a demo answer without hero_id parses (request 19)", () => {
    expect(demoResponseSchema.parse(without(demoHero, "hero_id", "job_id")).mode).toBe("replay");
  });
});

