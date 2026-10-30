"use client";
/**
 * Demo mode (UI-SPEC §6): any API response with `mode: "replay"` turns the banner on for the page. A replay of
 * synthetic recordings (`synthetic: true`, the drawn test clip before real footage exists) says so plainly.
 */
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Mode } from "@/lib/contracts";
import { PlayCircleIcon } from "./icons";

interface ModeContextValue {
  replay: boolean;
  synthetic: boolean;
  report: (mode: Mode, synthetic?: boolean) => void;
}

const ModeContext = createContext<ModeContextValue>({ replay: false, synthetic: false, report: () => undefined });

export function ModeProvider({ children }: { children: React.ReactNode }) {
  // Demo mode belongs to the page whose response said "replay" (§6): moving to another page
  // (say from the landing hero to a live /try upload) must not carry the banner along.
  const pathname = usePathname();
  const [replayPath, setReplayPath] = useState<string | null>(null);
  const [syntheticPath, setSyntheticPath] = useState<string | null>(null);
  const replay = replayPath !== null && replayPath === pathname;
  const synthetic = replay && syntheticPath === pathname;
  const report = useCallback(
    (mode: Mode, isSynthetic = false) => {
      if (mode !== "replay") return;
      setReplayPath(pathname);
      if (isSynthetic) setSyntheticPath(pathname);
    },
    [pathname],
  );
  const value = useMemo(() => ({ replay, synthetic, report }), [replay, synthetic, report]);
  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}

export function useMode(): ModeContextValue {
  return useContext(ModeContext);
}

/** Reports a response's mode (and whether its replay is synthetic) once it's known. */
export function useReportMode(mode: Mode | null | undefined, synthetic = false): void {
  const { report } = useMode();
  useEffect(() => {
    if (mode) report(mode, synthetic);
  }, [mode, synthetic, report]);
}

export function ModeBanners() {
  const { replay, synthetic } = useMode();
  const [open, setOpen] = useState(false);
  if (!replay) return null;
  return (
    <div role="status" className="border-b border-border bg-demo-bg text-demo-fg">
      <div className="mx-auto flex max-w-6xl flex-wrap items-start gap-x-4 gap-y-1 px-4 py-2 text-sm">
        <p className="flex min-w-0 flex-1 items-start gap-2">
          <PlayCircleIcon size={18} className="mt-0.5 shrink-0" />
          <span>
            <strong>Demo mode.</strong>{" "}
            {synthetic
              ? "You're seeing saved results for a synthetic test clip: the people are drawn shapes and the model answers were written to match them, not returned by Meta. Nothing is sent to Meta right now."
              : "You're seeing saved results from a real run on our consented demo clip. Nothing is sent to Meta right now."}
          </span>
        </p>
        <button type="button" className="min-h-11 underline underline-offset-2 lg:min-h-8" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          What&apos;s demo mode?
        </button>
        {open && (
          <p className="basis-full pb-1">
            {synthetic
              ? "Demo mode replays saved answers through the same pipeline and the same screens. These answers are synthetic stand-ins for Muse Spark, SAM 3.1 and Muse Voice Transcribe, so you can try every step before the live service opens. We always label it."
              : "Demo mode replays the exact responses Muse Spark, SAM 3.1 and Muse Voice Transcribe gave on a real run of this clip, through the same pipeline and the same screens. We use it when the live service is busy, and we always label it."}
          </p>
        )}
      </div>
    </div>
  );
}
