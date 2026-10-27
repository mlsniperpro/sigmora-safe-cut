import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProgressView } from "./ProgressView";

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
