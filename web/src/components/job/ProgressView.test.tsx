import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProgressView, fmtDuration } from "./ProgressView";

function setup() {
  // user-event installs its own clipboard; tests replace it after setup.
  const user = userEvent.setup();
  render(<ProgressView fileName="clip.mp4" duration={12} active="track" jobId="job-1" onDeleted={() => undefined} />);
  return user;
}
const stub = (clipboard: unknown) => Object.defineProperty(navigator, "clipboard", { value: clipboard, configurable: true });

afterEach(() => vi.restoreAllMocks());

describe("Copy link (UI-SPEC §2.5)", () => {
  it("copies the review link", async () => {
    const user = setup();
    const writeText = vi.fn(() => Promise.resolve());
    stub({ writeText });
    await user.click(screen.getByRole("button", { name: "Copy link" }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/jobs/job-1`);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Link copied.");
    // The label resets, so a second copy also confirms.
    await screen.findByRole("button", { name: "Copy link" }, { timeout: 3_000 });
  });

  it("the review link can wrap on a narrow screen", () => {
    setup();
    expect(screen.getByText(`${window.location.origin}/jobs/job-1`)).toHaveClass("break-all");
  });

  it("in mock mode, says the review link only works in this browser", () => {
    setup();
    expect(screen.getByText(/in this preview it only works in this browser/)).toBeInTheDocument();
  });

  it.each([
    ["the browser refuses", { writeText: () => Promise.reject(new DOMException("denied", "NotAllowedError")) }],
    ["there's no Clipboard API (not a secure context)", undefined],
  ])("says so and selects the link when %s", async (_, clipboard) => {
    const user = setup();
    stub(clipboard);
    await user.click(screen.getByRole("button", { name: "Copy link" }));
    expect(await screen.findByText("Couldn't copy. The link is selected: copy it from there.")).toBeInTheDocument();
    expect(window.getSelection()?.toString()).toBe(`${window.location.origin}/jobs/job-1`);
  });
});

describe("clip duration (§0: whole seconds round down)", () => {
  it("never rounds up to the limit", () => {
    expect(fmtDuration(59.6)).toBe("0:59");
    expect(fmtDuration(60)).toBe("1:00");
    expect(fmtDuration(8)).toBe("0:08");
    expect(fmtDuration(0.4)).toBe("0:00");
  });
});

describe("while the clip uploads (UI-SPEC §2.3, §2.7)", () => {
  it("shows a progress bar with the percent, and asks to keep the page open instead of offering the link", () => {
    render(<ProgressView fileName="clip.mp4" duration={12} active="uploading" uploadPercent={45} jobId="job-1" onDeleted={() => undefined} />);
    expect(screen.getByRole("progressbar", { name: "Upload progress" })).toHaveAttribute("value", "45");
    expect(screen.getByText("45%")).toBeInTheDocument();
    expect(screen.getByText("Keep this page open until the upload finishes. Leaving now stops it.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy link" })).toBeNull();
  });

  it("offers the review link once the upload is done", () => {
    render(<ProgressView fileName="clip.mp4" duration={12} active="prepare" jobId="job-1" onDeleted={() => undefined} />);
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});
