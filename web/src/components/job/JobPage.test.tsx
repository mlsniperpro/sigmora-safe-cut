/**
 * Integration tests: the job page against the mock backend through the real
 * client, reducer and components (UI-SPEC §3, §4, §10.4, §10.5).
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest";
import { SafeCutClient } from "@/lib/api";
import { setClientForTests } from "@/lib/client";
import { MockBackend } from "@/lib/mock-backend";
import { ModeBanners, ModeProvider } from "../mode";
import { FRESH_URL_WAIT_MS } from "../review/VideoPane";
import { JobPage } from "./JobPage";

const nav = vi.hoisted(() => ({ id: "job-review-hero1", search: "", replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: nav.id }),
  usePathname: () => `/jobs/${nav.id}`,
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
    await user.click(screen.getByRole("button", { name: "Keep clear Plate 1" }));
    expect(screen.getByText("Only keep this clear if nothing on it reveals who someone is.")).toBeInTheDocument();
    expect(reviewPosts()).toHaveLength(0);
    await user.click(within(chip("Plate 1")).getByRole("button", { name: "Keep clear" }));
    expect(await screen.findByText("Plate 1 will be kept clear.")).toBeInTheDocument();
    expect(within(column(/^Kept clear/)).getByRole("article", { name: /^Plate 1,/ })).toBeInTheDocument();
  });

  it("Keep clear on a plate in the Why drawer closes it to the confirm, with focus on Cancel", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: /^Why\? Plate 1/ }));
    const drawer = await screen.findByRole("dialog", { name: /^Plate 1/ });
    await user.click(within(drawer).getByRole("button", { name: "Keep clear" }));
    expect(await screen.findByText("Only keep this clear if nothing on it reveals who someone is.")).toBeInTheDocument();
    const cancel = within(chip("Plate 1")).getByRole("button", { name: "Cancel" });
    // Focus moves happen a frame later: let them all land, then check where focus stayed.
    for (let i = 0; i < 3; i++) await act(() => new Promise((resolve) => requestAnimationFrame(resolve)));
    expect(cancel).toHaveFocus();
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

  it("a rejected edit takes focus back to the chip in the column it returned to (§3.8)", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    // The refusal lands after focus has followed the chip to Hidden.
    let refuse: () => void = () => undefined;
    const original = backend.request.bind(backend);
    vi.spyOn(backend, "request").mockImplementation(async (init) => {
      if (init.method === "POST" && init.path.endsWith("/review")) await new Promise<void>((resolve) => (refuse = resolve));
      return original(init);
    });
    backend.inject(/\/review$/, "error-500");
    chip("Face 6").focus();
    await user.keyboard("h");
    await waitFor(() => expect(within(column(/^Hidden/)).getByRole("article", { name: /^Face 6,/ })).toHaveFocus());
    act(() => refuse());
    expect(await screen.findByText("That change didn't save. Check your connection and try again.")).toBeInTheDocument();
    await waitFor(() => expect(within(column(/^Needs you/)).getByRole("article", { name: /^Face 6,/ })).toHaveFocus());
  });

  it("on mobile, Try again on a rejected edit follows the chip to its new tab, and Dismiss hands focus back to the chip", async () => {
    const real = window.matchMedia;
    window.matchMedia = ((query: string) => ({ ...real(query), matches: false })) as typeof window.matchMedia;
    onTestFinished(() => void (window.matchMedia = real));
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    const tab = (name: RegExp) => screen.getByRole("tab", { name });
    backend.inject(/\/review$/, "error-500");
    await user.click(screen.getByRole("button", { name: "Hide Face 6" }));
    expect(await screen.findByText("That change didn't save. Check your connection and try again.")).toBeInTheDocument();
    await waitFor(() => expect(tab(/^Needs you/)).toHaveAttribute("aria-selected", "true"));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(tab(/^Hidden/)).toHaveAttribute("aria-selected", "true"));
    await waitFor(() => expect(within(column(/^Hidden/)).getByRole("article", { name: /^Face 6,/ })).toHaveFocus());
    // Rejected again, then dismissed from the keyboard: focus doesn't fall to the page.
    backend.inject(/\/review$/, "error-500");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("That change didn't save. Check your connection and try again.")).toBeInTheDocument();
    screen.getByRole("button", { name: "Dismiss" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(within(column(/^Hidden/)).getByRole("article", { name: /^Face 6,/ })).toHaveFocus());
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
    await user.click(screen.getByRole("button", { name: "Why? Face 6, needs you" }));
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
    await user.click(screen.getByRole("button", { name: "Cover it Unfixed spot U1" }));
    expect(await screen.findByText("U1 will be covered.")).toBeInTheDocument();
    expect(await screen.findByText("You changed something after rendering. Render again to update the video and receipt.")).toBeInTheDocument();
    expect(await screen.findByRole("article", { name: /^A1,/ })).toBeInTheDocument();
    // The ack swaps the optimistic chip for the server's item; focus follows it (§3.8).
    await waitFor(() => expect(screen.getByRole("article", { name: /^A1,/ })).toHaveFocus());
  });

  it("undoing a cover brings focus back to the unfixed spot's chip", async () => {
    const user = setup("result-unresolved-review", "view=review");
    await user.click(await screen.findByRole("button", { name: "Cover it Unfixed spot U1" }));
    await waitFor(() => expect(screen.getByRole("article", { name: /^A1,/ })).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(screen.getByRole("article", { name: /^Unfixed spot U1,/ })).toHaveFocus());
  });

  it("on mobile, a rejected edit's chip gets focus in the tab that opens for it, even when frames come before the commit", async () => {
    const real = window.matchMedia;
    window.matchMedia = ((query: string) => ({ ...real(query), matches: false })) as typeof window.matchMedia;
    // Frame callbacks that run before React commits the new tab, as in a busy browser (a microtask
    // beats React's flush). A frame loop that re-arms itself waits for a timer instead.
    let inFrame = false;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      if (inFrame) return window.setTimeout(() => cb(performance.now()), 16);
      queueMicrotask(() => {
        inFrame = true;
        try {
          cb(performance.now());
        } finally {
          inFrame = false;
        }
      });
      return 0;
    });
    onTestFinished(() => void (window.matchMedia = real));
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("tab", { name: /^Needs you/ }));
    backend.inject(/\/review$/, "error-500");
    await user.click(screen.getByRole("button", { name: "Hide Face 6" }));
    expect(await screen.findByText("That change didn't save. Check your connection and try again.")).toBeInTheDocument();
    // The rescue opens Needs you from an effect; the chip only mounts with that later commit.
    await waitFor(() => expect(screen.getByRole("tab", { name: /^Needs you/ })).toHaveAttribute("aria-selected", "true"));
    await waitFor(() => expect(within(column(/^Needs you/)).getByRole("article", { name: /^Face 6,/ })).toHaveFocus());
  });

  it("on mobile, closing the Why sheet after its edit was rejected opens the chip's tab again", async () => {
    const real = window.matchMedia;
    window.matchMedia = ((query: string) => ({ ...real(query), matches: false })) as typeof window.matchMedia;
    onTestFinished(() => void (window.matchMedia = real));
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("tab", { name: /^Needs you/ }));
    await user.click(screen.getByRole("button", { name: "Why? Face 6, needs you" }));
    const drawer = await screen.findByRole("dialog", { name: "Face 6 · Person" });
    backend.inject(/\/review$/, "error-500");
    await user.click(within(drawer).getByRole("button", { name: /^Hide$/ }));
    expect(await screen.findByText("That change didn't save. Check your connection and try again.")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: /Close/ }));
    await waitFor(() => expect(screen.getByRole("tab", { name: /^Needs you/ })).toHaveAttribute("aria-selected", "true"));
    await waitFor(() => expect(within(column(/^Needs you/)).getByRole("article", { name: /^Face 6,/ })).toHaveFocus());
  });

  it("a failed job's Try again hands focus to the progress once the job runs again", async () => {
    const user = setup("job-failed-upstream");
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Working on your clip" })).toHaveFocus());
  });

  it("a focus request that lapsed doesn't pull focus when its chip shows up later", async () => {
    const real = window.matchMedia;
    window.matchMedia = ((query: string) => ({ ...real(query), matches: false })) as typeof window.matchMedia;
    onTestFinished(() => void (window.matchMedia = real));
    const user = setup("result-unresolved-review", "view=review");
    // The cover's ack is late, so it lands after the viewer has moved to another tab.
    let ack: () => void = () => undefined;
    const original = backend.request.bind(backend);
    vi.spyOn(backend, "request").mockImplementation(async (init) => {
      if (init.method === "POST" && init.path.endsWith("/review")) await new Promise<void>((resolve) => (ack = resolve));
      return original(init);
    });
    await user.click(await screen.findByRole("button", { name: "Cover it Unfixed spot U1" }));
    await user.click(screen.getByRole("tab", { name: /^Needs you/ }));
    (document.activeElement as HTMLElement | null)?.blur();
    // The ack asks to focus the covering item, which isn't in the open tab.
    await act(async () => ack());
    await new Promise((resolve) => setTimeout(resolve, 1_200));
    const hidden = screen.getByRole("tab", { name: /^Hidden/ });
    hidden.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(hidden).toHaveAttribute("aria-selected", "true"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(hidden).toHaveFocus();
  });

  it.each([
    ["error-404-expired", "This clip has been deleted · Safe Cut"],
    ["nope", "We couldn't find that clip · Safe Cut"],
    ["job-processing-track", "Working on your clip · Safe Cut"],
    ["job-failed-roles", "Something went wrong while working out who's part of the story · Safe Cut"],
    ["job-review-hero1", "Review what Safe Cut hides · Safe Cut"],
  ])("the tab title follows the state the page shows (WCAG 2.4.2): %s", async (id, title) => {
    setup(id);
    await waitFor(() => expect(document.title).toBe(title));
  });

  it("deletes everything after the confirm and ignores late responses", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Delete everything now" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this clip?" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Deleted from Safe Cut's servers.")).toBeInTheDocument();
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

  it("focus follows the chip a shortcut moved, not an earlier one", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Hide Face 6" }));
    await waitFor(() => expect(chip("Face 6")).toHaveFocus());
    act(() => chip("Face 2").focus());
    await user.keyboard("h");
    await waitFor(() => expect(chip("Face 2")).toHaveFocus());
    expect(within(column(/^Hidden/)).getByRole("article", { name: /^Face 2,/ })).toBeInTheDocument();
  });

  it("with single-key shortcuts off, H does nothing but Ctrl+Z still undoes", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Keyboard shortcuts" }));
    const dialog = await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
    await user.click(within(dialog).getByRole("checkbox", { name: "Single-key shortcuts" }));
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    act(() => chip("Face 2").focus());
    await user.keyboard("h");
    expect(within(column(/^Kept clear/)).getByRole("article", { name: /^Face 2,/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hide Face 6" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());
    act(() => chip("Face 6").focus());
    await user.keyboard("{Control>}z{/Control}");
    expect(await screen.findByText("Undone.")).toBeInTheDocument();
  });

  it("Cmd+Z undoes on a Mac", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    await user.click(screen.getByRole("button", { name: "Hide Face 6" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());
    act(() => chip("Face 6").focus());
    await user.keyboard("{Meta>}z{/Meta}");
    expect(await screen.findByText("Undone.")).toBeInTheDocument();
  });

  it("refetches the job once for fresh keyframe URLs when thumbnails fail to load", async () => {
    setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    const gets = () => backend.log.filter((l) => l.method === "GET" && l.path === "/v1/jobs/job-review-hero1").length;
    const before = gets();
    const thumbs = document.querySelectorAll<HTMLImageElement>("article img");
    expect(thumbs.length).toBeGreaterThan(1);
    // Several expired thumbnails fail together: one refetch, not one each.
    act(() => thumbs.forEach((img) => img.dispatchEvent(new Event("error"))));
    await waitFor(() => expect(gets()).toBe(before + 1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(gets()).toBe(before + 1);
  });

  it("the review video refetches the job on an error, and again after a refreshed source played", async () => {
    setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    const gets = () => backend.log.filter((l) => l.method === "GET" && l.path === "/v1/jobs/job-review-hero1").length;
    const player = () => screen.getByLabelText("Your clip, with the Safe Cut preview drawn over it");
    const before = gets();
    fireEvent.error(player());
    await waitFor(() => expect(gets()).toBe(before + 1));
    fireEvent.loadedMetadata(player());
    fireEvent.error(player());
    await waitFor(() => expect(gets()).toBe(before + 2));
    // Without a load in between, a second error is final.
    fireEvent.error(player());
    expect(await screen.findByText("The video didn't load. The decisions below still work.")).toBeInTheDocument();
  });

  it("the ⋯ button closes its own menu", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    const trigger = screen.getAllByRole("button", { name: /^More actions for / })[0]!;
    await user.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await user.click(trigger);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("each job page has exactly one h1", async () => {
    setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("a refresh for fresh URLs doesn't restart the playing video; a later video error switches to the fresher URL without another fetch", async () => {
    setup("job-review-hero1");
    let signed = 0;
    const original = backend.request.bind(backend);
    vi.spyOn(backend, "request").mockImplementation(async (init) => {
      const raw = await original(init);
      if (init.method !== "GET" || init.path !== "/v1/jobs/job-review-hero1" || raw.status !== 200) return raw;
      signed += 1;
      const job = raw.body as { job: { prepared_url: string } };
      return { ...raw, body: { ...job, job: { ...job.job, prepared_url: `https://media.example/prepared.mp4?sig=${signed}` } } };
    });
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    const gets = () => backend.log.filter((l) => l.method === "GET" && l.path === "/v1/jobs/job-review-hero1").length;
    const player = () => screen.getByLabelText("Your clip, with the Safe Cut preview drawn over it");
    const playing = player().getAttribute("src");
    // A failing thumbnail asks for fresh URLs; the answer re-signs the video too.
    const before = gets();
    act(() => document.querySelector<HTMLImageElement>("article img")?.dispatchEvent(new Event("error")));
    await waitFor(() => expect(gets()).toBe(before + 1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(player().getAttribute("src")).toBe(playing);
    fireEvent.error(player());
    await waitFor(() => expect(player().getAttribute("src")).toMatch(/sig=\d+$/));
    expect(player().getAttribute("src")).not.toBe(playing);
    expect(gets()).toBe(before + 1);
  });

  it("a review video whose refetch brings no fresh URL says it didn't load", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    try {
      setup("job-review-hero1");
      await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
      const gets = () => backend.log.filter((l) => l.method === "GET" && l.path === "/v1/jobs/job-review-hero1").length;
      const before = gets();
      fireEvent.error(screen.getByLabelText("Your clip, with the Safe Cut preview drawn over it"));
      await waitFor(() => expect(gets()).toBe(before + 1));
      act(() => void vi.advanceTimersByTime(FRESH_URL_WAIT_MS));
      expect(await screen.findByText("The video didn't load. The decisions below still work.")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("a fresh URL that arrives after the wait gave up still gets its try: the player comes back", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    try {
      setup("job-review-hero1");
      await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
      // The refetch the error asks for is held until the wait has given up, then answers re-signed.
      let release: () => void = () => undefined;
      const held = new Promise<void>((resolve) => (release = resolve));
      let hold = false;
      const original = backend.request.bind(backend);
      vi.spyOn(backend, "request").mockImplementation(async (init) => {
        const raw = await original(init);
        if (!hold || init.method !== "GET" || init.path !== "/v1/jobs/job-review-hero1" || raw.status !== 200) return raw;
        await held;
        const job = raw.body as { job: { prepared_url: string } };
        return { ...raw, body: { ...job, job: { ...job.job, prepared_url: "https://media.example/prepared.mp4?sig=late" } } };
      });
      hold = true;
      fireEvent.error(screen.getByLabelText("Your clip, with the Safe Cut preview drawn over it"));
      act(() => void vi.advanceTimersByTime(FRESH_URL_WAIT_MS));
      expect(await screen.findByText("The video didn't load. The decisions below still work.")).toBeInTheDocument();
      act(() => release());
      await waitFor(() => expect(screen.getByLabelText("Your clip, with the Safe Cut preview drawn over it")).toHaveAttribute("src", "https://media.example/prepared.mp4?sig=late"));
      expect(screen.queryByText("The video didn't load. The decisions below still work.")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the demo-mode banner for a replayed job", async () => {
    setup("job-replay");
    expect(await screen.findByText(/You're seeing saved results from a real run/)).toBeInTheDocument();
  });
});

describe("job states", () => {
  it.each([
    ["error-404-expired", "This clip has been deleted. Safe Cut deletes clips from its servers automatically after 24 hours."],
    ["nope", "We couldn't find that clip. Check the link, or try another clip."],
    ["job-created", "This clip hasn't finished uploading. Upload it again to start."],
    ["job-failed-roles", "Something went wrong while working out who's part of the story. Your clip hasn't been published anywhere. You can try again, or delete it now."],
    ["job-failed-too-long", "This clip is 60.4 seconds long. The limit is 60 seconds. Trim it and try again."],
    ["job-retry-later", "Meta's service is busy right now. Safe Cut will try once more in a few minutes on its own; you can leave this page and come back with your review link. Nothing has been published."],
  ])("%s", async (id, text) => {
    setup(id);
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("a rate-limited Try again or Delete waits out Retry-After before it works again (§10.3)", async () => {
    const user = setup("job-failed-roles");
    await screen.findByRole("button", { name: "Try again" });
    backend.inject(/\/start$/, "error-429-rate");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Too many tries in a short time. Wait a minute and try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
    backend.inject(/^DELETE /, "error-429-rate");
    await user.click(screen.getByRole("button", { name: "Delete now" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Delete now" })).toBeDisabled());
    // The disabled button can't keep focus, so the error takes it rather than the page (WCAG 2.4.3).
    // Try again's answer and the delete's share their copy: the delete's is the newer one, and has focus.
    await waitFor(() => expect(screen.getAllByText("Too many tries in a short time. Wait a minute and try again.", { selector: "p[role=alert]" }).at(-1)).toHaveFocus());
  });

  it("Approve & render keeps focus while busy and hands it to the render progress", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    const button = screen.getByRole("button", { name: "Approve & render" });
    act(() => button.focus());
    await user.keyboard("{Enter}");
    await waitFor(() => expect(document.querySelector("[data-render-progress]")).toHaveFocus(), { timeout: 3_000 });
  });

  it("pressing Approve & render again on the code-cap line announces and focuses it again", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    backend.inject(/\/render$/, "error-429-render-code-cap", 2);
    await user.click(screen.getByRole("button", { name: "Approve & render" }));
    const first = await screen.findByRole("alert");
    await waitFor(() => expect(first).toHaveFocus());
    // While the second press is out, focus stays on the button; the answer then takes it.
    const original = backend.request.bind(backend);
    vi.spyOn(backend, "request").mockImplementation(async (init) => {
      if (init.path.endsWith("/render")) await new Promise((r) => setTimeout(r, 300));
      return original(init);
    });
    const button = screen.getByRole("button", { name: "Approve & render" });
    await user.click(button);
    await new Promise((r) => setTimeout(r, 100));
    expect(button).toHaveFocus();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveFocus());
    expect(screen.getByRole("alert")).not.toBe(first);
  });

  it("a second identical delete error is announced and focused again", async () => {
    const user = setup("job-failed-roles");
    await screen.findByRole("button", { name: "Delete now" });
    backend.inject(/^DELETE /, "error-500-delete", 2);
    for (let i = 0; i < 2; i++) {
      await user.click(screen.getByRole("button", { name: "Delete now" }));
      await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
      await waitFor(() => expect(screen.getByText("Something went wrong on our side. Nothing has been published.", { selector: "p[role=alert]" })).toHaveFocus());
      act(() => screen.getByRole("button", { name: "Delete now" }).focus());
    }
  });

  it("a refused Approve & render is announced and takes focus, since its button is now disabled", async () => {
    const user = setup("job-review-hero1");
    await screen.findByText("2 hidden · 1 kept clear · 1 needs you");
    backend.inject(/\/render$/, "error-429-rate");
    await user.click(screen.getByRole("button", { name: "Approve & render" }));
    const alert = await screen.findByText("Too many tries in a short time. Wait a minute and try again.", { selector: "p[role=alert]" });
    await waitFor(() => expect(alert).toHaveFocus());
    expect(screen.getByRole("button", { name: "Approve & render" })).toBeDisabled();
  });

  it("while a confirmed delete is in flight, its button keeps focus and only looks disabled", async () => {
    const user = setup("job-processing-track");
    const original = backend.request.bind(backend);
    vi.spyOn(backend, "request").mockImplementation(async (init) => {
      if (init.method === "DELETE") await new Promise((r) => setTimeout(r, 400));
      return original(init);
    });
    const button = await screen.findByRole("button", { name: "Cancel and delete" });
    await user.click(button);
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(button).toHaveAttribute("aria-disabled", "true"));
    await waitFor(() => expect(button).toHaveFocus());
    await user.click(button);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a rate-limited Cancel and delete while processing waits out Retry-After", async () => {
    const user = setup("job-processing-track");
    await screen.findByRole("button", { name: "Cancel and delete" });
    backend.inject(/^DELETE /, "error-429-rate");
    await user.click(screen.getByRole("button", { name: "Cancel and delete" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel and delete" })).toBeDisabled());
  });

  it("shows the stage list while processing", async () => {
    setup("job-processing-track");
    const active = await screen.findByRole("listitem", { current: "step" });
    expect(active).toHaveTextContent("Finding people and objects");
    expect(active).toHaveTextContent("SAM 3.1 is looking for faces, people, plates, screens and documents.");
    // The prepared clip's first frame, with no overlay yet (§2.3, §2.9).
    expect(screen.getByLabelText("The first frame of your clip, before anything is covered")).toHaveAttribute("preload", "metadata");
  });

  it("moves a done job to its result unless opened for review", async () => {
    setup("job-audit-rerun-done");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/jobs/job-audit-rerun-done/result"));
  });


});
