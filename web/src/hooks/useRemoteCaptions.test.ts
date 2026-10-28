import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRemoteCaptions } from "./useRemoteCaptions";

const vtt = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.500\nHello\n";

afterEach(() => vi.restoreAllMocks());

describe("useRemoteCaptions", () => {
  it("uses a same-origin path as it is, without fetching", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    expect(renderHook(() => useRemoteCaptions("/sample/captions.vtt")).result.current).toBe("/sample/captions.vtt");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fetches another origin's WebVTT and hands it over as a blob URL", async () => {
    URL.createObjectURL = vi.fn(() => "blob:captions");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(vtt, { status: 200 }));
    const { result } = renderHook(() => useRemoteCaptions("https://storage.example/c.vtt?sig=1"));
    expect(result.current).toBeNull();
    await waitFor(() => expect(result.current).toBe("blob:captions"));
    expect(fetchSpy).toHaveBeenCalledWith("https://storage.example/c.vtt?sig=1", expect.objectContaining({ credentials: "omit" }));
  });

  it.each([
    ["a 403", () => Promise.resolve(new Response("denied", { status: 403 }))],
    ["a body that isn't WebVTT", () => Promise.resolve(new Response("<html>", { status: 200 }))],
    ["a CORS or network failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("leaves the video without captions on %s", async (_, answer) => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(answer);
    const { result } = renderHook(() => useRemoteCaptions("https://storage.example/other.vtt"));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current).toBeNull();
  });

  it("keeps the captions on show while a re-signed URL for them loads", async () => {
        vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(new Response(vtt, { status: 200 })));
    const { result, rerender } = renderHook(({ u }) => useRemoteCaptions(u), { initialProps: { u: "https://storage.example/c.vtt?sig=1" } });
    await waitFor(() => expect(result.current).toMatch(/^blob:/));
    const first = result.current;
    rerender({ u: "https://storage.example/c.vtt?sig=2" });
    expect(result.current).toBe(first);
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current).toBe(first);
  });
});

