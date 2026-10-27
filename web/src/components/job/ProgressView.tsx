"use client";
/**
 * The pipeline progress view (UI-SPEC §2.3, §2.5): stage rows, the review link
 * and Cancel and delete. Shared by `/try` step C and `/jobs/[id]` while processing.
 */
import { useEffect, useRef, useState } from "react";
import { ApiError, isMockMode } from "@/lib/api";
import { getClient } from "@/lib/client";
import { COPY } from "@/lib/copy";
import { StageList } from "../StageList";
import { ConfirmDialog, btn } from "../ui";

export function fmtDuration(s: number): string {
  const whole = Math.round(s);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** How long "Copied" shows before the button reads "Copy link" again. */
const COPIED_MS = 2_000;

export function ProgressView({
  fileName,
  duration,
  active,
  uploadPercent,
  jobId,
  etaS,
  busy,
  onDeleting,
  onDeleted,
  headingLevel = 2,
}: {
  fileName: string | null;
  duration: number | null;
  active: Parameters<typeof StageList>[0]["active"];
  uploadPercent?: number;
  jobId: string;
  etaS?: number | null;
  busy?: boolean;
  /** The confirmed delete is on its way; `done` says whether it worked. */
  onDeleting?: (done: Promise<boolean>) => void;
  onDeleted: () => void;
  /** 1 on its own page (/jobs/[id]); 2 under /try's page heading. */
  headingLevel?: 1 | 2;
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  const [confirm, setConfirm] = useState(false);
  // Once the optional miss-loop row has appeared it stays, so the list doesn't jump (§2.5).
  const [seenMissLoop, setSeenMissLoop] = useState(false);
  if (active === "miss_loop" && !seenMissLoop) setSeenMissLoop(true);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const linkRef = useRef<HTMLElement>(null);
  // "Copied" goes back to "Copy link" after a moment, so a second copy also confirms.
  useEffect(() => {
    if (copied !== "copied") return;
    const t = setTimeout(() => setCopied("idle"), COPIED_MS);
    return () => clearTimeout(t);
  }, [copied]);
  const link = typeof window === "undefined" ? `/jobs/${jobId}` : `${window.location.origin}/jobs/${encodeURIComponent(jobId)}`;
  const doDelete = async () => {
    setConfirm(false);
    const attempt = getClient().deleteJob(jobId);
    onDeleting?.(attempt.then(() => true, () => false));
    try {
      await attempt;
      onDeleted();
    } catch (error) {
      setDeleteError(error instanceof ApiError && error.status === 429 ? COPY.rateLimited : COPY.unexpected);
    }
  };
  return (
    <div className="mt-8">
      {fileName && (
        <p className="font-medium">
          {fileName}
          {duration !== null ? ` · ${fmtDuration(duration)}` : ""}
        </p>
      )}
      <Heading data-step-heading tabIndex={-1} className="mt-4 text-xl font-semibold">
        Working on your clip
      </Heading>
      {busy && (
        <p role="status" className="mt-3 rounded-lg bg-needs-bg p-3 text-needs-fg">
          {COPY.metaBusy}
        </p>
      )}
      <div className="mt-4">
        <StageList active={active} kind="pipeline" showMissLoop={seenMissLoop} {...(uploadPercent !== undefined && { uploadPercent })} etaS={etaS ?? null} />
      </div>
      <div className="mt-8 flex flex-wrap items-center gap-3 text-sm">
        <span>You can leave this page. Your review link{isMockMode() ? " (in this preview it only works in this browser)" : ""}:</span>
        <code ref={linkRef} className="rounded bg-surface-2 px-2 py-1 break-all">
          {link}
        </code>
        <button
          type="button"
          className={btn.secondary}
          onClick={() => {
            // No Clipboard API (an insecure context) or no permission: select the link instead.
            const failed = () => {
              setCopied("failed");
              const el = linkRef.current;
              const selection = window.getSelection();
              if (el && selection) selection.selectAllChildren(el);
            };
            if (!navigator.clipboard) return failed();
            navigator.clipboard.writeText(link).then(() => setCopied("copied"), failed);
          }}
        >
          {copied === "copied" ? "Copied" : "Copy link"}
        </button>
        {/* Always mounted, so screen readers announce what changes in it. */}
        <span role="status" className={copied === "copied" ? "sr-only" : undefined}>
          {copied === "failed" ? "Couldn't copy. The link is selected: copy it from there." : copied === "copied" ? "Link copied." : ""}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
        {deleteError && (
          <p role="alert" className="text-danger">
            {deleteError}
          </p>
        )}
        <button type="button" className={btn.danger} onClick={() => setConfirm(true)}>
          Cancel and delete
        </button>
      </div>
      <ConfirmDialog
        open={confirm}
        title="Delete this clip?"
        body="Delete this clip and stop processing? This can't be undone."
        confirm="Delete"
        cancel="Keep going"
        onConfirm={() => void doDelete()}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}
