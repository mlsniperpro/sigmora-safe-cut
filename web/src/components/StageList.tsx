"use client";
/**
 * The stage rows (UI-SPEC §2.5): an ordered list with the active row marked and
 * announced once in a polite live region.
 */
import { AUDIT_PATCH_ROW, RENDER_ROWS, STAGE_ROWS, type ProgressStage } from "@/lib/copy";
import { CheckIcon, DotIcon, RingIcon } from "./icons";

export function StageList({
  active,
  kind,
  showMissLoop,
  uploadPercent,
  etaS,
  auditPatch = false,
}: {
  active: ProgressStage;
  kind: "pipeline" | "render";
  showMissLoop?: boolean;
  uploadPercent?: number;
  etaS?: number | null;
  auditPatch?: boolean;
}) {
  const rows = kind === "render" ? RENDER_ROWS : STAGE_ROWS.filter((r) => r.stage !== "miss_loop" || showMissLoop || active === "miss_loop");
  const activeIndex = rows.findIndex((r) => r.stage === active);
  const activeRow = rows[activeIndex];
  const activeLabel = auditPatch && active === "render" ? AUDIT_PATCH_ROW.label : activeRow?.label;
  return (
    <div>
      <ol className="flex flex-col gap-2">
        {rows.map((row, i) => {
          const done = activeIndex > i || activeIndex === -1;
          const isActive = i === activeIndex;
          const label = isActive && auditPatch && row.stage === "render" ? AUDIT_PATCH_ROW.label : row.label;
          const detail = isActive ? (auditPatch && row.stage === "render" ? AUDIT_PATCH_ROW.detail : row.stage === "uploading" ? `${uploadPercent ?? 0}%` : row.detail) : "";
          return (
            <li key={row.stage} aria-current={isActive ? "step" : undefined} className={`flex gap-3 ${isActive ? "font-medium" : done ? "" : "text-muted"}`}>
              <span className="mt-0.5 shrink-0" aria-hidden="true">
                {done ? <CheckIcon className="text-accent" /> : isActive ? <DotIcon className="text-accent" /> : <RingIcon />}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="flex flex-wrap justify-between gap-x-4">
                  <span>
                    <span className="sr-only">{done ? "Done: " : isActive ? "Now: " : "Next: "}</span>
                    {label}
                  </span>
                  {isActive && etaS ? <span className="text-sm text-muted">~{Math.max(1, Math.round(etaS))} s left</span> : null}
                </span>
                {detail && <span className="text-sm font-normal text-muted">{detail}</span>}
                {/* §2.7: a progress bar with the percent while uploading. */}
                {isActive && row.stage === "uploading" && (
                  <progress className="mt-1 h-2 w-full max-w-xs accent-[var(--accent)]" value={uploadPercent ?? 0} max={100} aria-label="Upload progress" />
                )}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        {activeLabel}
      </p>
    </div>
  );
}
