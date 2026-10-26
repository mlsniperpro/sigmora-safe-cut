import fc from "fast-check";
import { describe, expect, it } from "vitest";
import cafeMock from "../../../mocks/job-review-cafe.json";
import heroMock from "../../../mocks/job-review-hero1.json";
import reducerFixture from "../../../mocks/reducer-state.json";
import reentryMock from "../../../mocks/job-review-reentry.json";
import unresolvedMock from "../../../mocks/result-unresolved-review.json";
import auditFailedLeakMock from "../../../mocks/result-audit-failed-with-leak.json";
import jobCapMock from "../../../mocks/result-audit-over-budget-jobcap.json";
import coverAck from "../../../mocks/review-ack-cover-spot.json";
import { jobResponseSchema, type Item, type JobResponse } from "../contracts";
import { selectBar } from "./bar";
import {
  effectiveDecision,
  initialState,
  spotLabels,
  step,
  tracksShown,
  uncoveredSpots,
  visibleItems,
  type Action,
  type ReviewState,
  type ServerState,
} from "./reducer";

const job = (raw: unknown): JobResponse => jobResponseSchema.parse(raw);
const serverOf = (j: JobResponse): ServerState => ({
  items: j.items,
  plan: j.plan ?? { frames: {}, crowd_fills: [] },
  status: j.status,
  has_render: j.has_render,
  spots: j.audit?.spots ?? [],
});
const fromJob = (raw: unknown): ReviewState => {
  const j = job(raw);
  return initialState(serverOf(j), { tracks: j.tracks, roles: j.roles });
};
const fromFixture = (): ReviewState => ({
  ...(structuredClone(reducerFixture) as unknown as Omit<ReviewState, "toast" | "rejected" | "server" | "context">),
  toast: null,
  rejected: {},
  server: { items: [], plan: { frames: {}, crowd_fills: [] } },
  context: { tracks: [], roles: undefined },
});

let n = 0;
const id = () => `e_${(n += 1)}`;

/** Runs actions in order, collecting every edit sent. */
function run(state: ReviewState, ...actions: Action[]) {
  const sent = [];
  let s = state;
  for (const a of actions) {
    const r = step(s, a);
    s = r.state;
    if (r.send) sent.push(r.send);
  }
  return { state: s, sent };
}

/** The server's answer to an edit, built from the client's state (what WP3 would return). */
function ackItems(state: ReviewState, base: Item[]): Item[] {
  return base
    .filter((i) => state.items[i.item_id] && state.items[i.item_id]?.merged_into === null)
    .map((i) => {
      const s = state.items[i.item_id]!;
      const merged = Object.values(state.items).filter((m) => m.merged_into === i.item_id).flatMap((m) => m.track_ids);
      return { ...i, decision: s.decision, decided_by: s.decided_by, removed_by_creator: s.removed, track_ids: [...s.track_ids, ...merged] };
    });
}
const ack = (state: ReviewState, editId: string, base: Item[], over: Partial<ServerState> = {}): Action => ({
  type: "SERVER_ACK",
  edit_id: editId,
  server: { items: ackItems(state, base), plan: state.server.plan, status: state.status, has_render: state.has_render, spots: [], ...over },
});

describe("review reducer (UI-SPEC §10.5)", () => {
  it("R1: keep on a screen asks for the confirm first, sending nothing", () => {
    const r = run(fromJob(cafeMock), { type: "KEEP", id: "i_6", edit_id: id() });
    expect(r.state.confirm).toEqual({ item_id: "i_6" });
    expect(r.sent).toHaveLength(0);
    expect(r.state.items.i_6?.decision).toBe("needs_you");
  });

  it("R2: confirming the keep sends one edit and toasts", () => {
    const r = run(fromJob(cafeMock), { type: "KEEP", id: "i_6", edit_id: "e_r2" }, { type: "CONFIRM_KEEP", edit_id: "e_r2" });
    expect(r.state.items.i_6).toMatchObject({ decision: "keep", decided_by: "creator" });
    expect(r.state.confirm).toBeNull();
    expect(r.sent).toEqual([{ type: "keep", edit_id: "e_r2", item_id: "i_6" }]);
    expect(r.state.toast).toEqual({ kind: "edit", text: "Screen 3 will be kept clear.", edit_id: "e_r2" });
  });

  it("R2b: cancelling the confirm changes nothing", () => {
    const r = run(fromJob(cafeMock), { type: "KEEP", id: "i_6", edit_id: id() }, { type: "CANCEL_CONFIRM" });
    expect(r.state.items.i_6?.decision).toBe("needs_you");
    expect(r.state.confirm).toBeNull();
    expect(r.sent).toHaveLength(0);
  });

  it("R2c/R2d: a plate confirms too, then keeps", () => {
    const s = fromJob(heroMock);
    const r1 = run(s, { type: "KEEP", id: "i_3", edit_id: "e_p" });
    expect(r1.state.confirm).toEqual({ item_id: "i_3" });
    expect(r1.sent).toHaveLength(0);
    const r2 = run(r1.state, { type: "CONFIRM_KEEP", edit_id: "e_p" });
    expect(r2.state.items.i_3).toMatchObject({ decision: "keep", decided_by: "creator" });
    expect(r2.state.toast?.text).toBe("Plate 1 will be kept clear.");
    expect(r2.sent).toHaveLength(1);
  });

  it("R3: a locked child can't be kept, and nothing is sent", () => {
    const s = fromFixture();
    const r = run(s, { type: "KEEP", id: "i_2", edit_id: id() });
    expect(r.state).toBe(s);
    expect(r.sent).toHaveLength(0);
  });

  it("R4/R5: hide, acknowledge, undo sends an undo with its own edit_id", () => {
    const r4 = run(fromFixture(), { type: "HIDE", id: "i_4", edit_id: "e_r4" });
    expect(r4.state.items.i_4).toMatchObject({ decision: "hide", decided_by: "creator" });
    expect(r4.state.toast?.text).toBe("Face 6 will be hidden.");
    const acked = { ...r4.state, pending: {} };
    const r5 = run(acked, { type: "UNDO", target: "e_r4", edit_id: "e_r5" });
    expect(r5.state.items.i_4).toMatchObject({ decision: "needs_you", decided_by: "model" });
    expect(r5.state.toast).toEqual({ kind: "undone", text: "Undone." });
    expect(r5.sent).toEqual([{ type: "undo", edit_id: "e_r5", reverts: "e_r4" }]);
    expect(r5.state.undo).toHaveLength(0);
  });

  it("R6: a double-click sends one request", () => {
    const r = run(fromFixture(), { type: "HIDE", id: "i_1", edit_id: "a" }, { type: "HIDE", id: "i_1", edit_id: "b" });
    expect(r.sent).toHaveLength(1);
  });

  it("R7: keeping a needs-you person needs no confirm", () => {
    const r = run(fromFixture(), { type: "KEEP", id: "i_4", edit_id: "e7" });
    expect(r.state.items.i_4).toMatchObject({ decision: "keep", decided_by: "creator" });
    expect(r.state.toast?.text).toBe("Face 6 will be kept clear.");
    expect(r.sent).toHaveLength(1);
  });

  it("R8/R8b/R9: merge a re-entry into the kept guest, hide the guest, undo the merge", () => {
    const s = fromJob(reentryMock);
    expect(s.items.i_9?.reentry_target).toBe("i_1");
    const before = visibleItems(s).length;
    const r8 = run(s, { type: "MERGE", src: "i_9", dst: "i_1", edit_id: "e_r8" });
    expect(r8.sent).toEqual([{ type: "merge", edit_id: "e_r8", item_id: "i_9", into: "i_1" }]);
    expect(r8.state.items.i_9?.merged_into).toBe("i_1");
    expect(visibleItems(r8.state)).toHaveLength(before - 1);
    expect(tracksShown(r8.state, "i_1")).toContain("face:9");
    expect(r8.state.toast?.text).toBe("Face 9 merged into Face 2. They'll be kept clear like Face 2.");
    expect(effectiveDecision(r8.state, "i_9")).toBe("keep");

    const base = job(reentryMock).items;
    const acked = run(r8.state, ack(r8.state, "e_r8", base)).state;
    expect(acked.items.i_9).toBeUndefined();
    expect(acked.items.i_1?.track_ids).toEqual(["face:2", "person:1", "face:9"]);
    expect(acked.items.i_1?.reentry_target).toBeNull();

    const r8b = run(acked, { type: "HIDE", id: "i_1", edit_id: "e_r8b" });
    expect(r8b.state.items.i_1?.decision).toBe("hide");
    expect(r8b.state.toast?.text).toBe("Face 2 will be hidden.");

    const r9 = run(acked, { type: "UNDO", target: "e_r8", edit_id: "e_r9" });
    expect(r9.state.items.i_9).toMatchObject({ merged_into: null, reentry_target: "i_1", decision: "hide" });
    expect(r9.state.items.i_1?.track_ids).toEqual(["face:2", "person:1"]);
    expect(visibleItems(r9.state)).toHaveLength(before);
    expect(r9.sent).toEqual([{ type: "undo", edit_id: "e_r9", reverts: "e_r8" }]);
  });

  it.each([
    ["R9b: re-entry of a hidden bystander", "i_8", "i_1"],
    ["R10: child target", "i_9", "i_2"],
    ["R11: child source", "i_2", "i_1"],
    ["R12: target not kept", "i_9", "i_4"],
    ["R12b: target kept but not a participant", "i_9", "i_7"],
    ["self merge", "i_9", "i_9"],
  ])("%s is rejected with no request", (_name, src, dst) => {
    const s = fromFixture();
    const r = run(s, { type: "MERGE", src, dst, edit_id: id() });
    expect(r.state).toBe(s);
    expect(r.sent).toHaveLength(0);
  });

  it("R12c: a merge with an edit pending on the source is rejected", () => {
    const pending = run(fromFixture(), { type: "HIDE", id: "i_1", edit_id: "p" }, { type: "KEEP", id: "i_1", edit_id: "q" });
    // i_1 is pending (its hide), so the keep and a merge touching it both send nothing more.
    expect(pending.sent).toHaveLength(1);
    const r = run(pending.state, { type: "MERGE", src: "i_9", dst: "i_1", edit_id: id() });
    expect(r.sent).toHaveLength(0);
  });

  it("R13/R13b: remove a kept participant, then keep them clear again", () => {
    const r13 = run(fromFixture(), { type: "REMOVE_PERSON", id: "i_1", edit_id: "e13" });
    expect(r13.state.items.i_1).toMatchObject({ decision: "hide", removed: true });
    expect(r13.state.toast?.text).toBe("Face 2 will be fully covered wherever they appear.");
    const acked = { ...r13.state, pending: {} };
    const r13b = run(acked, { type: "KEEP", id: "i_1", edit_id: "e13b" });
    expect(r13b.state.items.i_1).toMatchObject({ decision: "keep", decided_by: "creator", removed: false });
    expect(r13b.state.confirm).toBeNull();
    expect(r13b.state.toast?.text).toBe("Face 2 will be kept clear. They're no longer removed.");
  });

  it("R14/R14b: a rejected edit reverts, and Try again resends the same edit_id", () => {
    const r14 = run(fromFixture(), { type: "HIDE", id: "i_4", edit_id: "e14" }, { type: "SERVER_REJECT", edit_id: "e14" });
    expect(r14.state.items.i_4?.decision).toBe("needs_you");
    expect(r14.state.pending).toEqual({});
    expect(r14.state.toast).toEqual({ kind: "failed", text: "That change didn't save. Check your connection and try again.", edit_id: "e14" });
    const r14b = run(r14.state, { type: "RETRY", edit_id: "e14" });
    expect(r14b.state.items.i_4?.decision).toBe("hide");
    expect(r14b.sent).toEqual([{ type: "hide", edit_id: "e14", item_id: "i_4" }]);
    expect(r14b.state.pending.e14).toBeDefined();
    expect(r14b.state.undo.at(-1)?.edit.edit_id).toBe("e14");
  });

  it("a rate-limited edit gets the rate-limit toast", () => {
    const r = run(fromFixture(), { type: "HIDE", id: "i_4", edit_id: "e" }, { type: "SERVER_REJECT", edit_id: "e", rateLimited: true });
    expect(r.state.toast?.text).toBe("Too many tries in a short time. Wait a minute and try again.");
  });

  it("R15: an ack replaces items and plan with the server's", () => {
    const s = fromJob(heroMock);
    const r = run(s, { type: "HIDE", id: "i_4", edit_id: "e15" });
    const plan = { frames: { "9": [{ item_id: "i_4", shape: "box" as const, box: [1, 2, 3, 4] as [number, number, number, number], mask: null, style: "solid" as const, grid: null }] }, crowd_fills: [] };
    const acked = run(r.state, ack(r.state, "e15", job(heroMock).items, { plan })).state;
    expect(acked.server.plan).toBe(plan);
    expect(acked.items.i_4?.decision).toBe("hide");
    expect(acked.pending).toEqual({});
  });

  it("an ack keeps other still-pending optimistic edits applied", () => {
    const s = fromJob(heroMock);
    const r = run(s, { type: "HIDE", id: "i_4", edit_id: "a" }, { type: "HIDE", id: "i_1", edit_id: "b" });
    // The server acknowledges only the first edit.
    const items = job(heroMock).items.map((i) => (i.item_id === "i_4" ? { ...i, decision: "hide" as const, decided_by: "creator" as const } : i));
    const acked = run(r.state, { type: "SERVER_ACK", edit_id: "a", server: { items, plan: s.server.plan, status: "review", has_render: false, spots: [] } }).state;
    expect(acked.items.i_1?.decision).toBe("hide");
    expect(acked.pending.b).toBeDefined();
  });

  it("R16: every mutating action is rejected while rendering", () => {
    const s = { ...fromFixture(), status: "rendering" as const };
    for (const a of [
      { type: "HIDE", id: "i_4", edit_id: "x" },
      { type: "KEEP", id: "i_4", edit_id: "x" },
      { type: "MERGE", src: "i_9", dst: "i_1", edit_id: "x" },
      { type: "REMOVE_PERSON", id: "i_1", edit_id: "x" },
    ] as Action[]) {
      const r = step(s, a);
      expect(r.state).toBe(s);
      expect(r.send).toBeNull();
    }
  });

  it("R18: an edit made at ?view=review moves the bar to 'edited after rendering'", () => {
    const s = { ...fromJob(heroMock), status: "done" as const, has_render: true };
    expect(selectBar(s, true)).toMatchObject({ row: 5 });
    const r = run(s, { type: "HIDE", id: "i_4", edit_id: "e18" });
    expect(selectBar(r.state, true)).toMatchObject({ row: 3 });
    const acked = run(r.state, ack(r.state, "e18", job(heroMock).items, { status: "review", has_render: true })).state;
    expect(selectBar(acked, true)).toMatchObject({ row: 6 });
  });

  it("R19/R20/R21: cover an unfixed spot, refuse a double-click, undo it", () => {
    const s = fromJob(unresolvedMock);
    expect(uncoveredSpots(s)).toEqual(["s1"]);
    expect(spotLabels(s.spots)).toEqual({ s1: "U1" });
    expect(selectBar(s, true)).toMatchObject({ row: 4, count: 1 });

    const r19 = run(s, { type: "COVER_SPOT", spot_id: "s1", edit_id: "e19" });
    expect(r19.sent).toEqual([{ type: "cover_spot", edit_id: "e19", spot_id: "s1" }]);
    expect(uncoveredSpots(r19.state)).toEqual([]);
    expect(Object.values(r19.state.items).find((i) => i.spot_id === "s1")?.label).toBe("A?");
    expect(selectBar(r19.state, true)).toMatchObject({ row: 3 });
    expect(r19.state.toast?.text).toBe("U1 will be covered.");

    expect(run(r19.state, { type: "COVER_SPOT", spot_id: "s1", edit_id: "e20" }).sent).toHaveLength(0);

    const server = coverAck.body;
    const acked = run(r19.state, {
      type: "SERVER_ACK",
      edit_id: "e19",
      server: { items: job({ ...unresolvedMock, items: server.items }).items, plan: s.server.plan, status: "review", has_render: true, spots: job({ ...unresolvedMock, audit: { ...unresolvedMock.audit, spots: server.audit.spots } }).audit!.spots },
    }).state;
    expect(acked.items.p_1?.label).toBe("A1");
    expect(acked.spots.s1?.covered_by).toBe("p_1");
    expect(selectBar(acked, true)).toMatchObject({ row: 6 });

    const r21 = run(acked, { type: "UNDO", target: "e19", edit_id: "e21" });
    expect(r21.sent).toEqual([{ type: "undo", edit_id: "e21", reverts: "e19" }]);
    expect(uncoveredSpots(r21.state)).toEqual(["s1"]);
    expect(r21.state.items.p_1).toBeUndefined();
    expect(selectBar({ ...r21.state, pending: {} }, true)).toMatchObject({ row: 4 });
  });

  it("R22: an audit_failed job is read-only with the audit bar", () => {
    const s = fromJob(auditFailedLeakMock);
    expect(selectBar(s, false)).toMatchObject({ row: 2 });
  });

  it("R23/R24: in needs_you every action is rejected with no request", () => {
    for (const mock of [jobCapMock, auditFailedLeakMock]) {
      const seeded: ReviewState = { ...fromJob(mock), undo: [{ edit: { type: "hide", edit_id: "old", item_id: "i_4" }, prev: { items: {}, spots: {} } }] };
      const r = run(
        seeded,
        { type: "HIDE", id: "i_1", edit_id: "a" },
        { type: "HIDE", id: "i_4", edit_id: "b" },
        { type: "MERGE", src: "i_4", dst: "i_1", edit_id: "c" },
        { type: "REMOVE_PERSON", id: "i_1", edit_id: "d" },
        { type: "COVER_SPOT", spot_id: "s1", edit_id: "e" },
        { type: "UNDO", target: "old", edit_id: "f" },
      );
      expect(r.sent).toHaveLength(0);
      expect(selectBar(r.state, false)).toMatchObject({ row: 2 });
    }
  });

  it("R25/R32: a daily-cap refusal survives acks and polls, and expires at its time", () => {
    const refused = run(fromJob(heroMock), { type: "ACTION_REFUSE", button: "render", code: "daily_cap", until: 1000 }).state;
    expect(refused.refusal).toEqual({ code: "daily_cap", until: 1000 });
    expect(selectBar(refused, false)).toMatchObject({ row: 0 });
    const r = run(refused, { type: "HIDE", id: "i_4", edit_id: "e25" });
    const acked = run(r.state, ack(r.state, "e25", job(heroMock).items, { status: "review" })).state;
    const polled = run(acked, { type: "SYNC", server: serverOf(job(heroMock)) }).state;
    expect(polled.refusal).toEqual({ code: "daily_cap", until: 1000 });
    expect(run(polled, { type: "REFUSAL_EXPIRED", now: 999 }).state.refusal).not.toBeNull();
    const expired = run(polled, { type: "REFUSAL_EXPIRED", now: 1000 }).state;
    expect(expired.refusal).toBeNull();
    expect(selectBar(expired, false).row).toBeGreaterThan(0);
  });

  it("R26/R33: a code-cap note shows until that button's next ack", () => {
    const capped = run(fromFixture(), { type: "ACTION_CAP", button: "render", auditBudgetCause: null }).state;
    expect(capped.capNote).toEqual({ button: "render" });
    expect(capped.refusal).toBeNull();
    expect(selectBar(capped, false).row).not.toBe(0);
    const audited = run(capped, { type: "ACTION_ACK", button: "audit", status: "rendering" }).state;
    expect(audited.capNote).toEqual({ button: "render" });
    const rendered = run(capped, { type: "ACTION_ACK", button: "render", status: "rendering" }).state;
    expect(rendered.capNote).toBeNull();
    expect(selectBar(rendered, false)).toMatchObject({ row: 1 });
  });

  it("no cap note in needs_you when the audit budget cause is already code_cap", () => {
    const s = { ...fromFixture(), status: "needs_you" as const };
    expect(run(s, { type: "ACTION_CAP", button: "audit", auditBudgetCause: "code_cap" }).state.capNote).toBeNull();
  });

  it("R29: two undos step back one edit at a time", () => {
    const s = fromFixture();
    const a = run(s, { type: "HIDE", id: "i_4", edit_id: "h4" }).state;
    const b = run({ ...a, pending: {} }, { type: "HIDE", id: "i_1", edit_id: "h1" }).state;
    const u1 = run({ ...b, pending: {} }, { type: "UNDO", target: "h1", edit_id: "u1" });
    expect(u1.state.items.i_1?.decision).toBe("keep");
    expect(u1.sent[0]).toEqual({ type: "undo", edit_id: "u1", reverts: "h1" });
    const u2 = run({ ...u1.state, pending: {} }, { type: "UNDO", target: "h4", edit_id: "u2" });
    expect(u2.state.items.i_4?.decision).toBe("needs_you");
    expect(u2.sent[0]).toEqual({ type: "undo", edit_id: "u2", reverts: "h4" });
    expect(u2.state.undo).toEqual([]);
  });

  it("R30: undo replaces the edit toast with 'Undone.'", () => {
    const a = run(fromFixture(), { type: "HIDE", id: "i_4", edit_id: "h" }).state;
    const u = run({ ...a, pending: {} }, { type: "UNDO", target: "h", edit_id: "u" }).state;
    expect(u.toast).toEqual({ kind: "undone", text: "Undone." });
    expect(u.undo).toEqual([]);
  });

  it("R31: after a rejected edit, undo has nothing to send", () => {
    const r = run(fromFixture(), { type: "HIDE", id: "i_4", edit_id: "h" }, { type: "SERVER_REJECT", edit_id: "h" }, { type: "UNDO", target: "h", edit_id: "u" });
    expect(r.state.items.i_4?.decision).toBe("needs_you");
    expect(r.state.undo).toEqual([]);
    expect(r.sent).toHaveLength(1);
  });

  it("a rejected undo puts the edit back at its place and re-applies it", () => {
    const a = run(fromFixture(), { type: "HIDE", id: "i_4", edit_id: "h4" }).state;
    const b = run({ ...a, pending: {} }, { type: "HIDE", id: "i_1", edit_id: "h1" }).state;
    const u = run({ ...b, pending: {} }, { type: "UNDO", target: "h4", edit_id: "u" }, { type: "SERVER_REJECT", edit_id: "u" }).state;
    expect(u.items.i_4?.decision).toBe("hide");
    expect(u.undo.map((e) => e.edit.edit_id)).toEqual(["h4", "h1"]);
  });

  it("an undo of a pending edit sends nothing", () => {
    const a = run(fromFixture(), { type: "HIDE", id: "i_4", edit_id: "h" }).state;
    expect(run(a, { type: "UNDO", target: "h", edit_id: "u" }).sent).toHaveLength(0);
  });

  it("bar rows 7 and 8 count only visible items that need you", () => {
    expect(selectBar(fromFixture(), false)).toMatchObject({ row: 7, count: 1 });
    const kept = run(fromFixture(), { type: "KEEP", id: "i_4", edit_id: "k" }).state;
    expect(selectBar({ ...kept, pending: {} }, false)).toMatchObject({ row: 8 });
  });

  it("property: any sequence of actions keeps the invariants", () => {
    const ids = ["i_1", "i_2", "i_3", "i_4", "i_5", "i_7", "i_8", "i_9"];
    const actionArb = fc.oneof(
      fc.record({ type: fc.constantFrom("KEEP", "HIDE", "REMOVE_PERSON"), id: fc.constantFrom(...ids) }),
      fc.record({ type: fc.constant("MERGE"), src: fc.constantFrom(...ids), dst: fc.constantFrom(...ids) }),
      fc.record({ type: fc.constantFrom("CONFIRM_KEEP", "CANCEL_CONFIRM") }),
      fc.record({ type: fc.constant("ACK") }),
      fc.record({ type: fc.constant("REJECT") }),
      fc.record({ type: fc.constant("UNDO_TOP") }),
    );
    fc.assert(
      fc.property(fc.array(actionArb, { maxLength: 40 }), (script) => {
        let s = fromFixture();
        let k = 0;
        const sentIds = new Set<string>();
        for (const raw of script) {
          const editId = `x${(k += 1)}`;
          let a: Action | null = null;
          const pendingIds = Object.keys(s.pending);
          if (raw.type === "ACK") {
            const first = pendingIds[0];
            if (first) s = { ...s, pending: Object.fromEntries(Object.entries(s.pending).filter(([key]) => key !== first)) };
            continue;
          }
          if (raw.type === "REJECT") {
            const first = pendingIds[0];
            if (first) a = { type: "SERVER_REJECT", edit_id: first };
          } else if (raw.type === "UNDO_TOP") {
            const top = s.undo.at(-1);
            if (top) a = { type: "UNDO", target: top.edit.edit_id, edit_id: editId };
          } else {
            a = { ...(raw as object), edit_id: editId } as Action;
          }
          if (!a) continue;
          const r = step(s, a);
          s = r.state;
          if (r.send) {
            // every request is unique, and a locked child is never sent a keep
            if (sentIds.has(r.send.edit_id) && a.type !== "RETRY") return false;
            sentIds.add(r.send.edit_id);
            if (r.send.type === "keep" && r.send.item_id === "i_2") return false;
          }
          // children stay hidden; no item is merged into a merged item; every pending edit touches distinct items
          if (effectiveDecision(s, "i_2") !== "hide") return false;
          for (const item of Object.values(s.items)) {
            if (item.merged_into && s.items[item.merged_into]?.merged_into) return false;
          }
          const touched = Object.values(s.pending).flatMap((p) => p.touches);
          if (new Set(touched).size !== touched.length) return false;
        }
        return true;
      }),
      { numRuns: 1500 },
    );
  });
});
