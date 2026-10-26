/**
 * `/try` against the mock backend: the happy path and the §2.6 refusals.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SafeCutClient } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { MockBackend } from "@/lib/mock-backend";
import { TryFlow } from "./TryFlow";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }), usePathname: () => "/try" }));

let backend: MockBackend;
let now = 0;

/** A clip whose metadata reports `duration` seconds (jsdom has no media pipeline). */
function clip(name = "street.mp4", type = "video/mp4", size = 1_000_000) {
  return new File([new Uint8Array(Math.min(size, 16))], name, { type });
}

function setup(latencyMs = 0) {
  backend = new MockBackend({ latencyMs, stepMs: 1_000, now: () => now });
  setClientForTests(new SafeCutClient({ transport: backend, sleep: () => Promise.resolve() }));
  const user = userEvent.setup({ applyAccept: false });
  render(<TryFlow />);
  return user;
}

let duration = 30;
beforeEach(() => {
  now = 0;
  duration = 30;
  push.mockReset();
  URL.createObjectURL = vi.fn(() => "blob:clip");
  URL.revokeObjectURL = vi.fn();
  // Fire loadedmetadata with the scripted duration whenever a video gets a src.
  Object.defineProperty(HTMLMediaElement.prototype, "src", {
    configurable: true,
    set(this: HTMLVideoElement) {
      Object.defineProperty(this, "duration", { configurable: true, value: duration });
      setTimeout(() => this.onloadedmetadata?.(new Event("loadedmetadata")), 0);
    },
    get() {
      return "";
    },
  });
});
afterEach(() => setClientForTests(null));

async function enterCode(user: ReturnType<typeof userEvent.setup>, code: string) {
  await user.type(screen.getByLabelText("Access code"), code);
  await user.click(screen.getByRole("button", { name: "Continue" }));
}

const fileInput = () => document.querySelector<HTMLInputElement>('input[type="file"]')!;

describe("/try", () => {
  it("asks for a code when it's empty", async () => {
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Enter your access code.")).toBeInTheDocument();
    expect(screen.getByLabelText("Access code")).toHaveFocus();
  });

  it("masks the code and has a Show toggle", async () => {
    const user = setup();
    const input = screen.getByLabelText("Access code");
    expect(input).toHaveClass("masked");
    expect(input).toHaveAttribute("autocomplete", "off");
    expect(input).toHaveAttribute("maxlength", "64");
    await user.click(screen.getByRole("button", { name: "Show" }));
    expect(input).not.toHaveClass("masked");
  });

  it("selects a wrong code's text", async () => {
    const user = setup();
    await enterCode(user, "wrong");
    expect(await screen.findByText("That code didn't work. Check it and try again.")).toBeInTheDocument();
    const input = screen.getByLabelText<HTMLInputElement>("Access code");
    expect(input.selectionStart).toBe(0);
    expect(input.selectionEnd).toBe(5);
  });

  it("explains a code that isn't active yet", async () => {
    const user = setup();
    await enterCode(user, "not-yet");
    expect(await screen.findByText(/^This code isn't active yet\. It works from .+ to .+\.$/)).toBeInTheDocument();
  });

  it("rejects the wrong type, two files and a too-long clip", async () => {
    const user = setup();
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip("a.avi", "video/x-msvideo"));
    expect(await screen.findByText("Safe Cut takes MP4 or MOV video files.")).toBeInTheDocument();
    fireEvent.drop(screen.getByText(/Drop a clip here/).closest("div")!, { dataTransfer: { files: [clip(), clip("b.mp4")] } });
    expect(await screen.findByText("Drop one clip at a time.")).toBeInTheDocument();
    duration = 61.2;
    await user.upload(fileInput(), clip());
    expect(await screen.findByText("This clip is 61.2 seconds long. The limit is 60 seconds. Trim it and try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  });

  it("needs the rights tick before starting", async () => {
    const user = setup();
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(screen.getByText("Tick the box to confirm you're 18 or over, can upload this clip and aren't in a restricted territory.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toHaveFocus();
  });

  it("uploads, starts, shows progress and moves to the review panel", async () => {
    const user = setup();
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText("Working on your clip")).toBeInTheDocument();
    await waitFor(() => expect(backend.log.some((l) => l.path.endsWith("/start"))).toBe(true));
    expect(backend.log.find((l) => l.path === "/v1/jobs")?.body).toMatchObject({ code: "judge", content_type: "video/mp4", file_name: "street.mp4" });
    now = 1_000_000;
    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/j_mock1"), { timeout: 5_000 });
  });

  it("refuses at start with a revoked code, offers a different code, and deletes the job once", async () => {
    const user = setup();
    await enterCode(user, "revoked");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    const alert = await screen.findByText("That code didn't work. Check it and try again.");
    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
    await waitFor(() => expect(backend.log.filter((l) => l.method === "DELETE")).toHaveLength(1));
    await user.click(within(alert.closest("div")!).getByRole("button", { name: "Use a different code" }));
    expect(screen.getByLabelText("Access code")).toBeInTheDocument();
  });

  it("keeps Start enabled and the job when the final check is unavailable", async () => {
    const user = setup();
    await enterCode(user, "no-auditor");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText("Safe Cut's final check isn't available right now, so it can't start new clips. Try again later.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start" })).toBeEnabled();
    expect(backend.log.some((l) => l.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Start" }));
    // The re-press re-sends only POST /start for the same job.
    await waitFor(() => expect(backend.log.filter((l) => l.path.endsWith("/start"))).toHaveLength(2));
    expect(backend.log.filter((l) => l.path === "/v1/jobs")).toHaveLength(1);
  });

  it("refuses a code with no budget before uploading", async () => {
    const user = setup();
    await enterCode(user, "no-budget");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText(/This access code doesn't have enough budget left for this clip/)).toBeInTheDocument();
    expect(backend.log.some((l) => l.path.endsWith("/start"))).toBe(false);
  });

  it("shows the Baseten line only for a code with open_weight", async () => {
    const user = setup();
    await enterCode(user, "open-weight");
    expect(await screen.findByText("Sampled frames of the result also go to Baseten, which runs Muse Spark Open.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "territory where Meta's API is restricted" })).toHaveAttribute("href", "https://dev.meta.ai/legal/geographic-use-policy");
  });

  it("no Baseten line for an ordinary code", async () => {
    const user = setup();
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    expect(screen.queryByText(/Baseten/)).toBeNull();
  });

  it("cancelling during the upload stays deleted and never re-uploads", async () => {
    const user = setup(80);
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    await screen.findByRole("listitem", { current: "step" });
    await user.click(screen.getByRole("button", { name: "Cancel and delete" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Delete this clip?" })).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Deleted from Safe Cut's servers.")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 600));
    expect(screen.getByText("Deleted from Safe Cut's servers.")).toBeInTheDocument();
    expect(screen.queryByText(/The upload stopped/)).toBeNull();
    expect(backend.log.filter((l) => l.path === "/v1/jobs")).toHaveLength(1);
    expect(backend.log.some((l) => l.path.endsWith("/start"))).toBe(false);
  });

  it("a slow POST /start still reaches the review panel (polling starts after start, not at 100% upload)", async () => {
    backend = new MockBackend({ latencyMs: 0, stepMs: 1_000, now: () => now });
    const slowStart = {
      request: async (init: Parameters<MockBackend["request"]>[0]) => {
        if (init.path.endsWith("/start")) await new Promise((r) => setTimeout(r, 300));
        return backend.request(init);
      },
      upload: backend.upload.bind(backend),
    };
    setClientForTests(new SafeCutClient({ transport: slowStart, sleep: () => Promise.resolve() }));
    const user = userEvent.setup({ applyAccept: false });
    render(<TryFlow />);
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(backend.log.some((l) => l.path.endsWith("/start"))).toBe(true));
    // No GET before the start is answered: a "created" answer would stop polling for good.
    const startIndex = backend.log.findIndex((l) => l.path.endsWith("/start"));
    expect(backend.log.slice(0, startIndex).some((l) => l.method === "GET")).toBe(false);
    now = 1_000_000;
    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/j_mock1"), { timeout: 5_000 });
  });

  it("Try another clip after a delete starts over at the access code", async () => {
    const user = setup();
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    await user.click(await screen.findByRole("button", { name: "Cancel and delete" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Delete this clip?" })).getByRole("button", { name: "Delete" }));
    await user.click(await screen.findByRole("button", { name: "Try another clip" }));
    expect(screen.getByLabelText("Access code")).toHaveFocus();
  });

  it("cancels and deletes from the progress step", async () => {
    const user = setup();
    await enterCode(user, "judge");
    await screen.findByRole("button", { name: "Choose a file" });
    await user.upload(fileInput(), clip());
    await screen.findByText(/street\.mp4/);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start" }));
    await user.click(await screen.findByRole("button", { name: "Cancel and delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this clip?" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Deleted from Safe Cut's servers.")).toBeInTheDocument();
  });
});
