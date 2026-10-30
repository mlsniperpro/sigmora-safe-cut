import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModeBanners, ModeProvider, useReportMode } from "./mode";

const nav = vi.hoisted(() => ({ path: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.path }));

function Reporter() {
  useReportMode("replay");
  return null;
}

describe("demo mode is per page (UI-SPEC §6)", () => {
  it("shows on the page that got a replay response, and not after moving to another page", async () => {
    nav.path = "/";
    const { rerender } = render(
      <ModeProvider>
        <Reporter />
        <ModeBanners />
      </ModeProvider>,
    );
    expect(await screen.findByText(/You're seeing saved results from a real run/)).toBeInTheDocument();
    nav.path = "/try";
    rerender(
      <ModeProvider>
        <ModeBanners />
      </ModeProvider>,
    );
    expect(screen.queryByText(/You're seeing saved results from a real run/)).toBeNull();
  });
});

describe("mock mode (no API configured)", () => {
  it("says the replayed results are sample data, so the demo banner never claims a real run alone", async () => {
    nav.path = "/jobs/job-replay";
    render(
      <ModeProvider>
        <Reporter />
        <ModeBanners />
      </ModeProvider>,
    );
    expect(await screen.findByText(/In this preview the saved results are sample data/)).toBeInTheDocument();
    expect(screen.getByText(/nothing leaves your browser/)).toBeInTheDocument();
  });
});
