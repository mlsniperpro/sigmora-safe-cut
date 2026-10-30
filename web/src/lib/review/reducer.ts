/**
 * The review reducer (UI-SPEC §10.5). Pure: `step(state, action)` returns the
 * next state and, at most, one edit to send. The page owns the network.
 */
import type { Box, DecidedBy, Decision, Item, JobStatus, Kind, Plan, ReviewEdit, Role, Roles, Spot, Track } from "../contracts";
import { isObjectKind, itemLabel } from "../labels";

export interface ItemState {
  label: string;
  track_ids: string[];
  decision: Decision;
  decided_by: DecidedBy;
  locked: boolean;
  kind: Kind;
  role: Role | null;
  reentry_target: string | null;
  merged_into: string | null;
  removed: boolean;
  /** Set on the optimistic item a pending `cover_spot` adds. */
  spot_id?: string | null;
  audit_label?: string | null;
}

export interface SpotState {
  first: number;
  last: number;
  boxes: Record<string, Box>;
  covered_by: string | null;
}

/** Item states before an edit, enough to put them back (`undefined` = the item didn't exist). */
export interface Snapshot {
  items: Record<string, ItemState | undefined>;
  spots: Record<string, string | null>;
}

export type EditAction =
  | { type: "KEEP"; id: string; edit_id: string }
  | { type: "CONFIRM_KEEP"; edit_id: string }
  | { type: "HIDE"; id: string; edit_id: string }
  | { type: "MERGE"; src: string; dst: string; edit_id: string }
  | { type: "REMOVE_PERSON"; id: string; edit_id: string }
  | { type: "COVER_SPOT"; spot_id: string; edit_id: string };

export type ActionButton = "render" | "audit";

export type Action =
  | EditAction
  | { type: "CANCEL_CONFIRM" }
  | { type: "UNDO"; target: string; edit_id: string }
  | { type: "SERVER_ACK"; edit_id: string; server: ServerState }
  | { type: "SERVER_REJECT"; edit_id: string; rateLimited?: boolean }
  | { type: "RETRY"; edit_id: string }
  | { type: "SYNC"; server: ServerState }
  | { type: "ACTION_ACK"; button: ActionButton; status: JobStatus }
  | { type: "ACTION_REFUSE"; button: ActionButton; code: string; until: number | null }
  | { type: "ACTION_CAP"; button: ActionButton; auditBudgetCause: string | null }
  | { type: "REFUSAL_EXPIRED"; now: number }
  | { type: "DISMISS_TOAST" };

export interface UndoEntry {
  edit: ReviewEdit;
  prev: Snapshot;
}

export interface PendingEdit {
  edit: ReviewEdit;
  prev: Snapshot;
  /** The action that made it (normal edits), so a rejected one can be retried. */
  action: EditAction | null;
  touches: string[];
  /** For an `undo` edit: the entry it took off the stack, and where it was. */
  undone?: { entry: UndoEntry; index: number };
}

export type Toast =
  | { kind: "edit"; text: string; edit_id: string }
  | { kind: "undone"; text: string }
  | { kind: "failed"; text: string; edit_id: string };

/** The server's view of the job, as the reducer needs it. */
export interface ServerState {
  items: Item[];
  plan: Plan;
  status: JobStatus;
  has_render: boolean;
  spots: Spot[];
}

export interface ReviewContext {
  tracks: readonly Track[];
  roles: Roles | undefined;
}

export interface ReviewState {
  items: Record<string, ItemState>;
  confirm: { item_id: string } | null;
  pending: Record<string, PendingEdit>;
  undo: UndoEntry[];
  status: JobStatus;
  has_render: boolean;
  spots: Record<string, SpotState>;
  refusal: { code: string; until: number | null } | null;
  capNote: { button: ActionButton } | null;
  toast: Toast | null;
  /** Rejected edits kept for the failed toast's [Try again]. */
  rejected: Record<string, { action: EditAction | null; edit: ReviewEdit; index?: number; entry?: UndoEntry }>;
  /** The server's items and plan, for everything the reducer doesn't model (reason, evidence…). */
  server: { items: Item[]; plan: Plan };
  context: ReviewContext;
}

export interface Step {
  state: ReviewState;
  send: ReviewEdit | null;
}

const EDIT_FAILED = "That change didn't save. Check your connection and try again.";
const RATE_LIMITED = "Too many tries in a short time. Wait a minute and try again.";

// ------------------------------------------------------------------ building state from the server

function trackOwners(items: readonly Item[]): Map<string, string> {
  const owners = new Map<string, string>();
  for (const item of items) for (const t of item.track_ids) owners.set(t, item.item_id);
  return owners;
}

export function buildItems(items: readonly Item[], context: ReviewContext): Record<string, ItemState> {
  const owners = trackOwners(items);
  const reentryOf = new Map(context.tracks.map((t) => [t.track_id, t.reentry_of]));
  const roleOf = new Map((context.roles?.tracks ?? []).map((t) => [t.track_id, t.role]));
  const out: Record<string, ItemState> = {};
  for (const item of items) {
    const primary = item.track_ids.find((t) => t.startsWith("face:")) ?? item.track_ids[0];
    let reentry: string | null = null;
    for (const t of item.track_ids) {
      const earlier = reentryOf.get(t);
      const owner = earlier ? owners.get(earlier) : undefined;
      if (owner && owner !== item.item_id) {
        reentry = owner;
        break;
      }
    }
    out[item.item_id] = {
      label: itemLabel(item),
      track_ids: [...item.track_ids],
      decision: item.decision,
      decided_by: item.decided_by,
      locked: item.locked,
      kind: item.kind,
      role: item.kind === "person" || item.kind === "child" ? (primary ? roleOf.get(primary) ?? null : null) : null,
      reentry_target: reentry,
      merged_into: null,
      removed: item.removed_by_creator,
      spot_id: item.spot_id ?? null,
      audit_label: item.audit_label ?? null,
    };
  }
  return out;
}

function buildSpots(spots: readonly Spot[]): Record<string, SpotState> {
  return Object.fromEntries(spots.map((s) => [s.spot_id, { first: s.first, last: s.last, boxes: { ...s.boxes }, covered_by: s.covered_by }]));
}

export function initialState(server: ServerState, context: ReviewContext): ReviewState {
  return {
    items: buildItems(server.items, context),
    confirm: null,
    pending: {},
    undo: [],
    status: server.status,
    has_render: server.has_render,
    spots: buildSpots(server.spots),
    refusal: null,
    capNote: null,
    toast: null,
    rejected: {},
    server: { items: server.items, plan: server.plan },
    context,
  };
}

// ------------------------------------------------------------------ derived

export function isReadOnly(state: Pick<ReviewState, "status">): boolean {
  return state.status === "rendering" || state.status === "needs_you";
}

/** The decision that applies to an item: its merge target's when it has one. */
export function effectiveDecision(state: Pick<ReviewState, "items">, id: string): Decision | null {
  let item = state.items[id];
  const seen = new Set<string>();
  while (item?.merged_into && !seen.has(item.merged_into)) {
    seen.add(item.merged_into);
    item = state.items[item.merged_into];
  }
  return item?.decision ?? null;
}

/** Items shown in the columns (merged items aren't). */
export function visibleItems(state: Pick<ReviewState, "items">): Array<[string, ItemState]> {
  return Object.entries(state.items).filter(([, item]) => item.merged_into === null);
}

/** Track IDs shown under an item: its own plus every item merged into it. */
export function tracksShown(state: Pick<ReviewState, "items">, id: string): string[] {
  const own = state.items[id]?.track_ids ?? [];
  const merged = Object.values(state.items)
    .filter((i) => i.merged_into === id)
    .flatMap((i) => i.track_ids);
  return [...own, ...merged.filter((t) => !own.includes(t))];
}

/** `U1, U2, …` by first frame, over every spot in the audit (labels don't shift when one is covered). */
export function spotLabels(spots: Record<string, Pick<SpotState, "first">>): Record<string, string> {
  const ordered = Object.entries(spots).sort(([a, x], [b, y]) => x.first - y.first || a.localeCompare(b));
  return Object.fromEntries(ordered.map(([id], i) => [id, `U${i + 1}`]));
}

export function uncoveredSpots(state: Pick<ReviewState, "spots">): string[] {
  return Object.entries(state.spots)
    .filter(([, s]) => s.covered_by === null)
    .map(([id]) => id);
}

function pendingTouches(state: ReviewState): Set<string> {
  return new Set(Object.values(state.pending).flatMap((p) => p.touches));
}

// ------------------------------------------------------------------ edits

function snapshot(state: ReviewState, ids: readonly string[], spotIds: readonly string[] = []): Snapshot {
  const items: Record<string, ItemState | undefined> = {};
  for (const id of ids) {
    const item = state.items[id];
    items[id] = item ? { ...item, track_ids: [...item.track_ids] } : undefined;
  }
  const spots: Record<string, string | null> = {};
  for (const id of spotIds) spots[id] = state.spots[id]?.covered_by ?? null;
  return { items, spots };
}

function restore(state: ReviewState, snap: Snapshot): ReviewState {
  const items = { ...state.items };
  for (const [id, item] of Object.entries(snap.items)) {
    if (item === undefined) delete items[id];
    else items[id] = { ...item, track_ids: [...item.track_ids] };
  }
  const spots = { ...state.spots };
  for (const [id, coveredBy] of Object.entries(snap.spots)) {
    const spot = spots[id];
    if (spot) spots[id] = { ...spot, covered_by: coveredBy };
  }
  return { ...state, items, spots };
}

const pendingCoverId = (editId: string) => `pending:${editId}`;

/** Checks an edit action's guards and preconditions; null when it may run. */
function blocked(state: ReviewState, action: EditAction): true | null {
  if (isReadOnly(state)) return true;
  const busy = pendingTouches(state);
  switch (action.type) {
    case "KEEP":
    case "HIDE":
    case "REMOVE_PERSON": {
      const item = state.items[action.id];
      if (!item || busy.has(action.id) || item.merged_into !== null) return true;
      if (action.type === "KEEP") return item.locked || item.decision === "keep" ? true : null;
      if (action.type === "HIDE") return item.decision === "hide" ? true : null;
      return (item.kind === "person" || item.kind === "child") && item.track_ids.length > 0 ? null : true;
    }
    case "CONFIRM_KEEP": {
      const id = state.confirm?.item_id;
      if (!id) return true;
      const item = state.items[id];
      return !item || busy.has(id) || item.merged_into !== null || item.locked || item.decision === "keep" ? true : null;
    }
    case "MERGE": {
      const src = state.items[action.src];
      const dst = state.items[action.dst];
      if (!src || !dst || action.src === action.dst) return true;
      if (busy.has(action.src) || busy.has(action.dst)) return true;
      const target = src.reentry_target ? state.items[src.reentry_target] : undefined;
      const keptParticipant = (i: ItemState | undefined) => !!i && i.kind === "person" && i.decision === "keep" && i.role === "participant";
      const ok =
        src.kind === "person" &&
        !src.locked &&
        src.merged_into === null &&
        keptParticipant(target) &&
        keptParticipant(dst) &&
        !dst.locked &&
        dst.merged_into === null;
      return ok ? null : true;
    }
    case "COVER_SPOT": {
      const spot = state.spots[action.spot_id];
      if (!spot || spot.covered_by !== null || Object.keys(state.pending).length > 0) return true;
      return null;
    }
  }
}

/** Applies an edit action's optimistic effect; returns the edit to send and what it touched. */
function applyEdit(state: ReviewState, action: EditAction): { state: ReviewState; edit: ReviewEdit; touches: string[]; prev: Snapshot; toast: string } {
  const edit_id = action.edit_id;
  switch (action.type) {
    case "KEEP":
    case "CONFIRM_KEEP": {
      const id = action.type === "KEEP" ? action.id : (state.confirm?.item_id as string);
      const item = state.items[id] as ItemState;
      const prev = snapshot(state, [id]);
      const wasRemoved = item.removed;
      const next = { ...state, confirm: null, items: { ...state.items, [id]: { ...item, decision: "keep" as const, decided_by: "creator" as const, removed: false } } };
      const toast = wasRemoved ? `${item.label} will be kept clear. They're no longer removed.` : `${item.label} will be kept clear.`;
      return { state: next, edit: { type: "keep", edit_id, item_id: id }, touches: [id], prev, toast };
    }
    case "HIDE": {
      const item = state.items[action.id] as ItemState;
      const prev = snapshot(state, [action.id]);
      const next = { ...state, items: { ...state.items, [action.id]: { ...item, decision: "hide" as const, decided_by: "creator" as const } } };
      return { state: next, edit: { type: "hide", edit_id, item_id: action.id }, touches: [action.id], prev, toast: `${item.label} will be hidden.` };
    }
    case "REMOVE_PERSON": {
      const item = state.items[action.id] as ItemState;
      const prev = snapshot(state, [action.id]);
      const next = { ...state, items: { ...state.items, [action.id]: { ...item, decision: "hide" as const, decided_by: "creator" as const, removed: true } } };
      return { state: next, edit: { type: "remove_person", edit_id, item_id: action.id }, touches: [action.id], prev, toast: `${item.label} will be fully covered wherever they appear.` };
    }
    case "MERGE": {
      const src = state.items[action.src] as ItemState;
      const dst = state.items[action.dst] as ItemState;
      const prev = snapshot(state, [action.src, action.dst]);
      const next = { ...state, items: { ...state.items, [action.src]: { ...src, merged_into: action.dst, decided_by: "creator" as const } } };
      return {
        state: next,
        edit: { type: "merge", edit_id, item_id: action.src, into: action.dst },
        touches: [action.src, action.dst],
        prev,
        toast: `${src.label} merged into ${dst.label}. They'll be kept clear like ${dst.label}.`,
      };
    }
    case "COVER_SPOT": {
      const spot = state.spots[action.spot_id] as SpotState;
      const label = spotLabels(state.spots)[action.spot_id] ?? action.spot_id;
      const itemId = pendingCoverId(edit_id);
      const prev = snapshot(state, [itemId], [action.spot_id]);
      const added: ItemState = {
        label: "A?",
        track_ids: [],
        decision: "hide",
        decided_by: "policy",
        locked: true,
        kind: "person",
        role: null,
        reentry_target: null,
        merged_into: null,
        removed: false,
        spot_id: action.spot_id,
        audit_label: null,
      };
      const next = {
        ...state,
        items: { ...state.items, [itemId]: added },
        spots: { ...state.spots, [action.spot_id]: { ...spot, covered_by: itemId } },
      };
      return { state: next, edit: { type: "cover_spot", edit_id, spot_id: action.spot_id }, touches: [itemId, `spot:${action.spot_id}`], prev, toast: `${label} will be covered.` };
    }
  }
}

function runEdit(state: ReviewState, action: EditAction): Step {
  if (blocked(state, action)) return { state, send: null };
  if (action.type === "KEEP") {
    const item = state.items[action.id] as ItemState;
    if (isObjectKind(item.kind)) return { state: { ...state, confirm: { item_id: action.id } }, send: null };
  }
  const applied = applyEdit(state, action);
  const entry: UndoEntry = { edit: applied.edit, prev: applied.prev };
  const rejected = { ...applied.state.rejected };
  delete rejected[applied.edit.edit_id];
  return {
    state: {
      ...applied.state,
      pending: { ...applied.state.pending, [applied.edit.edit_id]: { edit: applied.edit, prev: applied.prev, action, touches: applied.touches } },
      undo: [...applied.state.undo, entry],
      toast: { kind: "edit", text: applied.toast, edit_id: applied.edit.edit_id },
      rejected,
    },
    send: applied.edit,
  };
}

function reapplyPending(state: ReviewState, pending: Record<string, PendingEdit>): ReviewState {
  let next = state;
  for (const p of Object.values(pending)) {
    if (p.action) {
      const before = next.confirm;
      const temp = p.action.type === "CONFIRM_KEEP" ? { ...next, confirm: { item_id: p.touches[0] as string } } : next;
      next = { ...applyEdit(temp, p.action).state, confirm: before };
    } else if (p.undone) {
      next = restore(next, p.undone.entry.prev);
    }
  }
  return next;
}

// ------------------------------------------------------------------ the reducer

export function step(state: ReviewState, action: Action): Step {
  switch (action.type) {
    case "KEEP":
    case "CONFIRM_KEEP":
    case "HIDE":
    case "MERGE":
    case "REMOVE_PERSON":
    case "COVER_SPOT":
      return runEdit(state, action);

    case "CANCEL_CONFIRM":
      return { state: state.confirm ? { ...state, confirm: null } : state, send: null };

    case "UNDO": {
      if (isReadOnly(state)) return { state, send: null };
      const index = state.undo.findIndex((u) => u.edit.edit_id === action.target);
      const entry = state.undo[index];
      if (!entry || state.pending[action.target]) return { state, send: null };
      const touched = [...Object.keys(entry.prev.items), ...Object.keys(entry.prev.spots).map((s) => `spot:${s}`)];
      const busy = pendingTouches(state);
      if (touched.some((t) => busy.has(t))) return { state, send: null };
      const prev = snapshot(state, Object.keys(entry.prev.items), Object.keys(entry.prev.spots));
      const restored = restore(state, entry.prev);
      const edit: ReviewEdit = { type: "undo", edit_id: action.edit_id, reverts: action.target };
      return {
        state: {
          ...restored,
          undo: state.undo.filter((_, i) => i !== index),
          pending: { ...state.pending, [action.edit_id]: { edit, prev, action: null, touches: touched, undone: { entry, index } } },
          toast: { kind: "undone", text: "Undone." },
        },
        send: edit,
      };
    }

    case "SERVER_ACK": {
      const own = state.pending[action.edit_id];
      if (!own) return { state, send: null };
      const pending = { ...state.pending };
      delete pending[action.edit_id];
      const base: ReviewState = {
        ...state,
        items: buildItems(action.server.items, state.context),
        spots: buildSpots(action.server.spots),
        status: action.server.status,
        has_render: action.server.has_render,
        server: { items: action.server.items, plan: action.server.plan },
        pending,
      };
      // The server's ID for a covered spot replaces the optimistic one in the undo stack.
      const undo = state.undo.map((u) => {
        if (u.edit.edit_id !== action.edit_id || own.edit.type !== "cover_spot") return u;
        const spotId = own.edit.spot_id;
        const realId = action.server.spots.find((s) => s.spot_id === spotId)?.covered_by;
        if (!realId) return u;
        return { ...u, prev: { items: { [realId]: undefined }, spots: u.prev.spots } };
      });
      return { state: { ...reapplyPending(base, pending), undo }, send: null };
    }

    case "SERVER_REJECT": {
      const p = state.pending[action.edit_id];
      if (!p) return { state, send: null };
      const pending = { ...state.pending };
      delete pending[action.edit_id];
      let next = restore({ ...state, pending }, p.prev);
      if (p.undone) {
        const undo = [...next.undo];
        undo.splice(p.undone.index, 0, p.undone.entry);
        next = { ...next, undo };
      } else {
        next = { ...next, undo: next.undo.filter((u) => u.edit.edit_id !== action.edit_id) };
      }
      return {
        state: {
          ...next,
          rejected: { ...next.rejected, [action.edit_id]: { action: p.action, edit: p.edit, ...(p.undone && { index: p.undone.index, entry: p.undone.entry }) } },
          toast: { kind: "failed", text: action.rateLimited ? RATE_LIMITED : EDIT_FAILED, edit_id: action.edit_id },
        },
        send: null,
      };
    }

    case "RETRY": {
      const r = state.rejected[action.edit_id];
      const rejected = { ...state.rejected };
      delete rejected[action.edit_id];
      const dismissed = { ...state, rejected, toast: null };
      if (!r) return { state: dismissed, send: null };
      if (r.action) {
        // A rejected CONFIRM_KEEP is retried against KEEP's precondition; `confirm` was cleared when it was sent.
        const again = r.action.type === "CONFIRM_KEEP" && r.edit.type === "keep" ? { ...dismissed, confirm: { item_id: r.edit.item_id } } : dismissed;
        const result = runEdit(again, r.action);
        return result.send ? result : { state: dismissed, send: null };
      }
      // A rejected undo: try the same undo again with the same edit_id.
      if (r.edit.type === "undo") {
        const result = step(dismissed, { type: "UNDO", target: r.edit.reverts, edit_id: r.edit.edit_id });
        return result.send ? result : { state: dismissed, send: null };
      }
      return { state: dismissed, send: null };
    }

    case "SYNC": {
      const base: ReviewState = {
        ...state,
        status: action.server.status,
        has_render: action.server.has_render,
        spots: buildSpots(action.server.spots),
        items: buildItems(action.server.items, state.context),
        server: { items: action.server.items, plan: action.server.plan },
      };
      return { state: reapplyPending(base, state.pending), send: null };
    }

    case "ACTION_ACK":
      return {
        state: { ...state, status: action.status, capNote: state.capNote?.button === action.button ? null : state.capNote },
        send: null,
      };

    case "ACTION_REFUSE":
      return { state: { ...state, refusal: { code: action.code, until: action.until } }, send: null };

    case "ACTION_CAP":
      if (state.status === "needs_you" && action.auditBudgetCause === "code_cap") return { state, send: null };
      return { state: { ...state, capNote: { button: action.button } }, send: null };

    case "REFUSAL_EXPIRED":
      if (!state.refusal || state.refusal.until === null || action.now < state.refusal.until) return { state, send: null };
      return { state: { ...state, refusal: null }, send: null };

    case "DISMISS_TOAST":
      return { state: { ...state, toast: null }, send: null };
  }
}

/** The edit a visible toast's [Undo] would revert: only the top of the stack, and only once acknowledged. */
export function undoableFromToast(state: ReviewState): string | null {
  if (state.toast?.kind !== "edit") return null;
  const top = state.undo[state.undo.length - 1];
  if (!top || top.edit.edit_id !== state.toast.edit_id) return null;
  return state.toast.edit_id;
}

export function isPending(state: ReviewState, editId: string): boolean {
  return editId in state.pending;
}

