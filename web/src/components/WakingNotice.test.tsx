import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SafeCutClient, type RawResponse, type Transport } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { COPY } from "@/lib/copy";
import { WAKING_AFTER_MS } from "@/lib/wake";
import { WakingNotice } from "./WakingNotice";

afterEach(() => {
  setClientForTests(null);
  vi.useRealTimers();
});

describe("WakingNotice", () => {
  it("is an empty polite status region until a request has waited, then says so, then goes when the API answers", async () => {
    vi.useFakeTimers();
    let answer: (r: RawResponse) => void = () => undefined;
    const transport: Transport = { request: () => new Promise((resolve) => (answer = resolve)), upload: () => Promise.resolve() };
    const client = new SafeCutClient({ transport });
    setClientForTests(client);
    render(<WakingNotice />);
    const region = screen.getByRole("status");
    expect(region).toBeEmptyDOMElement();

    const pending = client.checkCode("code").catch(() => undefined);
    await act(() => vi.advanceTimersByTimeAsync(WAKING_AFTER_MS - 1));
    expect(region).toBeEmptyDOMElement();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(screen.getByRole("status")).toHaveTextContent(COPY.waking);
    expect(COPY.waking).toBe("Waking Safe Cut up. The first request after a quiet spell takes up to a minute.");

    await act(async () => {
      answer({ status: 401, headers: { get: () => null }, body: { error: { code: "bad_code" } } });
      await pending;
    });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("shows nothing for a slow request while the service is known to be awake", async () => {
    vi.useFakeTimers();
    const answers: Array<(r: RawResponse) => void> = [];
    const transport: Transport = { request: () => new Promise((resolve) => answers.push(resolve)), upload: () => Promise.resolve() };
    const client = new SafeCutClient({ transport });
    setClientForTests(client);
    render(<WakingNotice />);
    const first = client.getJob("j").catch(() => undefined);
    answers[0]?.({ status: 404, headers: { get: () => null }, body: null });
    await first;
    void client.getJob("j").catch(() => undefined);
    await act(() => vi.advanceTimersByTimeAsync(WAKING_AFTER_MS * 2));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
});
