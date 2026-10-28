import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import kappaUndefined from "../../../mocks/results-kappa-undefined.json";
import noEgoblur from "../../../mocks/results-no-egoblur.json";
import twoLabellers from "../../../mocks/results-two-labellers.json";
import { SafeCutClient } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { resultsTableSchema } from "@/lib/contracts";
import { MockBackend } from "@/lib/mock-backend";
import { ModeProvider } from "../mode";
import { HeroAndSteps } from "./HeroAndSteps";
import { ResultsTable } from "./ResultsTable";

afterEach(() => setClientForTests(null));

describe("results table (UI-SPEC §1.3)", () => {
  it("shows the placeholder, never a number, before WP8 fills it", () => {
    render(<ResultsTable results={null} />);
    expect(screen.getByText("Numbers appear here after our frozen test runs. We publish them whether they're good or not.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("marks a missing EgoBlur baseline and uses the one-labeller footnote", () => {
    render(<ResultsTable results={resultsTableSchema.parse(noEgoblur)} />);
    const table = screen.getByRole("table");
    expect(within(table).getByText("EgoBlur Gen 2: not run (EgoBlur weights unavailable)")).toBeInTheDocument();
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Method", "Recall", "Exposure", "Leak bursts", "Over-blur"]);
    expect(screen.getByText(/labelled by one person\. Agreement between two labellers wasn't measured\. 1 run per clip\. Run fixture-run\./)).toBeInTheDocument();
    expect(screen.queryByText(/κ/)).toBeNull();
  });

  it("always shows κ with the agreement and the 2×2 counts", () => {
    render(<ResultsTable results={resultsTableSchema.parse(twoLabellers)} />);
    expect(screen.getByText(/They agreed on 90\.0% of 10 decisions \(both said hide: 4 · only the first said hide: 1 · only the second said hide: 0 · both said keep: 5\); κ = 0\.80\./)).toBeInTheDocument();
  });

  it("adds the open-weight clause to the footnote only once the second opinion runs on the hero", () => {
    const note = /Muse Spark Open's second opinion ran only on consented hero and dev footage; the test-split numbers were measured without it\./;
    const { rerender } = render(<ResultsTable results={resultsTableSchema.parse(twoLabellers)} />);
    expect(screen.queryByText(note)).toBeNull();
    rerender(<ResultsTable results={resultsTableSchema.parse(twoLabellers)} heroOpenWeight />);
    expect(screen.getByText(note)).toBeInTheDocument();
  });

  it("rounds κ down, never up", () => {
    render(<ResultsTable results={resultsTableSchema.parse({ ...twoLabellers, kappa: 0.816 })} />);
    expect(screen.getByText(/κ = 0\.81\./)).toBeInTheDocument();
  });

  it("says when κ can't be computed instead of printing null", () => {
    render(<ResultsTable results={resultsTableSchema.parse(kappaUndefined)} />);
    expect(screen.getByText(/κ can't be computed: both labellers made the same call on every item\./)).toBeInTheDocument();
    expect(screen.queryByText(/null|NaN/)).toBeNull();
  });

  it("rounds in the unflattering direction", () => {
    const r = resultsTableSchema.parse({ ...twoLabellers, rows: [{ method: "Safe Cut", variant: "full", recall: 0.92349, exposure: 0.01001, leak_bursts: 0, over_blur: 0.05 }] });
    render(<ResultsTable results={r} />);
    const row = screen.getByRole("row", { name: /Safe Cut/ });
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["92.3%", "1.1%", "0", "5.0%"]);
  });
});

describe("hero and steps (UI-SPEC §1)", () => {
  it("plays the demo with a labelled raw/Safe Cut radio group and names the auditor from the demo job", async () => {
    setClientForTests(new SafeCutClient({ transport: new MockBackend({ latencyMs: 0 }) }));
    render(
      <ModeProvider>
        <HeroAndSteps />
      </ModeProvider>,
    );
    const group = await screen.findByRole("radiogroup", { name: "Version" });
    expect(within(group).getByRole("radio", { name: "■ Safe Cut" })).toHaveAttribute("aria-checked", "true");
    expect(await screen.findByText(/Before anything is published, Meta's EgoBlur checks the final render/)).toBeInTheDocument();
    expect(screen.getByText("Muse Spark decides who")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try it with an access code" })).toHaveAttribute("href", "/try");
  });

  it("with reduced motion, Play demo shows only while the clip is paused, so it never covers the controls in play", async () => {
    const real = window.matchMedia;
    window.matchMedia = ((query: string) => ({ ...real(query), matches: query === "(prefers-reduced-motion: reduce)" })) as typeof window.matchMedia;
    try {
      setClientForTests(new SafeCutClient({ transport: new MockBackend({ latencyMs: 0 }) }));
      render(
        <ModeProvider>
          <HeroAndSteps />
        </ModeProvider>,
      );
      const player = await screen.findByLabelText("The demo clip after Safe Cut");
      const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
      fireEvent.click(screen.getByRole("button", { name: "Play demo" }));
      // jsdom can't focus a video; the e2e checks focus moves to the player in Chromium.
      expect(play).toHaveBeenCalled();
      fireEvent.play(player);
      await waitFor(() => expect(screen.queryByRole("button", { name: "Play demo" })).not.toBeInTheDocument());
      fireEvent.pause(player);
      expect(await screen.findByRole("button", { name: "Play demo" })).toBeInTheDocument();
      fireEvent.play(player);
      await waitFor(() => expect(screen.queryByRole("button", { name: "Play demo" })).not.toBeInTheDocument());
      // Switching version mounts a new, paused element.
      fireEvent.click(screen.getByRole("radio", { name: /Raw/ }));
      expect(await screen.findByRole("button", { name: "Play demo" })).toBeInTheDocument();
    } finally {
      window.matchMedia = real;
      vi.restoreAllMocks();
    }
  });

  it("a refetch that gives back the same URL says the video didn't load, with the poster kept", async () => {
    setClientForTests(new SafeCutClient({ transport: new MockBackend({ latencyMs: 0 }) }));
    render(
      <ModeProvider>
        <HeroAndSteps />
      </ModeProvider>,
    );
    fireEvent.error(await screen.findByLabelText("The demo clip after Safe Cut"));
    expect(await screen.findByText("The demo video didn't load. You can still try Safe Cut with an access code.")).toBeInTheDocument();
  });

  it("refetches the demo on a video error, re-arms after a load, and keeps the poster under the failure message (§1.4)", async () => {
    const backend = new MockBackend({ latencyMs: 0 });
    // Each answer signs its URLs afresh, as the live API does.
    let signed = 0;
    const original = backend.request.bind(backend);
    vi.spyOn(backend, "request").mockImplementation(async (init) => {
      const raw = await original(init);
      if (!init.path.startsWith("/v1/demo/")) return raw;
      signed += 1;
      const d = raw.body as { video_url: string; job: { prepared_url: string } };
      return { ...raw, body: { ...d, video_url: `${d.video_url}?sig=${signed}`, job: { ...d.job, prepared_url: `${d.job.prepared_url}?sig=${signed}` } } };
    });
    setClientForTests(new SafeCutClient({ transport: backend }));
    render(
      <ModeProvider>
        <HeroAndSteps />
      </ModeProvider>,
    );
    const demoGets = () => backend.log.filter((l) => l.path.startsWith("/v1/demo/")).length;
    const player = () => screen.getByLabelText("The demo clip after Safe Cut");
    await screen.findByLabelText("The demo clip after Safe Cut");
    const poster = player().getAttribute("poster");
    expect(poster).toBeTruthy();
    fireEvent.error(player());
    await waitFor(() => expect(demoGets()).toBe(2));
    fireEvent.loadedMetadata(await screen.findByLabelText("The demo clip after Safe Cut"));
    fireEvent.error(player());
    await waitFor(() => expect(demoGets()).toBe(3));
    fireEvent.error(await screen.findByLabelText("The demo clip after Safe Cut"));
    expect(await screen.findByText("The demo video didn't load. You can still try Safe Cut with an access code.")).toBeInTheDocument();
    expect(document.querySelector("figure img")).toHaveAttribute("src", poster);
  });
});
