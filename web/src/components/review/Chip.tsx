"use client";
/**
 * One review chip (UI-SPEC §3.3): thumbnail, label, kind, badges, reason, time
 * range and the actions this item allows. Every state has an icon and a word.
 */
import { useEffect, useRef, useState } from "react";
import type { KeyframeGeometry } from "@/lib/contracts";
import { thumbnailCrop } from "@/lib/keyframe";
import type { Chip as ChipModel } from "@/lib/review/view";
import { ChildIcon, DocumentIcon, DotsIcon, HiddenIcon, KeptIcon, LockIcon, NeedsIcon, OtherIcon, PersonIcon, PlateIcon, ScreenIcon } from "../icons";

/** Each kind's icon, shown with its word (§3.3) and on the placeholder tile when there's no thumbnail. */
const KIND_ICON = { person: PersonIcon, child: ChildIcon, plate: PlateIcon, screen: ScreenIcon, document: DocumentIcon, other: OtherIcon } as const;

const COLUMN_ICON = { hide: HiddenIcon, keep: KeptIcon, needs_you: NeedsIcon } as const;
const COLUMN_WORD = { hide: "Hidden", keep: "Kept clear", needs_you: "Needs you" } as const;

export interface ChipHandlers {
  onSelect: (chip: ChipModel) => void;
  onWhy: (chip: ChipModel) => void;
  /** The "Always hidden" help link: opens the drawer at the explanation. */
  onLockedHelp: (chip: ChipModel) => void;
  onHide: (chip: ChipModel) => void;
  onKeep: (chip: ChipModel) => void;
  onConfirmKeep: () => void;
  onCancelConfirm: () => void;
  onMergeMenu: (chip: ChipModel, anchor: HTMLElement) => void;
  onRemove: (chip: ChipModel) => void;
  onJump: (chip: ChipModel) => void;
  onCover: (chip: ChipModel) => void;
  /** A keyframe image failed to load: its signed URL may have expired (§10.7). */
  onKeyframeError: () => void;
}

/** A crop around the item at its first evidence frame, covered unless it's kept (§3.3). */
export function Thumbnail({
  chip,
  url,
  geometry,
  size,
  onError,
}: {
  chip: ChipModel;
  url: string | null;
  geometry: KeyframeGeometry | undefined;
  size: number;
  onError?: () => void;
}) {
  // Keyed by URL: a refetched job's fresh signed URL gets a new try.
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const failed = failedUrl !== null && failedUrl === url;
  // A pending cover has no kind yet (§10.5 COVER_SPOT), so its tile keeps the state's icon.
  const Icon = chip.id.startsWith("pending:") ? COLUMN_ICON[chip.column] : KIND_ICON[chip.kind];
  const alt = `${chip.label}, ${chip.kindWord}, ${COLUMN_WORD[chip.column].toLowerCase()}`;
  if (!chip.thumb || !url || !geometry || failed) {
    return (
      <div role="img" aria-label={alt} className="flex shrink-0 items-center justify-center rounded-md bg-surface-2 text-muted" style={{ width: size, height: size }}>
        <Icon size={20} />
      </div>
    );
  }
  const [cx1, cy1, cx2] = thumbnailCrop(chip.thumb.box, geometry);
  const s = size / (cx2 - cx1);
  const [bx1, by1, bx2, by2] = chip.thumb.box;
  return (
    <div className="relative shrink-0 overflow-hidden rounded-md bg-surface-2" style={{ width: size, height: size }}>
      {/* A plain img: a signed keyframe URL needs no optimisation and must not be cached by an image proxy. */}
      {/* eslint-disable-next-line @next/next/no-img-element -- signed, short-lived URLs bypass next/image on purpose */}
      <img
        src={url}
        alt={alt}
        loading="lazy"
        decoding="async"
        onError={() => {
          setFailedUrl(url);
          onError?.();
        }}
        className="absolute max-w-none"
        style={{ width: geometry.image_width * s, height: geometry.image_height * s, left: -cx1 * s, top: -cy1 * s }}
      />
      {chip.column !== "keep" && (
        <div
          aria-hidden="true"
          className="absolute bg-[#18181b]"
          style={{ left: (bx1 - cx1) * s, top: (by1 + geometry.bar_h - cy1) * s, width: (bx2 - bx1) * s, height: (by2 - by1) * s }}
        />
      )}
    </div>
  );
}

function OverflowMenu({ chip, onRemove, onJump }: { chip: ChipModel; onRemove: () => void; onJump: () => void }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, [open]);
  const close = () => {
    setOpen(false);
    button.current?.focus();
  };
  const items = [
    ...(chip.buttons.menu.remove ? [{ label: "Remove this person from the video", run: onRemove }] : []),
    ...(chip.buttons.menu.jump ? [{ label: "Jump to first appearance", run: onJump }] : []),
  ];
  if (items.length === 0) return null;
  return (
    <div className="relative">
      <button
        ref={button}
        type="button"
        data-btn="menu"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`More actions for ${chip.label}`}
        className="flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-border hover:bg-surface-2 lg:min-h-8 lg:min-w-8"
        onClick={() => setOpen((v) => !v)}
      >
        <DotsIcon />
      </button>
      {open && (
        <ul
          ref={menu}
          role="menu"
          className="absolute right-0 z-20 mt-1 w-64 rounded-lg border border-border bg-surface p-1 shadow-[var(--shadow)]"
          onKeyDown={(e) => {
            const buttons = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
            const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
            if (e.key === "Escape") {
              e.stopPropagation();
              close();
            } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              e.stopPropagation();
              const next = buttons[(i + (e.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length];
              next?.focus();
            }
          }}
          onBlur={(e) => {
            // Focus moving to the trigger is its click, which toggles the menu shut itself.
            if (!menu.current?.contains(e.relatedTarget as Node) && e.relatedTarget !== button.current) setOpen(false);
          }}
        >
          {items.map((item) => (
            <li key={item.label} role="none">
              <button
                type="button"
                role="menuitem"
                className="flex min-h-11 w-full items-center rounded-md px-3 text-left text-sm hover:bg-surface-2 lg:min-h-9"
                onClick={() => {
                  setOpen(false);
                  item.run();
                }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Chip({
  chip,
  selected,
  confirming,
  thumbUrl,
  geometry,
  thumbSize,
  handlers,
  readOnlyNote,
}: {
  chip: ChipModel;
  selected: boolean;
  confirming: boolean;
  thumbUrl: string | null;
  geometry: KeyframeGeometry | undefined;
  thumbSize: number;
  handlers: ChipHandlers;
  readOnlyNote: boolean;
}) {
  const Icon = COLUMN_ICON[chip.column];
  const KindIcon = KIND_ICON[chip.kind];
  const merge = chip.buttons.merge;
  const confirmText = chip.kind === "screen" || chip.kind === "document" ? "Only keep this clear if nothing on it is personal." : "Only keep this clear if nothing on it reveals who someone is.";
  const actionClass = "inline-flex min-h-11 items-center rounded-lg border border-border px-3 text-sm font-medium hover:bg-surface-2 disabled:opacity-50 lg:min-h-8";
  return (
    <article
      aria-label={chip.accessibleName}
      data-chip-id={chip.id}
      data-selected={selected || undefined}
      tabIndex={0}
      className={`rounded-xl border bg-surface p-3 ${selected ? "border-accent ring-2 ring-accent forced-colors:border-[3px]" : "border-border"}`}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("button,a")) return;
        handlers.onSelect(chip);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) {
          e.preventDefault();
          // Enter selects, like a click on the body; the drawer opens from the chip's [Why?] (§3.8).
          if (chip.type === "spot") handlers.onJump(chip);
          else handlers.onSelect(chip);
        }
      }}
    >
      <div className="flex gap-3">
        <Thumbnail chip={chip} url={thumbUrl} geometry={geometry} size={thumbSize} onError={handlers.onKeyframeError} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-semibold">{chip.label}</span>
            {/* A pending covered spot shows no kind until the server's answer brings it (§10.5 COVER_SPOT). */}
            {!chip.id.startsWith("pending:") && (
              <span className="inline-flex items-center gap-1 text-sm text-muted">
                · <KindIcon size={12} /> {chip.kindWord}
              </span>
            )}
            <span className="sr-only">{COLUMN_WORD[chip.column]}</span>
            <Icon size={12} className="text-muted" />
            {chip.locked && (
              <span className="inline-flex items-center gap-1 rounded bg-hidden-bg px-1.5 text-xs font-medium text-hidden-fg">
                <LockIcon size={12} /> Always hidden
              </span>
            )}
            {chip.isNew && <span className="rounded bg-needs-bg px-1.5 text-xs font-semibold text-needs-fg">NEW</span>}
            {chip.changedByYou && <span className="rounded bg-surface-2 px-1.5 text-xs">Changed by you</span>}
          </p>
          {/* In full: a clamp hid the end of longer reasons at 320 px and under text-spacing overrides (WCAG 1.4.10, 1.4.12); a long URL or ID wraps. */}
          <p className="mt-1 text-sm [overflow-wrap:anywhere]">{chip.reason}</p>
          {chip.newLine && <p className="mt-1 text-sm text-muted [overflow-wrap:anywhere]">{chip.newLine}</p>}
          {chip.range && <p className="mt-1 text-xs text-muted tabular-nums">{chip.range}</p>}
        </div>
      </div>

      {confirming ? (
        <div role="group" aria-label={`Confirm keeping ${chip.label} clear`} className="mt-3 rounded-lg bg-needs-bg p-2 text-sm text-needs-fg">
          <p>{confirmText}</p>
          <div className="mt-2 flex gap-2">
            <button type="button" data-btn="confirm" className={actionClass} onClick={handlers.onConfirmKeep}>
              Keep clear
            </button>
            <button type="button" data-btn="cancel" className={actionClass} onClick={handlers.onCancelConfirm} autoFocus>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {chip.buttons.why && (
            <button type="button" data-btn="why" className={actionClass} onClick={() => handlers.onWhy(chip)}>
              Why?{" "}<span className="sr-only">{chip.label}, {COLUMN_WORD[chip.column].toLowerCase()}</span>
            </button>
          )}
          {merge && (
            <button type="button" data-btn="merge" className={actionClass} onClick={(e) => handlers.onMergeMenu(chip, e.currentTarget)}>
              Same as {merge.targetLabel}…
            </button>
          )}
          {chip.buttons.hide && (
            <button type="button" data-btn="hide" className={actionClass} disabled={chip.pending} onClick={() => handlers.onHide(chip)}>
              Hide{" "}<span className="sr-only">{chip.label}</span>
            </button>
          )}
          {chip.buttons.keep && (
            <button type="button" data-btn="keep" className={actionClass} disabled={chip.pending} onClick={() => handlers.onKeep(chip)}>
              Keep clear{" "}<span className="sr-only">{chip.label}</span>
            </button>
          )}
          {chip.buttons.cover && (
            <button type="button" data-btn="cover" className={actionClass} onClick={() => handlers.onCover(chip)}>
              Cover it{" "}<span className="sr-only">{chip.label}</span>
            </button>
          )}
          {chip.locked && (
            <button type="button" data-btn="locked" className="min-h-11 text-sm underline underline-offset-2 lg:min-h-8" onClick={() => handlers.onLockedHelp(chip)}>
              Always hidden
            </button>
          )}
          <span className="flex-1" />
          <OverflowMenu chip={chip} onRemove={() => handlers.onRemove(chip)} onJump={() => handlers.onJump(chip)} />
        </div>
      )}
      {chip.pending && <p className="mt-1 text-xs text-muted">Saving…</p>}
      {readOnlyNote && selected && <p className="mt-1 text-xs text-muted">Changes are paused while we render.</p>}
    </article>
  );
}
