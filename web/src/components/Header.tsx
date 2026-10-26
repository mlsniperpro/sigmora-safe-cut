"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { SITE, fromSigmora } from "@/lib/site";
import { CloseIcon, MenuIcon } from "./icons";

const NAV = [
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#results", label: "Results" },
  { href: "/try", label: "Try it" },
] as const;

function Wordmark() {
  return (
    <Link href="/" className="flex min-h-11 items-baseline gap-1.5 rounded font-semibold tracking-tight">
      <span className="text-lg">Safe Cut</span>
      <span className="text-xs font-normal text-muted">by Sigmora</span>
    </Link>
  );
}

/** The header without query-dependent parts, used while search params load. */
export function HeaderShell({ sigmora = false }: { sigmora?: boolean }) {
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const links = (
    <>
      {NAV.map((n) => (
        <Link key={n.href} href={n.href} className="flex min-h-11 items-center rounded px-2 hover:underline lg:min-h-8" onClick={() => setOpen(false)}>
          {n.label}
        </Link>
      ))}
      <a href={SITE.repoUrl} className="flex min-h-11 items-center rounded px-2 hover:underline lg:min-h-8" rel="noopener noreferrer" target="_blank">
        GitHub
      </a>
    </>
  );
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-1">
        <Wordmark />
        {sigmora ? (
          <a href={SITE.sigmoraUrl} className="flex min-h-11 items-center rounded px-2 font-medium hover:underline">
            Back to Sigmora
          </a>
        ) : (
          <>
            <nav aria-label="Main" className="hidden items-center gap-2 text-sm lg:flex">
              {links}
            </nav>
            <button
              ref={menuButton}
              type="button"
              className="flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded px-2 text-sm lg:hidden"
              aria-expanded={open}
              aria-controls="mobile-menu"
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <CloseIcon /> : <MenuIcon />} Menu
            </button>
          </>
        )}
      </div>
      {open && !sigmora && (
        <nav id="mobile-menu" aria-label="Main" className="border-t border-border px-4 pb-2 lg:hidden">
          {links}
        </nav>
      )}
    </header>
  );
}

export function Header() {
  const params = useSearchParams();
  return <HeaderShell sigmora={fromSigmora(params)} />;
}
