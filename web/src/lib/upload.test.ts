import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { MAX_BYTES, ceilTenth, checkFiles, durationProblem, normaliseCode, sizeMb, tooLongMessage } from "./upload";

const f = (name: string, type: string, size = 1000) => ({ name, type, size });

describe("upload checks (UI-SPEC §10.2)", () => {
  it("needs exactly one file", () => {
    expect(checkFiles([])).toMatchObject({ ok: false, problem: { message: "Drop one clip at a time." } });
    expect(checkFiles([f("a.mp4", "video/mp4"), f("b.mp4", "video/mp4")])).toMatchObject({ ok: false, problem: { kind: "count" } });
  });

  it("needs both the extension and the MIME type, deriving the type when the browser gave none", () => {
    expect(checkFiles([f("a.mp4", "video/mp4")])).toEqual({ ok: true, contentType: "video/mp4" });
    expect(checkFiles([f("A.MOV", "video/quicktime")])).toEqual({ ok: true, contentType: "video/quicktime" });
    expect(checkFiles([f("a.mov", "")])).toEqual({ ok: true, contentType: "video/quicktime" });
    expect(checkFiles([f("a.avi", "video/x-msvideo")])).toMatchObject({ ok: false, problem: { message: "Safe Cut takes MP4 or MOV video files." } });
    expect(checkFiles([f("a.mp4", "image/png")])).toMatchObject({ ok: false, problem: { kind: "type" } });
    expect(checkFiles([f("a", "")])).toMatchObject({ ok: false, problem: { kind: "type" } });
  });

  it("caps the size at 150 MiB and rounds the shown size up", () => {
    expect(checkFiles([f("a.mp4", "video/mp4", MAX_BYTES)]).ok).toBe(true);
    expect(checkFiles([f("a.mp4", "video/mp4", MAX_BYTES + 1)])).toMatchObject({ ok: false, problem: { message: "This file is 150.1 MB. The limit is 150 MB." } });
    expect(sizeMb(157_286_401)).toBe("150.1");
  });

  it("checks duration with the 0.05 s tolerance and defers unknown durations to the server", () => {
    expect(durationProblem(60.05)).toBeNull();
    expect(durationProblem(60.06)).toBe("This clip is 60.1 seconds long. The limit is 60 seconds. Trim it and try again.");
    expect(durationProblem(Number.NaN)).toBeNull();
    expect(durationProblem(Number.POSITIVE_INFINITY)).toBeNull();
    expect(durationProblem(null)).toBeNull();
    expect(tooLongMessage(undefined)).toBe("This clip is longer than 60 seconds. Trim it and try again.");
  });

  it("never shows a rounded number at or under the limit for an over-limit value", () => {
    fc.assert(fc.property(fc.double({ min: 60.0500001, max: 10_000, noNaN: true }), (d) => Number(ceilTenth(d)) > 60), { numRuns: 3000 });
    fc.assert(fc.property(fc.integer({ min: MAX_BYTES + 1, max: 10 * MAX_BYTES }), (b) => Number(sizeMb(b)) > 150), { numRuns: 3000 });
    fc.assert(fc.property(fc.double({ min: 0, max: 1000, noNaN: true }), (d) => Number(ceilTenth(d)) >= d - 1e-9), { numRuns: 3000 });
  });

  it("trims and caps the access code", () => {
    expect(normaliseCode("  abc  ")).toBe("abc");
    expect(normaliseCode("x".repeat(100))).toHaveLength(64);
  });
});
