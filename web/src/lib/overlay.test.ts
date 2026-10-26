import { describe, expect, it } from "vitest";
import type { Plan } from "./contracts";
import { MAX_REGIONS, overlayOps, type OverlayInput } from "./overlay";

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
      { kind: "fill", box: [0, 0, 1280, 100] },
      { kind: "cover", box: [692, 140, 758, 225], style: "pixelate", grid: [692, 140, 11] },
    ]);
  });

  it("draws nothing on a frame the plan leaves out", () => {
    expect(overlayOps({ ...base, frame: 3, plan: { ...plan, crowd_fills: [] } })).toEqual([]);
  });

  it("covers a locally hidden item with its padded track boxes until the plan arrives", () => {
    const ops = overlayOps({ ...base, plan: { frames: {}, crowd_fills: [] }, unplanned: [{ itemId: "i_1", trackIds: ["face:2"] }] });
    expect(ops).toHaveLength(1);
    const op = ops[0]!;
    expect(op.kind).toBe("cover");
    if (op.kind === "cover") expect(op.box).toEqual([399.5, 108.5, 490.5, 225.5]);
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
