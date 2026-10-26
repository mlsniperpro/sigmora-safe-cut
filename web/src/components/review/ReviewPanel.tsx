"use client";
/**
 * The review panel (UI-SPEC §3): player with overlay, three chip columns (tabs
 * on mobile), the Why drawer, and the bottom bar. Edits are optimistic through
 * the §10.5 reducer; the server's answer replaces them.
 */
import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import type { Box, JobResponse, ReviewAck } from "@/lib/contracts";
import { COPY, auditSummary, budgetCauseLine, expiresBefore, formatLocal, jobRefusalMessage } from "@/lib/copy";
import { selectBar, type BarRow } from "@/lib/review/bar";
import { effectiveDecision, initialState, step, tracksShown, visibleItems, type Action, type ReviewState, type ServerState } from "@/lib/review/reducer";
import { buildChips, columnsOf, headerCounts, isObjectChip, mergeTargets, type Chip as ChipModel, type Column } from "@/lib/review/view";
import { formatFrame } from "@/lib/time";
import { buildWhy } from "@/lib/why/model";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useCaptions } from "@/hooks/useCaptions";
import { useNow } from "@/hooks/useNow";
import { HiddenIcon, KeptIcon, NeedsIcon, WarningIcon } from "../icons";
import { StageList } from "../StageList";
import { ConfirmDialog, Dialog, btn } from "../ui";
import { Chip, Thumbnail, type ChipHandlers } from "./Chip";
import { VideoPane, type VideoPaneHandle } from "./VideoPane";
import { WhyDrawer } from "./WhyDrawer";

const COLUMNS: ReadonlyArray<{ key: Column; title: string; Icon: typeof HiddenIcon; empty: string }> = [
  { key: "hide", title: "Hidden", Icon: HiddenIcon, empty: "Nothing is hidden." },
  { key: "keep", title: "Kept clear", Icon: KeptIcon, empty: "Nothing is kept clear. Tap Keep clear on a chip to change that." },
  { key: "needs_you", title: "Needs you", Icon: NeedsIcon, empty: "Nothing needs you." },
];
const TOAST_MS = 6_000;
const SHORTCUTS_KEY = "safecut.shortcuts";

const newEditId = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `e_${Date.now()}_${Math.random().toString(16).slice(2)}`);

export function serverStateOf(job: Pick<JobResponse, "items" | "plan" | "status" | "has_render" | "audit">): ServerState {
  return { items: job.items, plan: job.plan ?? { frames: {}, crowd_fills: [] }, status: job.status, has_render: job.has_render, spots: job.audit?.spots ?? [] };
}

function readShortcutsPref(): boolean {
  try {
    return window.localStorage.getItem(SHORTCUTS_KEY) !== "off";
  } catch {
    return true;
  }
}

export interface ReviewPanelProps {
  /** The job ID from the URL; every request uses it. */
  jobId: string;
  job: JobResponse;
  viewReview: boolean;
  onPatchJob: (update: (job: JobResponse) => JobResponse) => void;
  onResume: () => void;
  onDeleted: () => void;
  /** Called when this page starts a render or audit, so the page can move on to the result when it's done. */
  onRenderStarted: () => void;
  /** Query parameters kept across links (`from`, `demo`), e.g. "?from=sigmora". */
  query: string;
}

export function ReviewPanel({ jobId, job, viewReview, onPatchJob, onResume, onDeleted, onRenderStarted, query }: ReviewPanelProps) {
  const context = useMemo(() => ({ tracks: job.tracks, roles: job.roles }), [job.tracks, job.roles]);
  const [state, setState] = useState<ReviewState>(() => initialState(serverStateOf(job), context));
  const [synced, setSynced] = useState(job);
  const stateRef = useRef(state);
  useLayoutEffect(() => {
    stateRef.current = state;
  }, [state]);

  // A fresh job from polling or an action: adopt the server's view, keeping pending edits applied.
  if (synced !== job) {
    setSynced(job);
    const next = step({ ...state, context }, { type: "SYNC", server: serverStateOf(job) }).state;
    setState(next);
  }

  const dispatch = useCallback(
    (action: Action) => {
      const result = step(stateRef.current, action);
      stateRef.current = result.state;
      setState(result.state);
      const edit = result.send;
      if (!edit) return;
      getClient()
        .review(jobId, edit)
        .then((ack: ReviewAck) => {
          const server: ServerState = { items: ack.items, plan: ack.plan, status: ack.status, has_render: ack.has_render, spots: ack.audit?.spots ?? [] };
          const acked = step(stateRef.current, { type: "SERVER_ACK", edit_id: edit.edit_id, server });
          stateRef.current = acked.state;
          setState(acked.state);
          onPatchJob((j) => ({ ...j, status: ack.status, has_render: ack.has_render, items: ack.items, plan: ack.plan, audit: j.audit ? { ...j.audit, spots: ack.audit?.spots ?? j.audit.spots } : j.audit }));
        })
        .catch((error: unknown) => {
          console.error(`job ${jobId}: edit ${edit.type} rejected (${error instanceof ApiError ? (error.status ?? error.kind) : "error"})`);
          const rejected = step(stateRef.current, { type: "SERVER_REJECT", edit_id: edit.edit_id, rateLimited: error instanceof ApiError && error.status === 429 });
          stateRef.current = rejected.state;
          setState(rejected.state);
        });
    },
    [jobId, onPatchJob],
  );

  const desktop = useMediaQuery("(min-width: 1024px)");
  const captionsUrl = useCaptions(job.transcript, job.job?.audio ?? false);
  const now = useNow(15_000);
  const chips = useMemo(() => buildChips(state, job), [state, job]);
  const columns = useMemo(() => columnsOf(chips), [chips]);
  const bar = selectBar(state, viewReview);
  const fps = job.job?.fps ?? 30;

  // ------------------------------------------------------------------ selection, drawer, dialogs
  const video = useRef<VideoPaneHandle>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<{ id: string; locked: boolean } | null>(null);
  const [removeFor, setRemoveFor] = useState<ChipModel | null>(null);
  const [mergeFor, setMergeFor] = useState<ChipModel | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [shortcuts, setShortcuts] = useState(true);
  const returnFocus = useRef<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setShortcuts(readShortcutsPref()), 0);
    return () => clearTimeout(t);
  }, []);

  const focusChip = (id: string | null) => {
    if (!id) return;
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-chip-id="${CSS.escape(id)}"]`)?.focus());
  };

  const select = useCallback((chip: ChipModel) => {
    setSelected(chip.id);
    video.current?.seekToFrame(chip.seekFrame);
  }, []);

  const openWhy = (chip: ChipModel, locked = false) => {
    returnFocus.current = chip.id;
    setSelected(chip.id);
    setDrawer({ id: chip.id, locked });
  };

  /** The chip an edit moved, so focus follows it to its new column (§3.8). */
  const [edited, setEdited] = useState<string | null>(null);
  /**
   * Every edit goes through here: it runs the action, then points focus at the chip it moved
   * (and, on mobile, opens the tab that chip landed in), whichever route sent it: a button,
   * a shortcut, the drawer, a dialog or Undo.
   */
  const act = (action: Action) => {
    const before = stateRef.current;
    let target: string | null = null;
    switch (action.type) {
      case "HIDE":
      case "KEEP":
      case "REMOVE_PERSON":
        target = action.id;
        break;
      case "CONFIRM_KEEP":
        target = before.confirm?.item_id ?? null;
        break;
      case "MERGE":
        target = action.dst;
        break;
      case "UNDO":
        target = Object.keys(before.undo.find((u) => u.edit.edit_id === action.target)?.prev.items ?? {}).find((id) => !id.startsWith("pending:")) ?? null;
        break;
      case "COVER_SPOT":
        target = `pending:${action.edit_id}`;
        break;
      default:
        break;
    }
    dispatch(action);
    if (!target || stateRef.current === before) return;
    // An object's keep only opened its in-chip confirm, which takes focus itself.
    if (action.type === "KEEP" && stateRef.current.confirm?.item_id === target) return;
    setEdited(target);
    const column = effectiveDecision(stateRef.current, target);
    if (column && !desktop) setTab(column);
    focusChip(target);
  };
  const handlers: ChipHandlers = {
    onSelect: select,
    onWhy: (chip) => openWhy(chip, false),
    onLockedHelp: (chip) => openWhy(chip, true),
    onHide: (chip) => act({ type: "HIDE", id: chip.id, edit_id: newEditId() }),
    onKeep: (chip) => act({ type: "KEEP", id: chip.id, edit_id: newEditId() }),
    onConfirmKeep: () => act({ type: "CONFIRM_KEEP", edit_id: newEditId() }),
    onCancelConfirm: () => {
      const id = stateRef.current.confirm?.item_id ?? null;
      dispatch({ type: "CANCEL_CONFIRM" });
      focusChip(id);
    },
    onMergeMenu: (chip) => setMergeFor(chip),
    onRemove: (chip) => setRemoveFor(chip),
    onJump: (chip) => {
      setSelected(chip.id);
      video.current?.seekToFrame(chip.span?.first ?? chip.seekFrame);
      focusChip(chip.id);
    },
    onCover: (chip) => act({ type: "COVER_SPOT", spot_id: chip.id.replace(/^spot:/, ""), edit_id: newEditId() }),
  };

  // Keep focus on the chip an edit moved, in its new column (§3.8).
  const lastToast = state.toast;
  useEffect(() => {
    if (lastToast?.kind === "edit" && edited) focusChip(edited);
  }, [lastToast, edited]);

  // Focus must never land under the sticky player or the fixed bottom bar (WCAG 2.4.11, §3.8).
  const stickyTop = useRef<HTMLDivElement>(null);
  const bottomBar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = document.documentElement;
    const measure = () => {
      root.style.setProperty("--sticky-top", `${desktop ? 0 : (stickyTop.current?.offsetHeight ?? 0)}px`);
      root.style.setProperty("--sticky-bottom", `${(bottomBar.current?.offsetHeight ?? 0) + 8}px`);
    };
    const ro = new ResizeObserver(measure);
    if (stickyTop.current) ro.observe(stickyTop.current);
    if (bottomBar.current) ro.observe(bottomBar.current);
    measure();
    return () => {
      ro.disconnect();
      root.style.removeProperty("--sticky-top");
      root.style.removeProperty("--sticky-bottom");
    };
  }, [desktop]);

  // ------------------------------------------------------------------ toasts and the refusal timer
  useEffect(() => {
    if (!state.toast || state.toast.kind === "failed") return;
    const t = setTimeout(() => dispatch({ type: "DISMISS_TOAST" }), TOAST_MS);
    return () => clearTimeout(t);
  }, [state.toast, dispatch]);

  useEffect(() => {
    const until = state.refusal?.until;
    if (until === null || until === undefined) return;
    const t = setTimeout(() => dispatch({ type: "REFUSAL_EXPIRED", now: Date.now() }), Math.max(0, until - Date.now()));
    return () => clearTimeout(t);
  }, [state.refusal, dispatch]);

  // ------------------------------------------------------------------ render / audit / delete
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [refusalValidUntil, setRefusalValidUntil] = useState<string | null>(null);
  const runAction = async (button: "render" | "audit") => {
    setActionBusy(true);
    setActionError(null);
    try {
      const ack = await (button === "render" ? getClient().render(jobId) : getClient().audit(jobId));
      dispatch({ type: "ACTION_ACK", button, status: ack.status });
      onRenderStarted();
      onPatchJob((j) => ({ ...j, status: ack.status, stage: ack.stage ?? j.stage }));
      onResume();
    } catch (error) {
      const e = error instanceof ApiError ? error : null;
      if (e?.status === 409) {
        // Already rendering: the render this page asked for is under way.
        onRenderStarted();
        onResume();
      } else if (e?.status === 401) {
        dispatch({ type: "ACTION_REFUSE", button, code: e.code === "code_not_active" ? "code_not_active" : "unauthorized", until: null });
        setRefusalValidUntil(e.detail?.valid_until ?? null);
      } else if (e?.status === 429 && e.code === "code_cap") {
        dispatch({ type: "ACTION_CAP", button, auditBudgetCause: job.audit_budget_cause ?? job.audit?.audit_budget_cause ?? null });
      } else if (e?.status === 429 && e.code === "daily_cap") {
        const retryAt = e.detail?.retry_at ?? null;
        const expiring = expiresBefore(retryAt, job.code_valid_until);
        dispatch({ type: "ACTION_REFUSE", button, code: expiring ? "daily_cap_expiring" : "daily_cap", until: expiring || !retryAt ? null : Date.parse(retryAt) });
      } else if (e?.status === 429 && e.code === "pilot_pool_cap") {
        dispatch({ type: "ACTION_REFUSE", button, code: "pilot_pool_cap", until: null });
      } else if (e?.status === 429) {
        dispatch({ type: "ACTION_REFUSE", button, code: "rate_limited", until: Date.now() + (e.retryAfterS ?? 60) * 1000 });
      } else if (e?.kind === "timeout" || e?.kind === "network") {
        setActionError(COPY.unreachable);
        onResume();
      } else {
        setActionError(COPY.unexpected);
      }
    } finally {
      setActionBusy(false);
    }
  };

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBlockedUntil, setDeleteBlockedUntil] = useState<number | null>(null);
  const doDelete = async () => {
    setDeleteOpen(false);
    setDeleteError(null);
    try {
      await getClient().deleteJob(jobId);
      onDeleted();
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setDeleteError(COPY.rateLimited);
        const until = Date.now() + (error.retryAfterS ?? 60) * 1000;
        setDeleteBlockedUntil(until);
        setTimeout(() => setDeleteBlockedUntil(null), until - Date.now());
      } else {
        setDeleteError(COPY.unexpected);
      }
    }
  };
  const deleteHasRender = job.has_render && state.status !== "rendering";

  // ------------------------------------------------------------------ keyboard (§3.8)
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.closest("input,textarea,select,[role=menu]")) return;
    const article = target.closest<HTMLElement>("[data-chip-id]");
    const columnEl = target.closest<HTMLElement>("[data-column]");
    if ((e.key === "ArrowUp" || e.key === "ArrowDown") && article && columnEl) {
      e.preventDefault();
      const list = Array.from(columnEl.querySelectorAll<HTMLElement>("[data-chip-id]"));
      const next = list[list.indexOf(article) + (e.key === "ArrowDown" ? 1 : -1)];
      if (!next) return;
      const btnKind = target.getAttribute("data-btn");
      (btnKind ? next.querySelector<HTMLElement>(`[data-btn="${btnKind}"]`) ?? next : next).focus();
      return;
    }
    if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && columnEl && desktop) {
      e.preventDefault();
      const cols = Array.from(document.querySelectorAll<HTMLElement>("[data-column]"));
      const next = cols[cols.indexOf(columnEl) + (e.key === "ArrowRight" ? 1 : -1)];
      next?.querySelector<HTMLElement>("[data-chip-id]")?.focus();
      return;
    }
    if (e.altKey || e.metaKey) return;
    const chipId = article?.getAttribute("data-chip-id") ?? null;
    const key = e.key.toLowerCase();
    // Ctrl+Z isn't a single-character shortcut, so it works with the switch off; plain Z doesn't.
    if (key === "z" && ((e.ctrlKey && !e.shiftKey) || (shortcuts && !e.ctrlKey && !e.shiftKey))) {
      const top = stateRef.current.undo.at(-1);
      if (top) {
        e.preventDefault();
        act({ type: "UNDO", target: top.edit.edit_id, edit_id: newEditId() });
      }
      return;
    }
    if (e.ctrlKey || !shortcuts) return;
    if (key === "h" && chipId) {
      e.preventDefault();
      act({ type: "HIDE", id: chipId, edit_id: newEditId() });
    } else if (key === "c" && chipId) {
      e.preventDefault();
      act({ type: "KEEP", id: chipId, edit_id: newEditId() });
    } else if (key === "k") {
      e.preventDefault();
      video.current?.togglePlay();
    } else if (e.key === "?") {
      e.preventDefault();
      setHelpOpen(true);
    }
  };

  // ------------------------------------------------------------------ overlay inputs
  const overlay = useMemo(() => {
    const plannedItems = new Set(Object.values(state.server.plan.frames).flatMap((rs) => rs.map((r) => r.item_id)));
    const visible = visibleItems(state);
    return {
      plan: state.server.plan,
      isCovered: (id: string) => {
        const d = effectiveDecision(state, id);
        return d === "hide" || d === "needs_you";
      },
      unplanned: visible
        .filter(([id]) => {
          const d = effectiveDecision(state, id);
          return (d === "hide" || d === "needs_you") && !plannedItems.has(id);
        })
        .map(([id]) => ({ itemId: id, trackIds: tracksShown(state, id) })),
      items: visible.map(([id, i]) => ({ itemId: id, label: i.label, trackIds: tracksShown(state, id) })),
      tracks: new Map(job.tracks.map((t) => [t.track_id, t])),
      spots: Object.entries(state.spots)
        .filter(([, s]) => s.covered_by === null)
        .map(([id, s]) => ({ label: chips.find((c) => c.id === `spot:${id}`)?.label.replace("Unfixed spot ", "") ?? id, first: s.first, last: s.last, boxes: s.boxes })),
      selected,
    };
  }, [state, job.tracks, chips, selected]);
  const timeline = useMemo(
    () => chips.filter((c) => c.span).map((c) => ({ id: c.id, first: c.span!.first, last: c.span!.last, covered: c.column !== "keep" })),
    [chips],
  );

  // ------------------------------------------------------------------ drawer model
  const drawerItem = drawer ? state.items[drawer.id] : undefined;
  const whyModel = useMemo(() => {
    if (!drawer || !drawerItem) return null;
    return buildWhy(job, drawer.id, {
      decision: effectiveDecision(state, drawer.id) ?? drawerItem.decision,
      decided_by: drawerItem.decided_by,
      removed: drawerItem.removed,
      locked: drawerItem.locked,
      isReentry: drawerItem.reentry_target !== null,
      track_ids: tracksShown(state, drawer.id),
    });
  }, [drawer, drawerItem, job, state]);
  const drawerChip = chips.find((c) => c.id === drawer?.id);
  const boxFor = useCallback(
    (frame: number): Box | null => {
      if (!drawer) return null;
      const tracks = new Map(job.tracks.map((t) => [t.track_id, t]));
      const ids = tracksShown(state, drawer.id);
      const primary = ids.find((t) => t.startsWith("face:")) ?? ids[0];
      const order = primary ? [primary, ...ids.filter((t) => t !== primary)] : ids;
      for (const id of order) {
        const b = tracks.get(id)?.boxes[String(frame)];
        if (b) return b;
      }
      return job.items.find((i) => i.item_id === drawer.id)?.box ?? null;
    },
    [drawer, job, state],
  );

  // ------------------------------------------------------------------ layout
  const firstTab: Column = columns.needs_you.length > 0 ? "needs_you" : "hide";
  const [tab, setTab] = useState<Column | null>(null);
  const activeTab = tab ?? firstTab;
  const thumbSize = desktop ? 64 : 96;
  const duration = job.job ? formatFrame(job.job.frames, job.job.fps) : "";
  const empty = chips.length === 0;
  const auditBanner = state.status === "needs_you" && job.audit ? auditSummary(job.audit, job.job?.frames ?? job.audit.frames_scanned, budgetCauseLine(job.audit_budget_cause ?? job.audit.audit_budget_cause, job.retry_at, job.code_valid_until, (iso) => formatLocal(iso))) : null;

  const renderColumn = (col: (typeof COLUMNS)[number]) => {
    const list = columns[col.key];
    return (
      <section key={col.key} data-column={col.key} aria-labelledby={`col-${col.key}`} className="min-w-0">
        <h2 id={`col-${col.key}`} className="mb-3 hidden items-center gap-2 font-semibold lg:flex">
          <col.Icon size={14} /> {col.title} <span className={col.key === "needs_you" && list.length > 0 ? "font-bold" : "font-normal text-muted"}>({list.length})</span>
        </h2>
        {list.length === 0 ? (
          <p className="text-sm text-muted">{col.empty}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {list.map((chip) => (
              <li key={chip.id}>
                <Chip
                  chip={chip}
                  selected={selected === chip.id}
                  confirming={state.confirm?.item_id === chip.id}
                  thumbUrl={chip.thumb ? job.keyframe_urls[String(chip.thumb.frame)] ?? null : null}
                  geometry={job.keyframe_geometry}
                  thumbSize={thumbSize}
                  handlers={handlers}
                  readOnlyNote={state.status === "rendering"}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  };

  return (
    <div className="mx-auto max-w-6xl px-4 pt-6 pb-48 lg:pb-32">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">
          {job.job?.source_name ?? "Your clip"}
          {duration ? ` · ${duration}` : ""}
        </p>
        <p className="flex flex-wrap items-center gap-3 text-sm text-muted">
          <span>{headerCounts(columns)}</span>
          <button type="button" className="min-h-11 underline underline-offset-2 lg:min-h-8" onClick={() => setHelpOpen(true)}>
            Keyboard shortcuts
          </button>
        </p>
      </div>

      <div ref={stickyTop} className="-mx-4 mt-3 bg-bg px-4 pb-2 lg:static lg:mx-0 lg:px-0 [@media(min-height:640px)]:sticky [@media(min-height:640px)]:top-0 [@media(min-height:640px)]:z-10">
        <VideoPane
          ref={video}
          src={job.job?.prepared_url}
          captionsUrl={captionsUrl}
          onMediaError={onResume}
          fps={fps}
          frames={job.job?.frames ?? 1}
          width={job.job?.width ?? 1280}
          height={job.job?.height ?? 720}
          overlay={overlay}
          timeline={timeline}
          selected={selected}
        />
      </div>

      {auditBanner && (
        <div role="status" className="mt-6 rounded-xl border border-needs-fg/30 bg-needs-bg p-4 text-needs-fg">
          <p className="flex items-center gap-2 font-semibold">
            <WarningIcon /> {auditBanner.title}
          </p>
          {auditBanner.lines.map((l) => (
            <p key={l} className="mt-1">
              {l}
            </p>
          ))}
          <p className="mt-1">This version hasn&apos;t been fully checked.</p>
        </div>
      )}
      {state.status === "rendering" && <p className="mt-6 text-sm text-muted">{COPY.pausedWhileRendering}</p>}

      <div className="mt-6" onKeyDown={onKeyDown}>
        {empty ? (
          <p className="rounded-xl border border-border bg-surface p-5">
            Safe Cut didn&apos;t find any people, plates, screens or documents in this clip. If that&apos;s wrong, tell us and don&apos;t publish yet.
          </p>
        ) : desktop ? (
          <div className="grid grid-cols-3 gap-5">{COLUMNS.map(renderColumn)}</div>
        ) : (
          <div>
            <div role="tablist" aria-label="Decisions" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2">
              {COLUMNS.map((col) => (
                <button
                  key={col.key}
                  type="button"
                  role="tab"
                  id={`tab-${col.key}`}
                  aria-selected={activeTab === col.key}
                  aria-controls={`panel-${col.key}`}
                  tabIndex={activeTab === col.key ? 0 : -1}
                  className={`flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border px-4 ${activeTab === col.key ? "border-accent bg-accent text-accent-text" : "border-border bg-surface"}`}
                  onClick={() => setTab(col.key)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                      e.preventDefault();
                      const i = COLUMNS.findIndex((c) => c.key === col.key);
                      const next = COLUMNS[(i + (e.key === "ArrowRight" ? 1 : COLUMNS.length - 1)) % COLUMNS.length]!;
                      setTab(next.key);
                      document.getElementById(`tab-${next.key}`)?.focus();
                    }
                  }}
                >
                  <col.Icon size={14} /> {col.title} {columns[col.key].length}
                </button>
              ))}
            </div>
            {COLUMNS.filter((c) => c.key === activeTab).map((col) => (
              <div key={col.key} role="tabpanel" id={`panel-${col.key}`} aria-labelledby={`tab-${col.key}`} className="mt-3">
                {renderColumn(col)}
              </div>
            ))}
          </div>
        )}
      </div>

      <BottomBar
        bar={bar}
        job={job}
        state={state}
        busy={actionBusy}
        error={actionError}
        refusalValidUntil={refusalValidUntil}
        now={now}
        jobId={jobId}
        query={query}
        barRef={bottomBar}
        onRender={() => void runAction("render")}
        onAudit={() => void runAction("audit")}
        onDelete={() => setDeleteOpen(true)}
        deleteError={deleteError}
        deleteDisabled={deleteBlockedUntil !== null}
      />

      <ToastView
        state={state}
        onUndo={(id) => act({ type: "UNDO", target: id, edit_id: newEditId() })}
        onRetry={(id) => dispatch({ type: "RETRY", edit_id: id })}
        onDismiss={() => dispatch({ type: "DISMISS_TOAST" })}
      />

      <WhyDrawer
        key={drawer?.id ?? "none"}
        open={!!drawer && !!whyModel}
        job={job}
        model={whyModel}
        decision={drawer ? effectiveDecision(state, drawer.id) ?? "hide" : "hide"}
        badges={{ locked: !!drawerItem?.locked, isNew: !!drawerChip?.isNew, changedByYou: drawerItem?.decided_by === "creator" }}
        boxFor={boxFor}
        focusLocked={drawer?.locked ?? false}
        actions={{
          canHide: !!drawerChip?.buttons.hide,
          canKeep: !!drawerChip?.buttons.keep,
          onHide: () => drawer && act({ type: "HIDE", id: drawer.id, edit_id: newEditId() }),
          onKeep: () => {
            if (!drawer) return;
            // An object's keep asks for the in-chip confirm, so the drawer closes to show it.
            if (drawerChip && isObjectChip(drawerChip)) setDrawer(null);
            act({ type: "KEEP", id: drawer.id, edit_id: newEditId() });
          },
        }}
        onClose={() => {
          setDrawer(null);
          focusChip(returnFocus.current);
        }}
      />

      <ConfirmDialog
        open={!!removeFor}
        title="Remove this person?"
        body="They'll be fully covered, not just their face, every time they appear. Your privacy receipt will record that you removed them."
        confirm="Remove"
        cancel="Cancel"
        onConfirm={() => {
          if (removeFor) {
            act({ type: "REMOVE_PERSON", id: removeFor.id, edit_id: newEditId() });
          }
          setRemoveFor(null);
        }}
        onCancel={() => {
          focusChip(removeFor?.id ?? null);
          setRemoveFor(null);
        }}
      />

      <Dialog
        open={!!mergeFor}
        title={mergeFor ? `Who is ${mergeFor.label}?` : "Same person as…"}
        onClose={() => {
          focusChip(mergeFor?.id ?? null);
          setMergeFor(null);
        }}
      >
        <ul className="flex flex-col gap-2">
          {mergeFor &&
            mergeTargets(state, mergeFor.id).map((t) => {
              const chip = chips.find((c) => c.id === t.id);
              const description = describeParticipant(job, t.id);
              return (
                <li key={t.id}>
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-center gap-3 rounded-lg border border-border p-2 text-left hover:bg-surface-2"
                    onClick={() => {
                      act({ type: "MERGE", src: mergeFor.id, dst: t.id, edit_id: newEditId() });
                      setMergeFor(null);
                    }}
                  >
                    {chip && <Thumbnail chip={chip} url={chip.thumb ? job.keyframe_urls[String(chip.thumb.frame)] ?? null : null} geometry={job.keyframe_geometry} size={48} />}
                    <span>
                      Same person as {t.label}
                      {description ? ` (${description})` : ""}
                    </span>
                  </button>
                </li>
              );
            })}
        </ul>
        <div className="mt-4 flex justify-end">
          <button type="button" className={btn.secondary} onClick={() => setMergeFor(null)}>
            Cancel
          </button>
        </div>
      </Dialog>

      <ConfirmDialog
        open={deleteOpen}
        title={deleteHasRender ? "Delete everything now?" : "Delete this clip?"}
        body={deleteHasRender ? "Delete the video, the receipt and all working files now? Download anything you need first. This can't be undone." : "Delete this clip and stop processing? This can't be undone."}
        confirm="Delete"
        cancel={deleteHasRender ? "Cancel" : "Keep going"}
        onConfirm={() => void doDelete()}
        onCancel={() => setDeleteOpen(false)}
      />

      <Dialog open={helpOpen} title="Keyboard shortcuts" onClose={() => setHelpOpen(false)}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {[
            ["Tab", "Move through every button"],
            ["↑ / ↓", "Same button on the previous / next chip"],
            ["← / →", "First chip of the neighbouring column"],
            ["Enter", "Open Why? on a focused chip"],
            ["H", "Hide the focused item"],
            ["C", "Keep the focused item clear"],
            ["Z or Ctrl+Z", "Undo the last edit"],
            ["K", "Play or pause the video"],
            ["?", "Show this list"],
            ["Esc", "Close a menu, dialog or the drawer"],
          ].map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-mono">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <label className="mt-4 flex min-h-11 items-center gap-2">
          <input
            type="checkbox"
            className="h-5 w-5"
            checked={shortcuts}
            onChange={(e) => {
              setShortcuts(e.target.checked);
              try {
                window.localStorage.setItem(SHORTCUTS_KEY, e.target.checked ? "on" : "off");
              } catch {
                // Storage can be blocked; the choice still holds for this page.
              }
            }}
          />
          Single-key shortcuts
        </label>
        <div className="mt-4 flex justify-end">
          <button type="button" className={btn.secondary} onClick={() => setHelpOpen(false)} autoFocus>
            Close
          </button>
        </div>
      </Dialog>
    </div>
  );
}

function describeParticipant(job: JobResponse, itemId: string): string | null {
  const item = job.items.find((i) => i.item_id === itemId);
  const primary = item?.track_ids.find((t) => t.startsWith("face:")) ?? item?.track_ids[0];
  const k = job.roles?.tracks.find((t) => t.track_id === primary)?.matches_participant;
  if (k === null || k === undefined) return null;
  return job.scene?.participants[k]?.description ?? null;
}

// ------------------------------------------------------------------ bottom bar (§3.5)

function BottomBar({
  bar,
  job,
  state,
  busy,
  error,
  refusalValidUntil,
  now,
  jobId,
  query,
  barRef,
  onRender,
  onAudit,
  onDelete,
  deleteError,
  deleteDisabled,
}: {
  bar: BarRow;
  job: JobResponse;
  state: ReviewState;
  busy: boolean;
  error: string | null;
  refusalValidUntil: string | null;
  now: number;
  jobId: string;
  query: string;
  barRef: React.RefObject<HTMLDivElement | null>;
  onRender: () => void;
  onAudit: () => void;
  onDelete: () => void;
  deleteError: string | null;
  deleteDisabled: boolean;
}) {
  const cause = job.audit_budget_cause ?? job.audit?.audit_budget_cause ?? null;
  const hasRender = job.has_render;
  const download = hasRender && job.result?.video_url ? job.result.video_url : null;
  let text: string | null = null;
  let main: React.ReactNode = null;
  const approve = (disabled: boolean) => (
    <button type="button" className={btn.primary} disabled={disabled || busy} onClick={onRender}>
      Approve &amp; render
    </button>
  );
  const runAudit = (disabled: boolean) => (
    <button type="button" className={btn.primary} disabled={disabled || busy} onClick={onAudit}>
      Run the audit again
    </button>
  );
  const downloadLink = download ? (
    <a href={download} download className={btn.secondary}>
      Download this version
    </a>
  ) : null;

  switch (bar.kind) {
    case "refused": {
      const code = bar.code;
      text =
        code === "unauthorized" || code === "code_not_active"
          ? jobRefusalMessage(code, refusalValidUntil, now, hasRender)
          : code === "daily_cap"
            ? COPY.dailyCapJob
            : code === "daily_cap_expiring"
              ? COPY.dailyCapJobExpiring
              : code === "pilot_pool_cap"
                ? COPY.pilotPoolJob
                : COPY.rateLimited;
      const hide = code === "daily_cap_expiring";
      main =
        state.status === "needs_you" ? (
          <>
            {cause !== "job_cap" && !hide && runAudit(true)}
            {downloadLink}
          </>
        ) : (
          <>
            {!hide && approve(true)}
            {downloadLink}
          </>
        );
      break;
    }
    case "rendering":
      main = (
        <div className="w-full">
          <StageList kind="render" active={job.stage === "audit" || job.stage === "receipt" ? job.stage : "render"} auditPatch={job.stage_reason === "audit_patch"} />
        </div>
      );
      break;
    case "audit_blocked": {
      text = job.audit ? null : "This version hasn't been fully checked.";
      const retryAt = job.retry_at ? Date.parse(job.retry_at) : null;
      const expiring = cause === "daily_cap" && expiresBefore(job.retry_at, job.code_valid_until);
      const waiting = cause === "daily_cap" && retryAt !== null && now < retryAt;
      main = (
        <>
          {cause !== "job_cap" && !expiring && runAudit(waiting || cause === "pilot_pool_cap")}
          {cause === "daily_cap" && !expiring && job.retry_at && waiting && <span className="text-sm text-muted">Available after {formatLocal(job.retry_at)}.</span>}
          {cause === "code_cap" && <span className="text-sm">{COPY.codeCapJob}</span>}
          {cause === "pilot_pool_cap" && <span className="text-sm">{COPY.pilotPoolJob}</span>}
          {downloadLink}
          {cause === "job_cap" && (
            <Link href="/try" className={btn.secondary}>
              Try another clip
            </Link>
          )}
        </>
      );
      break;
    }
    case "saving":
      text = "Saving your changes…";
      main = approve(true);
      break;
    case "unfixed":
      text = `${bar.count} unfixed ${bar.count === 1 ? "spot is" : "spots are"} visible in the video. Cover ${bar.count === 1 ? "it" : "them"} before rendering.`;
      main = approve(true);
      break;
    case "unchanged":
      text = "Nothing has changed since the last render.";
      main = (
        <>
          {approve(true)}
          <Link href={`/jobs/${encodeURIComponent(jobId)}/result${query}`} className={btn.link}>
            Back to result
          </Link>
        </>
      );
      break;
    case "edited_after_render":
      text = "You changed something after rendering. Render again to update the video and receipt.";
      main = approve(false);
      break;
    case "needs_you":
      text = `${bar.count} ${bar.count === 1 ? "item still needs" : "items still need"} you. If you render now, ${bar.count === 1 ? "it stays" : "they stay"} hidden.`;
      main = approve(false);
      break;
    case "all_decided":
      text = "Everything's decided.";
      main = approve(false);
      break;
  }

  return (
    <div ref={barRef} className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3">
        {state.capNote && <p className="text-sm">{COPY.codeCapJob}</p>}
        {text && <p className="font-medium">{text}</p>}
        <div className="flex flex-wrap items-center gap-2">
          {main}
          <span className="flex-1" />
          {deleteError && (
            <p role="alert" className="text-sm text-danger">
              {deleteError}
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <button type="button" className={btn.danger} onClick={onDelete} disabled={deleteDisabled}>
            Delete everything now
          </button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ toast (§3.4, §10.5)

function ToastView({ state, onUndo, onRetry, onDismiss }: { state: ReviewState; onUndo: (id: string) => void; onRetry: (id: string) => void; onDismiss: () => void }) {
  const toast = state.toast;
  const top = state.undo.at(-1);
  const undoable = toast?.kind === "edit" && top?.edit.edit_id === toast.edit_id;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-40 z-30 flex justify-center px-4 lg:bottom-28">
      <div role="status" aria-live="polite" className="pointer-events-auto">
        {toast && (
          <div className="flex items-center gap-3 rounded-lg bg-text px-4 py-2 text-sm text-bg shadow-[var(--shadow)]">
            <span>{toast.text}</span>
            {undoable && (
              <button type="button" className="min-h-11 font-semibold underline underline-offset-2 disabled:opacity-50 lg:min-h-9" disabled={toast.edit_id in state.pending} onClick={() => onUndo(toast.edit_id)}>
                Undo
              </button>
            )}
            {toast.kind === "failed" && (
              <>
                <button type="button" className="min-h-11 font-semibold underline underline-offset-2 lg:min-h-9" onClick={() => onRetry(toast.edit_id)}>
                  Try again
                </button>
                <button type="button" className="min-h-11 underline underline-offset-2 lg:min-h-9" onClick={onDismiss}>
                  Dismiss
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
