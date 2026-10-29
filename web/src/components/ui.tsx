"use client";
/** Small shared pieces: buttons, the native modal dialog, and the §7 message page. */
import Link from "next/link";
import { useEffect, useRef } from "react";

/** Forced colours (Windows High Contrast) drop backgrounds: the accent buttons keep an edge there. */
export const btn = {
  primary: "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-accent px-4 font-semibold text-accent-text forced-colors:border-2 forced-colors:border-[ButtonText] hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 lg:min-h-9",
  secondary: "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-border bg-surface px-3 font-medium hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50 lg:min-h-8",
  danger: "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-danger px-3 font-medium text-danger hover:bg-danger-bg disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 lg:min-h-8",
  link: "inline-flex min-h-11 items-center underline underline-offset-4 lg:min-h-8",
} as const;

/**
 * A modal on the native `<dialog>`: the browser traps focus and Esc closes it.
 * Focus returns to whatever opened it.
 */
export function Dialog({
  open,
  title,
  children,
  onClose,
  labelledBy,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  labelledBy?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<Element | null>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      opener.current = document.activeElement;
      d.showModal();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const onClose_ = () => {
      onClose();
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
    d.addEventListener("close", onClose_);
    return () => d.removeEventListener("close", onClose_);
  }, [onClose]);
  const id = labelledBy ?? `dlg-${title.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <dialog ref={ref} aria-labelledby={id} className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-0 text-text shadow-[var(--shadow)] backdrop:bg-black/50">
      {open && (
        <div className="p-5">
          <h2 id={id} className="text-lg font-semibold">
            {title}
          </h2>
          <div className="mt-3">{children}</div>
        </div>
      )}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirm,
  cancel,
  danger = true,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirm: string;
  cancel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={open} title={title} onClose={onCancel}>
      <p className="text-muted">{body}</p>
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button type="button" className={btn.secondary} onClick={onCancel} autoFocus>
          {cancel}
        </button>
        <button type="button" className={danger ? btn.danger : btn.primary} onClick={onConfirm}>
          {confirm}
        </button>
      </div>
    </Dialog>
  );
}

/** Full-page messages (UI-SPEC §7, §3.7 expired, §2.6 deleted). */
export function MessagePage({ message, actions }: { message: string; actions: Array<{ label: string; href?: string; onClick?: () => void }> }) {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      {/* The message is the page's heading; the wrapper announces it. */}
      <div role="status">
        <h1 className="text-xl font-medium">{message}</h1>
      </div>
      <div className="mt-6 flex flex-wrap gap-3">
        {actions.map((a) =>
          a.href ? (
            <Link key={a.label} href={a.href} className={btn.secondary}>
              {a.label}
            </Link>
          ) : (
            <button key={a.label} type="button" className={btn.secondary} onClick={a.onClick}>
              {a.label}
            </button>
          ),
        )}
      </div>
    </section>
  );
}

/**
 * The answer to an action (a delete's error, a refused render), next to its control. It takes
 * focus when it appears: the control may be disabled by then (a cooldown, a refusal, a request in
 * flight), and focus must not fall to the page (WCAG 2.4.3). `plain` is for refusals that aren't errors.
 */
export function ActionError({ message, className, tone = "danger" }: { message: string; className?: string; tone?: "danger" | "plain" }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [message]);
  return (
    <p ref={ref} role="alert" tabIndex={-1} className={`${tone === "danger" ? "text-danger" : ""} ${className ?? ""}`.trim()}>
      {message}
    </p>
  );
}

