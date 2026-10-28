import { describe, expect, it } from "vitest";
import { trackSchema } from "./contracts";

describe("contracts", () => {
  it("a track without reentry_of (WP0's default None, key left out) parses as null", () => {
    const track = trackSchema.parse({ track_id: "face:1", concept: "face", first: 0, last: 3, boxes: { "0": [1, 2, 3, 4] } });
    expect(track.reentry_of).toBeNull();
    expect(trackSchema.parse({ ...track, reentry_of: "face:2" }).reentry_of).toBe("face:2");
  });
});
