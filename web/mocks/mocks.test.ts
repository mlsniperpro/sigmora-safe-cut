/**
 * The UI-SPEC §10.1 mock invariants, checked on every fixture, plus a drift
 * check against scripts/gen-mocks.mjs.
 */
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  codeCheckSchema,
  createJobResponseSchema,
  demoResponseSchema,
  errorBodySchema,
  jobResponseSchema,
  resultResponseSchema,
  resultsTableSchema,
  reviewAckSchema,
  actionAckSchema,
  type JobResponse,
} from "../src/lib/contracts";
import { primaryTrackId } from "../src/lib/labels";
import { checkTimeline } from "../src/lib/time";

const DIR = __dirname;
const files = readdirSync(DIR).filter((f) => f.endsWith(".json"));
const load = (f: string): unknown => JSON.parse(readFileSync(join(DIR, f), "utf8"));
const name = (f: string) => f.replace(/\.json$/, "");

type Envelope = { status: number; body: unknown };
const isEnvelope = (v: unknown): v is Envelope => typeof v === "object" && v !== null && "status" in v && "body" in v && typeof (v as Envelope).status === "number";

/** Fixtures standing in for `GET /v1/jobs/{id}` (not envelopes, results, demo or the reducer state). */
const jobFiles = files.filter((f) => {
  const v = load(f);
  return !isEnvelope(v) && typeof v === "object" && v !== null && "job_id" in v && "deletes_at" in v && !("receipt_html_url" in v);
});

describe("mock fixtures", () => {
  it("are up to date with scripts/gen-mocks.mjs", () => {
    execFileSync(process.execPath, [join(DIR, "..", "scripts", "gen-mocks.mjs"), "--check"], { stdio: "pipe" });
  });

  it.each(files.map((f) => [f]))("%s parses against its schema", (f) => {
    const v = load(f);
    const n = name(f);
    if (n === "reducer-state") return;
    if (isEnvelope(v)) {
      if (v.status >= 400) errorBodySchema.parse(v.body);
      else if (n.startsWith("code-check-ok")) codeCheckSchema.parse(v.body);
      else if (n === "create-job-ok") createJobResponseSchema.parse(v.body);
      else if (n.startsWith("review-ack")) reviewAckSchema.parse(v.body);
      else if (n.endsWith("-ack")) actionAckSchema.parse(v.body);
      else expect(v.status).toBe(204);
      return;
    }
    if (n.startsWith("demo-")) demoResponseSchema.parse(v);
    else if (n.startsWith("results-")) resultsTableSchema.parse(v);
    else if (typeof v === "object" && v !== null && "receipt_html_url" in v) resultResponseSchema.parse(v);
    else jobResponseSchema.parse(v);
  });

  describe.each(jobFiles.map((f) => [name(f)]))("%s", (n) => {
    const j: JobResponse = jobResponseSchema.parse(load(`${n}.json`));
    const tracks = new Map(j.tracks.map((t) => [t.track_id, t]));
    const frames = j.job?.frames ?? 0;
    const inRange = (f: number) => f >= 0 && f < frames;

    it("has a valid prepared timeline", () => {
      if (!j.job) return;
      expect(checkTimeline(j.job)).toBeNull();
    });

    it("references only existing tracks, frames and items", () => {
      const itemIds = new Set(j.items.map((i) => i.item_id));
      for (const item of j.items) {
        for (const t of item.track_ids) expect(tracks.has(t), `${item.item_id} → ${t}`).toBe(true);
        for (const f of item.evidence_frames) expect(inRange(f)).toBe(true);
        expect(typeof item.removed_by_creator).toBe("boolean");
      }
      for (const t of j.tracks) {
        expect(inRange(t.first) && inRange(t.last)).toBe(true);
        for (const f of Object.keys(t.boxes)) expect(inRange(Number(f))).toBe(true);
        if (t.reentry_of) expect(tracks.has(t.reentry_of)).toBe(true);
      }
      for (const [f, regions] of Object.entries(j.plan?.frames ?? {})) {
        expect(inRange(Number(f))).toBe(true);
        for (const r of regions) expect(itemIds.has(r.item_id), `plan ${f} → ${r.item_id}`).toBe(true);
      }
      for (const o of j.roles?.objects ?? []) expect(tracks.has(o.track_id)).toBe(true);
    });

    it("has a keyframe with a primary-track box for every evidence frame", () => {
      const keyframes = new Set(j.roles?.keyframes ?? []);
      for (const item of j.items) {
        if (item.origin === "static" || item.origin === "audit_patch") continue;
        const primary = primaryTrackId(item.track_ids);
        for (const f of item.evidence_frames) {
          expect(keyframes.has(`som/${String(f).padStart(6, "0")}.jpg`), `${item.item_id} keyframe ${f}`).toBe(true);
          expect(j.keyframe_urls[String(f)], `${item.item_id} url ${f}`).toBeDefined();
          expect(primary && tracks.get(primary)?.boxes[String(f)], `${item.item_id} box ${f}`).toBeTruthy();
        }
      }
    });

    it("covers every hidden or needs-you item on the plan", () => {
      for (const item of j.items) {
        if (item.decision === "keep") continue;
        const covered = Object.entries(j.plan?.frames ?? {}).filter(([, rs]) => rs.some((r) => r.item_id === item.item_id)).map(([f]) => Number(f));
        if (item.origin === "static") {
          const span = item.track_ids.map((t) => tracks.get(t)!);
          expect(covered.some((f) => span.some((t) => f >= t.first && f <= t.last)), item.item_id).toBe(true);
        } else {
          expect(item.evidence_frames.some((f) => covered.includes(f)), item.item_id).toBe(true);
        }
      }
    });

    it("keeps keyframe geometry consistent with the clip", () => {
      const g = j.keyframe_geometry;
      if (!g || !j.job || n === "job-review-keyframe-mismatch") return;
      expect(g.image_width).toBe(g.frame_width);
      expect(g.frame_width).toBe(j.job.width);
      expect(g.frame_height).toBe(j.job.height);
      expect(g.image_height).toBe(g.frame_height + g.bar_h);
    });

    it("carries stage statuses and transcript quality fields", () => {
      if (j.transcript) {
        expect(j.transcript.status).toBeDefined();
        const audio = j.job?.audio ?? true;
        if (audio && j.transcript.status === "ok") expect(j.transcript.source_kind).not.toBeNull();
      }
      if (j.scene) expect(j.scene.status).toBeDefined();
      if (j.roles) expect(j.roles.status).toBeDefined();
    });

    it("ties each hold to the stage that didn't run (UI-SPEC §10.1)", () => {
      // job-review-why-rows carries one item per hold with every stage ok, on purpose (the spec exempts it).
      if (n === "job-review-why-rows") return;
      for (const item of j.items) {
        const primary = primaryTrackId(item.track_ids);
        const track = j.roles?.tracks.find((t) => t.track_id === primary);
        if (item.hold === "no_roles") {
          const failedTrack = !!track && (track.failed_votes === 3 || (track.role === "unsure" && !track.escalated));
          expect(j.roles?.status !== "ok" || failedTrack, item.item_id).toBe(true);
        }
        if (item.hold === "no_scene") expect(j.scene?.status, item.item_id).not.toBe("ok");
        if (item.hold === "no_speech") expect(j.transcript?.status !== "ok" || j.transcript.degraded, item.item_id).toBe(true);
      }
    });

    it("marks audit-added items and has_render consistently", () => {
      for (const item of j.items) if (item.track_ids.length === 0) {
        expect(item.origin).toBe("audit_patch");
        expect(item.audit_label).toMatch(/^A\d+$/);
      }
      if (j.result?.video_url) expect(j.has_render).toBe(true);
    });

    it("never points at a resolvable media host", () => {
      const urls = [j.job?.prepared_url, ...Object.values(j.keyframe_urls), j.result?.video_url].filter(Boolean) as string[];
      for (const u of urls) expect(u.startsWith("https://example.invalid/") || u.startsWith("/sample/")).toBe(true);
    });
  });
});
