import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest";
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

  it("a paused redraw maps the frame on screen, not currentTime late in that frame (§3.6)", () => {
    const callbacks: VideoFrameRequestCallback[] = [];
    const proto = HTMLVideoElement.prototype as unknown as Record<string, unknown>;
    const had = "requestVideoFrameCallback" in proto;
    proto.requestVideoFrameCallback = function (cb: VideoFrameRequestCallback) {
      callbacks.push(cb);
      return callbacks.length;
    };
    proto.cancelVideoFrameCallback = () => undefined;
    onTestFinished(() => {
      if (!had) {
        delete proto.requestVideoFrameCallback;
        delete proto.cancelVideoFrameCallback;
      }
    });
    // Unmounts before the stub goes, as its cleanup cancels the frame callback.
    {
      const { container, unmount } = render(
        <VideoPane src="/sample/prepared.mp4" captionsUrl={null} fps={30} frames={240} width={1280} height={720} overlay={{} as never} timeline={[]} selected={null} />,
      );
      const video = container.querySelector("video")!;
      // A scrub lands 0.8 into frame 202: the video shows frame 202, whose timestamp is 202/30.
      Object.defineProperty(video, "currentTime", { configurable: true, value: 202.8 / 30 });
      fireEvent.seeking(video);
      callbacks.at(-1)!(0, { mediaTime: 202 / 30 } as VideoFrameCallbackMetadata);
      overlay.overlayOps.mockClear();
      fireEvent.seeked(video);
      const calls = overlay.overlayOps.mock.calls.length;
      const drawn = (overlay.overlayOps.mock.calls[0] as unknown as [{ frame: number }])[0].frame;
      unmount();
      expect(calls).toBe(1);
      expect(drawn).toBe(202);
    }
  });
});

