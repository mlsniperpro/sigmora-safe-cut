"use client";
/**
 * One review chip (UI-SPEC §3.3): thumbnail, label, kind, badges, reason, time
 * range and the actions this item allows. Every state has an icon and a word.
 */
import { useEffect, useRef, useState } from "react";
import type { KeyframeGeometry } from "@/lib/contracts";
import { thumbnailCrop } from "@/lib/keyframe";
import type { Chip as ChipModel } from "@/lib/review/view";
import { DotsIcon, HiddenIcon, KeptIcon, LockIcon, NeedsIcon } from "../icons";

const COLUMN_ICON = { hide: HiddenIcon, keep: KeptIcon, needs_you: NeedsIcon } as const;
const COLUMN_WORD = { hide: "Hidden", keep: "Kept clear", needs_you: "Needs you" } as const;

export interface ChipHandlers {
  onSelect: (chip: ChipModel) => void;
  onWhy: (chip: ChipModel) => void;
  onHide: (chip: ChipModel) => void;
  onKeep: (chip: ChipModel) => void;
  onConfirmKeep: () => void;
  onCancelConfirm: () => void;
  onMergeMenu: (chip: ChipModel, anchor: HTMLElement) => void;
  onRemove: (chip: ChipModel) => void;
  onJump: (chip: ChipModel) => void;
  onCover: (chip: ChipModel) => void;
}

/** A crop around the item at its first evidence frame, covered unless it's kept (§3.3). */
export function Thumbnail({ chip, url, geometry, size }: { chip: ChipModel; url: string | null; geometry: KeyframeGeometry | undefined; size: number }) {
  const [failed, setFailed] = useState(false);
  const Icon = COLUMN_ICON[chip.column];
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
        onError={() => setFailed(true)}
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
            if (!menu.current?.contains(e.relatedTarget as Node)) setOpen(false);
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
  const merge = chip.buttons.merge;
  const confirmText = chip.kind === "screen" || chip.kind === "document" ? "Only keep this clear if nothing on it is personal." : "Only keep this clear if nothing on it reveals who someone is.";
  const actionClass = "inline-flex min-h-11 items-center rounded-lg border border-border px-3 text-sm font-medium hover:bg-surface-2 disabled:opacity-50 lg:min-h-8";
  return (
    <article
      aria-label={chip.accessibleName}
      data-chip-id={chip.id}
      tabIndex={-1}
      className={`rounded-xl border bg-surface p-3 [contain-intrinsic-size:auto_150px] [content-visibility:auto] ${selected ? "border-accent ring-2 ring-accent" : "border-border"}`}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("button,a")) return;
        handlers.onSelect(chip);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) {
          e.preventDefault();
          if (chip.type === "spot") handlers.onJump(chip);
          else handlers.onWhy(chip);
        }
      }}
    >
      <div className="flex gap-3">
        <Thumbnail chip={chip} url={thumbUrl} geometry={geometry} size={thumbSize} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-semibold">{chip.label}</span>
            <span className="text-sm text-muted">· {chip.kindWord}</span>
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
          <p className="line-clamp-2 mt-1 text-sm" title={chip.reason}>
            {chip.reason}
          </p>
          {chip.newLine && <p className="mt-1 text-sm text-muted">{chip.newLine}</p>}
          {chip.range && <p className="mt-1 text-xs text-muted tabular-nums">{chip.range}</p>}
        </div>
      </div>

      {confirming ? (
        <div role="group" aria-label={`Confirm keeping ${chip.label} clear`} className="mt-3 rounded-lg bg-needs-bg p-2 text-sm text-needs-fg">
          <p>{confirmText}</p>
          <div className="mt-2 flex gap-2">
            <button type="button" data-btn="confirm" className={actionClass} onClick={handlers.onConfirmKeep} autoFocus>
              Keep clear
            </button>
            <button type="button" data-btn="cancel" className={actionClass} onClick={handlers.onCancelConfirm}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {chip.buttons.why && (
            <button type="button" data-btn="why" className={actionClass} aria-label={`Why is ${chip.label} ${COLUMN_WORD[chip.column].toLowerCase()}?`} onClick={() => handlers.onWhy(chip)}>
              Why?
            </button>
          )}
          {merge && (
            <button type="button" data-btn="merge" className={actionClass} onClick={(e) => handlers.onMergeMenu(chip, e.currentTarget)}>
              Same as {merge.targetLabel}…
            </button>
          )}
          {chip.buttons.hide && (
            <button type="button" data-btn="hide" className={actionClass} aria-label={`Hide ${chip.label}`} disabled={chip.pending} onClick={() => handlers.onHide(chip)}>
              Hide
            </button>
          )}
          {chip.buttons.keep && (
            <button type="button" data-btn="keep" className={actionClass} aria-label={`Keep ${chip.label} clear`} disabled={chip.pending} onClick={() => handlers.onKeep(chip)}>
              Keep clear
            </button>
          )}
          {chip.buttons.cover && (
            <button type="button" data-btn="cover" className={actionClass} aria-label={`Cover ${chip.label}`} onClick={() => handlers.onCover(chip)}>
              Cover it
            </button>
          )}
          {chip.locked && (
            <button type="button" data-btn="locked" className="text-sm underline underline-offset-2" onClick={() => handlers.onWhy(chip)}>
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
