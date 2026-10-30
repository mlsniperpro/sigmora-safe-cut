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

function SyntheticReporter() {
  useReportMode("replay", true);
  return null;
}

describe("a synthetic replay says so", () => {
  it("never claims a real run for synthetic recordings", async () => {
    nav.path = "/jobs/job-replay";
    render(
      <ModeProvider>
        <SyntheticReporter />
        <ModeBanners />
      </ModeProvider>,
    );
    expect(await screen.findByText(/saved results for a synthetic test clip/)).toBeInTheDocument();
    expect(screen.queryByText(/from a real run/)).toBeNull();
  });

  it("shows no banner for a live response", () => {
    nav.path = "/";
    function Live() {
      useReportMode("live");
      return null;
    }
    render(
      <ModeProvider>
        <Live />
        <ModeBanners />
      </ModeProvider>,
    );
    expect(screen.queryByRole("status")).toBeNull();
  });
});
