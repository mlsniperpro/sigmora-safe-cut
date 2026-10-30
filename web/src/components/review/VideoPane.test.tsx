import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VideoPane } from "./VideoPane";

const overlay = vi.hoisted(() => ({ drawOverlay: vi.fn(), overlayOps: vi.fn(() => []) }));
vi.mock("@/lib/overlay", () => overlay);

describe("VideoPane", () => {
  const getContext = HTMLCanvasElement.prototype.getContext;
  beforeEach(() => {
    // jsdom has no 2D canvas; the drawing itself is mocked above.
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({})) as unknown as typeof getContext;
    overlay.drawOverlay.mockClear();
  });
  afterEach(() => {
    HTMLCanvasElement.prototype.getContext = getContext;
  });

  it("redraws the overlay once a paused seek's frame is decoded (§3.6)", () => {
    const { container } = render(
      <VideoPane src="/sample/prepared.mp4" captionsUrl={null} fps={30} frames={240} width={1280} height={720} overlay={{} as never} timeline={[]} selected={null} />,
    );
    const video = container.querySelector("video")!;
    // The decoded frame is there now: a redraw can draw pixelate covers from it, not a solid stand-in.
    Object.defineProperty(video, "readyState", { configurable: true, value: 4 });
    overlay.drawOverlay.mockClear();
    fireEvent.seeked(video);
    expect(overlay.drawOverlay).toHaveBeenCalledTimes(1);
    expect(overlay.drawOverlay.mock.calls[0]![1]).toBe(video);
    overlay.drawOverlay.mockClear();
    fireEvent.loadedData(video);
    expect(overlay.drawOverlay).toHaveBeenCalledTimes(1);
  });
});
