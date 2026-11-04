import { describe, expect, it } from "vitest";
import type { Plan } from "./contracts";
import { MAX_REGIONS, drawOverlay, headBox, overlayOps, type OverlayInput } from "./overlay";

const plan: Plan = {
  frames: {
    "9": [
      { item_id: "i_4", shape: "box", box: [692, 140, 758, 225], mask: null, style: "pixelate", grid: [692, 140, 11] },
      { item_id: "i_9", shape: "box", box: [10, 10, 20, 20], mask: null, style: "solid", grid: null },
    ],
  },
  crowd_fills: [{ frames: [9], box: [0, 0, 1280, 100] }],
};
const tracks = new Map([
  ["face:2", { boxes: { "9": [410, 122, 480, 212] as [number, number, number, number] } }],
  ["person:1", { boxes: { "9": [370, 102, 570, 700] as [number, number, number, number] } }],
]);
const base: OverlayInput = {
  frame: 9, plan, isCovered: (id) => id === "i_4", unplanned: [], items: [{ itemId: "i_1", label: "Face 2", trackIds: ["face:2", "person:1"] }],
  tracks, spots: [], mode: "safecut", selected: null, width: 1280, height: 720,
};

describe("overlayOps (UI-SPEC §3.6)", () => {
  it("covers only regions whose item is hidden after local edits, plus crowd fills", () => {
    const ops = overlayOps(base);
    expect(ops).toEqual([
      { kind: "cover", box: [692, 140, 758, 225], style: "pixelate", grid: [692, 140, 11] },
      { kind: "fill", box: [0, 0, 1280, 100] },
    ]);
  });

  it("draws a cover, mosaic or solid, in its mask's shape; a bad mask or a wrong-size one covers the box (§3.6)", () => {
    // 4×4 frame, mask = column 1, rows 1–2. Column-major counts: 5 off, 2 on, 9 off.
    const mask = { size: [4, 4] as [number, number], counts: "529" };
    const region = (over: object) => ({ item_id: "i_4", shape: "mask" as const, box: [1, 1, 2, 3] as [number, number, number, number], mask, style: "person_solid" as const, grid: null, ...over });
    const at = (r: ReturnType<typeof region>) => overlayOps({ ...base, width: 4, height: 4, plan: { frames: { "9": [r] }, crowd_fills: [] } })[0];
    expect(at(region({}))).toMatchObject({ kind: "cover", mask: [[1, 1, 2]] });
    expect(at(region({ style: "pixelate", grid: [1, 1, 1] }))).toMatchObject({ kind: "cover", style: "pixelate", mask: [[1, 1, 2]] });
    expect(at(region({ mask: { size: [4, 4], counts: "5" } }))).not.toHaveProperty("mask");
    expect(at(region({ mask: { size: [8, 8], counts: "52?" } }))).not.toHaveProperty("mask");
    expect(at(region({ shape: "box" }))).not.toHaveProperty("mask");
  });

  it("draws a masked cover frosted inside its mask runs, never as a dark block", () => {
    const calls: string[] = [];
    const ctx = {
      canvas: { width: 8, height: 8 }, clearRect: () => undefined, save: () => undefined, restore: () => undefined, beginPath: () => undefined, clip: () => calls.push("clip"),
      rect: (...r: number[]) => calls.push(`rect ${r.join(",")}`), fillRect: () => calls.push("fill"), fillStyle: "", filter: "",
    } as unknown as CanvasRenderingContext2D;
    drawOverlay(ctx, null, [{ kind: "cover", box: [0, 0, 4, 4], style: "solid", grid: null, mask: [[1, 1, 2], [2, 0, 1]] }], 2);
    // Clipped to the mask's runs (one rect per run, a pixel wide, slightly overdrawn), then frosted cells.
    expect(calls.slice(0, 3)).toEqual(["rect 2,2,2.5,4.5", "rect 4,0,2.5,2.5", "clip"]);
    expect(calls.filter((c) => c === "fill").length).toBeGreaterThan(0);
    expect(ctx.filter).toMatch(/^blur\(/);
    const [r, g, b] = (ctx.fillStyle as string).match(/\d+/g)!.map(Number);
    expect((r! + g! + b!) / 3).toBeGreaterThan(150); // the haze: light, never the old dark slate
  });

  it("frosts in the plain haze when the video can't be read (a cross-origin, tainted canvas)", () => {
    const tainted = { width: 0, height: 0, getContext: () => ({ drawImage: () => undefined, getImageData: () => { throw new DOMException("tainted", "SecurityError"); } }) };
    const original = document.createElement.bind(document);
    document.createElement = ((tag: string) => (tag === "canvas" ? tainted : original(tag))) as typeof document.createElement;
    const noop = () => undefined;
    const ctx = { canvas: { width: 8, height: 8 }, clearRect: noop, save: noop, restore: noop, beginPath: noop, clip: noop, rect: noop, fillRect: noop, fillStyle: "", filter: "" } as unknown as CanvasRenderingContext2D;
    try {
      expect(() => drawOverlay(ctx, {} as CanvasImageSource, [{ kind: "cover", box: [0, 0, 4, 4], style: "solid", grid: null }], 2)).not.toThrow();
    } finally {
      document.createElement = original;
    }
  });

  it("draws nothing on a frame the plan leaves out", () => {
    expect(overlayOps({ ...base, frame: 3, plan: { ...plan, crowd_fills: [] } })).toEqual([]);
  });

  it("covers a locally hidden person's face with the mosaic until the plan arrives, never their body (§2.7)", () => {
    const ops = overlayOps({ ...base, plan: { frames: {}, crowd_fills: [] }, unplanned: [{ itemId: "i_1", trackIds: ["face:2", "person:1"] }] });
    // The face padded like the guard's (15 % + 8 px), on the grid the guard locks: 70 px wide → 18 px cells (4 across).
    expect(ops).toEqual([{ kind: "cover", box: [391, 100, 499, 234], style: "pixelate", grid: [391, 100, 18] }]);
  });

  it("covers a head estimate, not the body, where a hidden person's face isn't seen (§2.7)", () => {
    const ops = overlayOps({ ...base, plan: { frames: {}, crowd_fills: [] }, unplanned: [{ itemId: "i_1", trackIds: ["person:1"] }] });
    expect(headBox([370, 102, 570, 700])).toEqual([370, 102, 570, 234]);
    // No face track to size a grid: solid, over the head only (padded like a face).
    expect(ops).toEqual([{ kind: "cover", box: [332, 74, 608, 262], style: "solid", grid: null }]);
    const covered = ops.reduce((n, op) => n + (op.kind === "cover" ? (op.box[2] - op.box[0]) * (op.box[3] - op.box[1]) : 0), 0);
    expect(covered).toBeLessThan(0.5 * 200 * 598);
  });

  it("covers the whole person only for Remove person", () => {
    const ops = overlayOps({ ...base, plan: { frames: {}, crowd_fills: [] }, unplanned: [{ itemId: "i_1", trackIds: ["face:2", "person:1"], whole: true }] });
    expect(ops.map((op) => op.kind === "cover" && op.style)).toEqual(["person_solid", "person_solid"]);
  });

  it("passes a region's kept faces through and cuts them out of what it draws (§2.6)", () => {
    const r = { item_id: "i_4", shape: "box" as const, box: [0, 0, 8, 8] as [number, number, number, number], mask: null, style: "solid" as const, grid: null, keep_clear: [[2, 2, 4, 4]] as [number, number, number, number][] };
    const ops = overlayOps({ ...base, width: 8, height: 8, plan: { frames: { "9": [r] }, crowd_fills: [] } });
    expect(ops).toEqual([{ kind: "cover", box: [0, 0, 8, 8], style: "solid", grid: null, clear: [[2, 2, 4, 4]] }]);
    const calls: string[] = [];
    const noop = () => undefined;
    const lctx = { save: noop, restore: noop, beginPath: noop, rect: noop, clip: noop, fillRect: () => calls.push("fill"), clearRect: (...a: number[]) => calls.push(`clear ${a.join(",")}`), fillStyle: "", filter: "" };
    const layer = { width: 0, height: 0, getContext: () => lctx };
    const original = document.createElement.bind(document);
    document.createElement = ((tag: string) => (tag === "canvas" ? layer : original(tag))) as typeof document.createElement;
    try {
      const ctx = { canvas: { width: 16, height: 16 }, clearRect: () => undefined, drawImage: () => calls.push("lay"), fillRect: () => calls.push("direct"), fillStyle: "" } as unknown as CanvasRenderingContext2D;
      drawOverlay(ctx, null, ops, 2);
    } finally {
      document.createElement = original;
    }
    expect(calls.filter((c) => c !== "fill")).toEqual(["clear 4,4,4,4", "lay"]);
    expect(calls).not.toContain("direct");
  });

  it("in Raw mode outlines items instead of covering, and rings the selection", () => {
    const ops = overlayOps({ ...base, mode: "raw" });
    expect(ops).toEqual([{ kind: "outline", box: [410, 122, 480, 212], label: "Face 2", selected: false }]);
    const sel = overlayOps({ ...base, selected: "i_1" });
    expect(sel.at(-1)).toEqual({ kind: "outline", box: [410, 122, 480, 212], label: "Face 2", selected: true });
  });

  it("rings unfixed spots on their frames only", () => {
    const spots = [{ label: "U1", first: 9, last: 9, boxes: { "9": [600, 200, 660, 250] as [number, number, number, number] } }];
    expect(overlayOps({ ...base, spots }).at(-1)).toEqual({ kind: "spot", box: [600, 200, 660, 250], label: "U1" });
    expect(overlayOps({ ...base, frame: 8, spots })).toEqual([]);
  });

  it("never draws more than the cap", () => {
    const many = Array.from({ length: 500 }, (_, i) => ({ item_id: `i_${i}`, shape: "box" as const, box: [0, 0, 1, 1] as [number, number, number, number], mask: null, style: "solid" as const, grid: null }));
    expect(overlayOps({ ...base, plan: { frames: { "9": many }, crowd_fills: [] }, isCovered: () => true })).toHaveLength(MAX_REGIONS);
  });
});
