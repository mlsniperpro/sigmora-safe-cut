"use client";
/**
 * Demo mode (UI-SPEC §6): any API response with `mode: "replay"` turns the
 * banner on for the page. Mock mode (no API configured) shows its own banner.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Mode } from "@/lib/contracts";
import { isMockMode } from "@/lib/api";
import { PlayCircleIcon } from "./icons";

interface ModeContextValue {
  replay: boolean;
  report: (mode: Mode) => void;
}

const ModeContext = createContext<ModeContextValue>({ replay: false, report: () => undefined });

export function ModeProvider({ children }: { children: React.ReactNode }) {
  const [replay, setReplay] = useState(false);
  const report = useCallback((mode: Mode) => {
    if (mode === "replay") setReplay(true);
  }, []);
  const value = useMemo(() => ({ replay, report }), [replay, report]);
  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}

export function useMode(): ModeContextValue {
  return useContext(ModeContext);
}

/** Reports a response's mode once it's known. */
export function useReportMode(mode: Mode | null | undefined): void {
  const { report } = useMode();
  useEffect(() => {
    if (mode) report(mode);
  }, [mode, report]);
}

export function ModeBanners() {
  const { replay } = useMode();
  const [open, setOpen] = useState(false);
  const mock = isMockMode();
  return (
    <>
      {replay && (
        <div role="status" className="border-b border-border bg-demo-bg text-demo-fg">
          <div className="mx-auto flex max-w-6xl flex-wrap items-start gap-x-4 gap-y-1 px-4 py-2 text-sm">
            <p className="flex min-w-0 flex-1 items-start gap-2">
              <PlayCircleIcon size={18} className="mt-0.5 shrink-0" />
              <span>
                <strong>Demo mode.</strong> You&apos;re seeing saved results from a real run on our consented demo clip. Nothing is sent to Meta right now.
              </span>
            </p>
            <button type="button" className="min-h-8 underline underline-offset-2" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
              What&apos;s demo mode?
            </button>
            {open && (
              <p className="basis-full pb-1">
                Demo mode replays the exact responses Muse Spark, SAM 3.1 and Muse Voice Transcribe gave on a real run of this clip, through the same pipeline and the same screens. We use it when the live service is busy, and we always label it.
              </p>
            )}
          </div>
        </div>
      )}
      {mock && (
        <div role="note" className="border-b border-border bg-surface-2 text-muted">
          <p className="mx-auto max-w-6xl px-4 py-1.5 text-xs">
            Preview with sample data: no Safe Cut service is connected, nothing leaves your browser, and the people in the sample clip are drawn shapes.
          </p>
        </div>
      )}
    </>
  );
}
