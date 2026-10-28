import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom lacks these browser APIs; components use them, tests don't need real behaviour.
if (typeof window !== "undefined") {
  window.matchMedia ??= ((query: string) => ({
    matches: query.includes("min-width: 1024px"),
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;

  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;

  const proto = HTMLDialogElement.prototype;
  proto.showModal ??= function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.close ??= function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    // Browsers fire `close` from a queued task, not synchronously inside close().
    setTimeout(() => this.dispatchEvent(new Event("close")), 0);
  };

  Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: vi.fn(() => Promise.resolve()) });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: vi.fn() });
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  window.requestAnimationFrame ??= ((cb: FrameRequestCallback) => setTimeout(() => cb(performance.now()), 16) as unknown as number);
  globalThis.CSS ??= { escape: (s: string) => s.replace(/["\\]/g, "\\$&") } as typeof CSS;
}
