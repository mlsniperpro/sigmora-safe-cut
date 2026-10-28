import { describe, expect, it } from "vitest";
import { TIMELINE_ROWS, timelineRows } from "./VideoPane";

const items = Array.from({ length: 60 }, (_, i) => ({ id: `i_${i}` }));

describe("timeline rows (§3.3)", () => {
  it("shows at most the cap, and always the selected item", () => {
    expect(timelineRows(items, null)).toHaveLength(TIMELINE_ROWS);
    expect(timelineRows(items, "i_3").map((t) => t.id)).toEqual(items.slice(0, TIMELINE_ROWS).map((t) => t.id));
    const rows = timelineRows(items, "i_40");
    expect(rows).toHaveLength(TIMELINE_ROWS);
    expect(rows.at(-1)?.id).toBe("i_40");
    expect(timelineRows(items.slice(0, 5), "i_40")).toHaveLength(5);
  });
});
