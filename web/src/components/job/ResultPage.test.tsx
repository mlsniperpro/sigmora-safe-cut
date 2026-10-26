import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SafeCutClient } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { MockBackend } from "@/lib/mock-backend";
import { ModeProvider } from "../mode";
import { ResultPage } from "./ResultPage";

const nav = vi.hoisted(() => ({ id: "result-clean", search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: nav.id }),
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
