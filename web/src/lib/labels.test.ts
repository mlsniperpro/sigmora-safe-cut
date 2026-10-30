import { describe, expect, it } from "vitest";
import { asSentence, trackLabel } from "./labels";
import { modelList } from "./why/model";

describe("labels from API strings", () => {
  it("a concept named like an Object.prototype member reads as a word, not a function", () => {
    expect(trackLabel("face:2")).toBe("Face 2");
    expect(trackLabel("constructor:1")).toBe("Constructor 1");
    expect(trackLabel("toString:3")).toBe("ToString 3");
  });

  it("a model ID named like an Object.prototype member is shown as given", () => {
    expect(modelList({ models: { a: "sam-3.1", b: "constructor" }, tracks: [] })).toBe("SAM 3.1 · constructor");
  });

  it("asSentence adds a full stop only when the text has none", () => {
    expect(asSentence("covered it")).toBe("covered it.");
    expect(asSentence("covered it.")).toBe("covered it.");
  });
});
