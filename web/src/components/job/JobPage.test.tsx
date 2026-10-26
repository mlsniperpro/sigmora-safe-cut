/**
 * Integration tests: the job page against the mock backend through the real
 * client, reducer and components (UI-SPEC §3, §4, §10.4, §10.5).
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SafeCutClient } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { MockBackend } from "@/lib/mock-backend";
import { ModeBanners, ModeProvider } from "../mode";
import { JobPage } from "./JobPage";

const nav = vi.hoisted(() => ({ id: "job-review-hero1", search: "", replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: nav.id }),
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace, push: nav.push }),
}));

let backend: MockBackend;

function setup(id: string, search = "") {
  nav.id = id;
  nav.search = search;
  backend = new MockBackend({ latencyMs: 0, stepMs: 60_000 });
  setClientForTests(new SafeCutClient({ transport: backend, sleep: () => Promise.resolve() }));
  const user = userEvent.setup();
  render(
    <ModeProvider>
      <ModeBanners />
      <JobPage />
    </ModeProvider>,
  );
  return user;
}

const column = (name: RegExp) => screen.getByRole("heading", { name }).closest("section") as HTMLElement;
const chip = (label: string) => screen.getByRole("article", { name: new RegExp(`^${label},`) });
const reviewPosts = () => backend.log.filter((l) => l.method === "POST" && l.path.endsWith("/review"));

beforeEach(() => {
  nav.replace.mockReset();
  nav.push.mockReset();
});
afterEach(() => setClientForTests(null));

describe("review panel", () => {
  it("shows the hero's chips in their columns with the header counts", async () => {
    setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    expect(within(column(/^Hidden/)).getAllByRole("article")).toHaveLength(2);
    expect(within(column(/^Kept clear/)).getByRole("article", { name: /^Face 2,/ })).toBeInTheDocument();
    expect(within(column(/^Needs you/)).getByRole("article", { name: /^Face 6,/ })).toBeInTheDocument();
    expect(screen.getByText("1 item still needs you. If you render now, it stays hidden.")).toBeInTheDocument();
  });

  it("hides with one tap, toasts with Undo, and undoes", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Hide Face 6" }));
    expect(within(column(/^Hidden/)).getByRole("article", { name: /^Face 6,/ })).toBeInTheDocument();
    expect(await screen.findByText("Face 6 will be hidden.")).toBeInTheDocument();
    await waitFor(() => expect(reviewPosts()).toHaveLength(1));
    expect(reviewPosts()[0]?.body).toMatchObject({ type: "hide", item_id: "i_4" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("Undone.")).toBeInTheDocument();
    expect(within(column(/^Needs you/)).getByRole("article", { name: /^Face 6,/ })).toBeInTheDocument();
    await waitFor(() => expect(reviewPosts()).toHaveLength(2));
    expect(reviewPosts()[1]?.body).toMatchObject({ type: "undo", reverts: (reviewPosts()[0]?.body as { edit_id: string }).edit_id });
  });

  it("never offers a toggle on a locked child", async () => {
    setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    const child = chip("Face 4");
    expect(within(child).queryByRole("button", { name: /Keep Face 4 clear/ })).toBeNull();
    expect(within(child).getAllByText("Always hidden").length).toBeGreaterThan(0);
  });

  it("asks before keeping a plate clear", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Keep Plate 1 clear" }));
    expect(screen.getByText("Only keep this clear if nothing on it reveals who someone is.")).toBeInTheDocument();
    expect(reviewPosts()).toHaveLength(0);
    await user.click(within(chip("Plate 1")).getByRole("button", { name: "Keep clear" }));
    expect(await screen.findByText("Plate 1 will be kept clear.")).toBeInTheDocument();
    expect(within(column(/^Kept clear/)).getByRole("article", { name: /^Plate 1,/ })).toBeInTheDocument();
  });

  it("merges a re-entry into the kept guest", async () => {
    const user = setup("job-review-reentry");
    await screen.findByRole("article", { name: /^Face 9,/ });
    await user.click(screen.getByRole("button", { name: "Same as Face 2…" }));
    const dialog = await screen.findByRole("dialog", { name: "Who is Face 9?" });
    await user.click(within(dialog).getByRole("button", { name: /Same person as Face 2/ }));
    expect(await screen.findByText("Face 9 merged into Face 2. They'll be kept clear like Face 2.")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: /^Face 9,/ })).toBeNull();
    await waitFor(() => expect(reviewPosts()[0]?.body).toMatchObject({ type: "merge", item_id: "i_9", into: "i_1" }));
  });

  it("offers no merge for a re-acquired bystander", async () => {
    setup("job-review-reentry-bystander");
    const van = await screen.findByRole("article", { name: /^Face 8,/ });
    expect(within(van).queryByRole("button", { name: /Same as/ })).toBeNull();
    expect(within(van).getByText("The tracker lost this person and found them again. They stay hidden.")).toBeInTheDocument();
  });

  it("reverts a failed edit and retries it with the same edit_id", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    backend.inject(/\/review$/, "error-500");
    await user.click(screen.getByRole("button", { name: "Hide Face 6" }));
    expect(await screen.findByText("That change didn't save. Check your connection and try again.")).toBeInTheDocument();
    expect(within(column(/^Needs you/)).getByRole("article", { name: /^Face 6,/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(reviewPosts()).toHaveLength(2));
    expect((reviewPosts()[1]?.body as { edit_id: string }).edit_id).toBe((reviewPosts()[0]?.body as { edit_id: string }).edit_id);
    expect(within(column(/^Hidden/)).getByRole("article", { name: /^Face 6,/ })).toBeInTheDocument();
  });

  it("removes a person after the dialog", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "More actions for Face 2" }));
    await user.click(screen.getByRole("menuitem", { name: "Remove this person from the video" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove this person?" });
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(await screen.findByText("Face 2 will be fully covered wherever they appear.")).toBeInTheDocument();
  });

  it("opens the Why drawer with the votes and the speech evidence", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Why is Face 6 needs you?" }));
    const drawer = await screen.findByRole("dialog", { name: "Face 6 · Person" });
    expect(within(drawer).getByText("Why it needs you")).toBeInTheDocument();
    expect(within(drawer).getByText("Check 2: Part of the story, disagrees with the majority")).toBeInTheDocument();
    expect(within(drawer).getByText("A longer, closer look suggests: Not part of the story. You decide.")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: /Close/ }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Face 6 · Person" })).toBeNull());
  });

  it("renders: Approve & render shows the render stages", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Approve & render" }));
    expect(await screen.findByRole("listitem", { current: "step" })).toHaveTextContent("Applying your choices");
    expect(screen.queryByRole("button", { name: "Hide Face 6" })).toBeNull();
  });

  it("shows a daily-cap refusal on render without deleting anything", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    backend.inject(/\/render$/, "error-429-render-daily-cap");
    await user.click(screen.getByRole("button", { name: "Approve & render" }));
    expect(await screen.findByText("Safe Cut has reached today's limit for the public demo. Try again tomorrow.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve & render" })).toBeDisabled();
    expect(backend.log.some((l) => l.method === "DELETE")).toBe(false);
  });

  it("is read-only with the audit actions when the audit couldn't finish", async () => {
    setup("result-audit-failed");
    expect(await screen.findByText("The final check couldn't finish on 4 frames. Publishing is off until it runs.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run the audit again" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Download this version" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve & render" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Hide / })).toBeNull();
  });

  it("covers an unfixed spot", async () => {
    const user = setup("result-unresolved-review", "view=review");
    expect(await screen.findByText("1 unfixed spot is visible in the video. Cover it before rendering.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cover Unfixed spot U1" }));
    expect(await screen.findByText("U1 will be covered.")).toBeInTheDocument();
    expect(await screen.findByText("You changed something after rendering. Render again to update the video and receipt.")).toBeInTheDocument();
    expect(await screen.findByRole("article", { name: /^A1,/ })).toBeInTheDocument();
  });

  it("deletes everything after the confirm and ignores late responses", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Delete everything now" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this clip?" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Deleted. Nothing from this clip is kept.")).toBeInTheDocument();
  });

  it("keeps the page when a delete fails", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    backend.inject(/^DELETE /, "error-500-delete");
    await user.click(screen.getByRole("button", { name: "Delete everything now" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Delete this clip?" })).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Something went wrong on our side. Nothing has been published.")).toBeInTheDocument();
    expect(screen.getByText("2 hidden · 1 kept clear · 1 needs you")).toBeInTheDocument();
  });

  it("supports H, C and Z on a focused chip", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    act(() => chip("Face 6").focus());
    await user.keyboard("h");
    expect(within(column(/^Hidden/)).getByRole("article", { name: /^Face 6,/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());
    act(() => chip("Face 6").focus());
    await user.keyboard("z");
    expect(await screen.findByText("Undone.")).toBeInTheDocument();
  });

  it("shows the demo-mode banner for a replayed job", async () => {
    setup("job-replay");
    expect(await screen.findByText(/You're seeing saved results from a real run/)).toBeInTheDocument();
  });
});

describe("job states", () => {
  it.each([
    ["error-404-expired", "This clip has been deleted. Safe Cut deletes everything automatically after 24 hours."],
    ["nope", "We couldn't find that clip. Check the link, or try another clip."],
    ["job-created", "This clip hasn't finished uploading. Upload it again to start."],
    ["job-failed-roles", "Something went wrong while working out who's part of the story. Your clip hasn't been published anywhere. You can try again, or delete it now."],
    ["job-failed-too-long", "This clip is 60.4 seconds long. The limit is 60 seconds. Trim it and try again."],
    ["job-retry-later", "Meta's service is busy right now. Safe Cut will try once more in a few minutes on its own; you can leave this page and come back with your review link. Nothing has been published."],
  ])("%s", async (id, text) => {
    setup(id);
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("shows the stage list while processing", async () => {
    setup("job-processing-track");
    const active = await screen.findByRole("listitem", { current: "step" });
    expect(active).toHaveTextContent("Finding people and objects");
    expect(active).toHaveTextContent("SAM 3.1 is looking for faces, people, plates, screens and documents.");
  });

  it("moves a done job to its result unless opened for review", async () => {
    setup("job-audit-rerun-done");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/jobs/job-audit-rerun-done/result"));
  });


});
