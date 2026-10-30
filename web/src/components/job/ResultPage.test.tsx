import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SafeCutClient, type RawResponse, type Transport } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { MockBackend } from "@/lib/mock-backend";
import { ModeProvider } from "../mode";
import { URL_REFRESH_MS } from "@/lib/polling";
import { ResultPage } from "./ResultPage";

const nav = vi.hoisted(() => ({ id: "result-clean", search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: nav.id }),
  usePathname: () => `/jobs/${nav.id}`,
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
}));

function setup(id: string, search = "") {
  nav.id = id;
  nav.search = search;
  nav.replace.mockReset();
  setClientForTests(new SafeCutClient({ transport: new MockBackend({ latencyMs: 0 }), sleep: () => Promise.resolve() }));
  render(
    <ModeProvider>
      <ResultPage />
    </ModeProvider>,
  );
  return userEvent.setup();
}
afterEach(() => setClientForTests(null));

describe("result and receipt (UI-SPEC §5)", () => {
  it("clean: checked, download, embedded sandboxed receipt, no Publish outside Sigmora", async () => {
    setup("result-clean");
    expect(await screen.findByText("No leaks found.")).toBeInTheDocument();
    expect(screen.getByText("12 of 12 frames checked.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download video" })).toHaveAttribute("download");
    expect(screen.getByTitle("Privacy receipt")).toHaveAttribute("sandbox", "");
    expect(screen.queryByRole("button", { name: "Publish to Sigmora" })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to review" })).toHaveAttribute("href", "/jobs/result-clean?view=review");
  });

  it("keeps demo and from on the links back to review (§10.4)", async () => {
    setup("result-unresolved", "from=sigmora&demo=1");
    expect(await screen.findByRole("link", { name: "Review them" })).toHaveAttribute("href", "/jobs/result-unresolved?view=review&from=sigmora&demo=1");
    expect(screen.getByRole("link", { name: "Back to review" })).toHaveAttribute("href", "/jobs/result-unresolved?view=review&from=sigmora&demo=1");
  });

  it("a result without captions_url, status or frames still loads, with captions from the job's transcript", async () => {
    nav.id = "result-clean";
    nav.search = "";
    const backend = new MockBackend({ latencyMs: 0 });
    const transport: Transport = {
      upload: (...args) => backend.upload(...args),
      request: (init: Parameters<MockBackend["request"]>[0]) =>
        backend.request(init).then((raw) => {
          if (!init.path.endsWith("/result") || raw.status !== 200) return raw;
          const body: Record<string, unknown> = { ...(raw.body as Record<string, unknown>) };
          for (const key of ["captions_url", "status", "frames"]) delete body[key];
          return { ...raw, body };
        }),
    };
    setClientForTests(new SafeCutClient({ transport, sleep: () => Promise.resolve() }));
    const { container } = render(
      <ModeProvider>
        <ResultPage />
      </ModeProvider>,
    );
    expect(await screen.findByText("No leaks found.")).toBeInTheDocument();
    expect(screen.getByText("12 of 12 frames checked.")).toBeInTheDocument();
    // Built from the transcript, so a blob URL rather than the API's captions file.
    expect(container.querySelector("track")?.getAttribute("src")).toMatch(/^blob:/);
  });

  it("fixed: counts distinct patched items", async () => {
    setup("result-fixed");
    expect(await screen.findByText("1 leak found and fixed. Nothing left to fix.")).toBeInTheDocument();
  });

  it("unresolved: publish off from Sigmora, with a link to review the spots", async () => {
    setup("result-unresolved", "from=sigmora");
    expect(await screen.findByText("1 spot couldn't be fixed automatically. Publishing is off until each is fixed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Sigmora" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Review them" })).toHaveAttribute("href", "/jobs/result-unresolved?view=review&from=sigmora");
    expect(screen.getByText("This version has 1 unfixed spot.")).toBeInTheDocument();
  });

  it("uses the YuNet wording when EgoBlur wasn't available", async () => {
    const user = setup("result-clean-yunet");
    await user.click(await screen.findByRole("button", { name: "What the check does →" }));
    expect(screen.getByText(/^A face detector \(YuNet\) looked for faces/)).toBeInTheDocument();
  });

  it("publishes to Sigmora when opened from it and clean", async () => {
    const opener = { postMessage: vi.fn() };
    Object.defineProperty(window, "opener", { configurable: true, value: opener });
    const user = setup("result-clean", "from=sigmora");
    await user.click(await screen.findByRole("button", { name: "Publish to Sigmora" }));
    expect(opener.postMessage).toHaveBeenCalledWith(expect.objectContaining({ type: "safecut:publish", job_id: "j_hero1" }), "https://sigmora.org");
    expect(screen.getByText("Sent to Sigmora. You can close this tab.")).toBeInTheDocument();
    Object.defineProperty(window, "opener", { configurable: true, value: null });
  });

  it("redirects a job still in review back to the panel", async () => {
    setup("job-review-hero1", "from=sigmora&view=review");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/jobs/job-review-hero1?from=sigmora"));
  });
});

describe("a video that won't play", () => {
  it("says so when the refetch gives back the same URL, instead of leaving a dead player", async () => {
    setup("result-clean");
    expect(await screen.findByText("No leaks found.")).toBeInTheDocument();
    fireEvent.error(screen.getByLabelText("Your clip after Safe Cut"));
    expect(await screen.findByText("Something went wrong on our side. Nothing has been published.")).toBeInTheDocument();
  });
});

describe("signed URLs expire (UI-SPEC §10.7)", () => {
  /** Each result fetch signs its URLs afresh (`v=<n>`), as the live API does. */
  let backend: MockBackend;
  let fetches = 0;
  const inflight = new Set<Promise<RawResponse>>();
  const sign = (url: string) => `${url}${url.includes("?") ? "&" : "?"}v=${fetches}`;

  function setupSigned(id: string) {
    nav.id = id;
    nav.search = "";
    nav.replace.mockReset();
    fetches = 0;
    backend = new MockBackend({ latencyMs: 0 });
    const transport: Transport = {
      upload: (...args) => backend.upload(...args),
      request: (init: Parameters<MockBackend["request"]>[0]) => {
        const p = backend.request(init).then((raw) => {
          if (init.method !== "GET" || !init.path.endsWith("/result") || raw.status !== 200) return raw;
          fetches += 1;
          const body = raw.body as { video_url: string; receipt_html_url: string; receipt_json_url: string };
          return { ...raw, body: { ...body, video_url: sign(body.video_url), receipt_html_url: sign(body.receipt_html_url), receipt_json_url: sign(body.receipt_json_url) } };
        });
        inflight.add(p);
        void p.finally(() => inflight.delete(p)).catch(() => undefined);
        return p;
      },
    };
    setClientForTests(new SafeCutClient({ transport, sleep: () => Promise.resolve() }));
    render(
      <ModeProvider>
        <ResultPage />
      </ModeProvider>,
    );
  }
  // A response can start the next request (job, then result) once act flushes its effects:
  // repeat until nothing new starts.
  const settle = async () => {
    do {
      await act(async () => {
        while (inflight.size > 0) await Promise.allSettled([...inflight]);
        for (let i = 0; i < 10; i++) await new Promise((resolve) => setImmediate(resolve));
      });
    } while (inflight.size > 0);
  };
  const advance = async (ms: number) => {
    await act(() => vi.advanceTimersByTimeAsync(ms));
    await settle();
  };
  const video = () => screen.getByLabelText("Your clip after Safe Cut");
  const receipt = () => screen.getByTitle("Privacy receipt");

  afterEach(() => vi.useRealTimers());

  it("refreshes the download and receipt links before they expire, without reloading the video", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    setupSigned("result-clean");
    await settle();
    expect(screen.getByText("No leaks found.")).toBeInTheDocument();
    fireEvent.load(receipt());
    expect(screen.getByRole("link", { name: "Download video" }).getAttribute("href")).toMatch(/v=1$/);
    await advance(URL_REFRESH_MS);
    expect(fetches).toBe(2);
    expect(screen.getByRole("link", { name: "Download video" }).getAttribute("href")).toMatch(/v=2$/);
    expect(screen.getByRole("link", { name: "Download receipt (JSON)" }).getAttribute("href")).toMatch(/v=2$/);
    expect(screen.getByRole("link", { name: "Open the receipt in a new tab" }).getAttribute("href")).toMatch(/v=2$/);
    // What's already playing or showing keeps its URL.
    expect(video().getAttribute("src")).toMatch(/v=1$/);
    expect(receipt().getAttribute("src")).toMatch(/v=1$/);
  });

  it("a failed link refresh keeps the page, and the next refresh still comes", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    setupSigned("result-clean");
    await settle();
    expect(screen.getByText("No leaks found.")).toBeInTheDocument();
    fireEvent.load(receipt());
    backend.inject(/\/result$/, "error-500");
    await advance(URL_REFRESH_MS);
    expect(screen.getByText("No leaks found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download video" }).getAttribute("href")).toMatch(/v=1$/);
    await advance(URL_REFRESH_MS);
    expect(screen.getByRole("link", { name: "Download video" }).getAttribute("href")).toMatch(/v=2$/);
  });

  it("a video error refetches once for a fresh URL, then shows the error page", async () => {
    setupSigned("result-clean");
    expect(await screen.findByText("No leaks found.")).toBeInTheDocument();
    fireEvent.error(video());
    await waitFor(() => expect(video().getAttribute("src")).toMatch(/v=2$/));
    fireEvent.error(video());
    expect(await screen.findByText("Something went wrong on our side. Nothing has been published.")).toBeInTheDocument();
  });

  it("a refreshed video that played re-arms its refresh, so a later expiry refreshes again", async () => {
    setupSigned("result-clean");
    expect(await screen.findByText("No leaks found.")).toBeInTheDocument();
    fireEvent.error(video());
    await waitFor(() => expect(video().getAttribute("src")).toMatch(/v=2$/));
    fireEvent.loadedMetadata(video());
    fireEvent.error(video());
    await waitFor(() => expect(video().getAttribute("src")).toMatch(/v=3$/));
    expect(screen.getByText("No leaks found.")).toBeInTheDocument();
  });

  it("Try again after a failed result load fetches the result again", async () => {
    setupSigned("result-clean");
    backend.inject(/\/result$/, "error-500");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No leaks found.")).toBeInTheDocument();
  });

  it("Try again after the video failed twice starts over with a fresh URL and a fresh retry", async () => {
    setupSigned("result-clean");
    expect(await screen.findByText("No leaks found.")).toBeInTheDocument();
    fireEvent.error(video());
    await waitFor(() => expect(video().getAttribute("src")).toMatch(/v=2$/));
    fireEvent.error(video());
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(video().getAttribute("src")).toMatch(/v=3$/));
    // Its one retry is back: another error refetches instead of failing at once.
    fireEvent.error(video());
    await waitFor(() => expect(video().getAttribute("src")).toMatch(/v=4$/));
  });

  it("a receipt that doesn't load refetches once, then offers the JSON", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    setupSigned("result-clean");
    await settle();
    expect(screen.getByText("No leaks found.")).toBeInTheDocument();
    await advance(15_000);
    expect(fetches).toBe(2);
    expect(receipt().getAttribute("src")).toMatch(/v=2$/);
    expect(video().getAttribute("src")).toMatch(/v=1$/);
    await advance(15_000);
    expect(screen.getByText("The receipt didn't load. You can still download it as JSON.")).toBeInTheDocument();
    expect(fetches).toBe(2);
  });
});
