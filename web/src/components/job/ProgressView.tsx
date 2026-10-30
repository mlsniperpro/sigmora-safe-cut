"use client";
/**
 * The pipeline progress view (UI-SPEC §2.3, §2.5): stage rows, the review link
 * and Cancel and delete. Shared by `/try` step C and `/jobs/[id]` while processing.
 */
import { useEffect, useRef, useState } from "react";
import { ApiError, isMockMode } from "@/lib/api";
import { getClient } from "@/lib/client";
import { useCooldown } from "@/hooks/useCooldown";
import { COPY } from "@/lib/copy";
import { StageList } from "../StageList";
import { ActionError, ConfirmDialog, btn } from "../ui";

/** Whole seconds round down (§0), so a 59.6 s clip never reads as the 1:00 limit. */
export function fmtDuration(s: number): string {
  const whole = Math.floor(s);
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
  firstFrameUrl = null,
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
  /** The prepared clip, once `prepare` made it: its first frame shows, with no overlay yet (§2.3, §2.9). */
  firstFrameUrl?: string | null;
  /** 1 on its own page (/jobs/[id]); 2 under /try's page heading. */
  headingLevel?: 1 | 2;
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  const [confirm, setConfirm] = useState(false);
  // Once the optional miss-loop row has appeared it stays, so the list doesn't jump (§2.5).
  const [seenMissLoop, setSeenMissLoop] = useState(false);
  if (active === "miss_loop" && !seenMissLoop) setSeenMissLoop(true);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const { coolingDown, coolDown } = useCooldown();
  /** One delete at a time: the button waits for the answer. */
  const [deleting, setDeleting] = useState(false);
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
    // A fresh attempt: an identical error is announced and focused again.
    setDeleteError(null);
    setDeleting(true);
    const attempt = getClient().deleteJob(jobId);
    onDeleting?.(attempt.then(() => true, () => false));
    try {
      await attempt;
      onDeleted();
    } catch (error) {
      const limited = error instanceof ApiError && error.status === 429;
      if (limited) coolDown(error.retryAfterS);
      setDeleteError(limited ? COPY.rateLimited : COPY.unexpected);
    } finally {
      setDeleting(false);
    }
  };
  return (
    <div className="mt-8">
      {fileName && (
        <p className="font-medium [overflow-wrap:anywhere]">
          {fileName}
          {duration !== null ? ` · ${fmtDuration(duration)}` : ""}
        </p>
      )}
      {firstFrameUrl && (
        <video
          src={firstFrameUrl}
          preload="metadata"
          muted
          playsInline
          aria-label="The first frame of your clip, before anything is covered"
          className="mt-4 aspect-video w-full max-w-md rounded-lg bg-black"
        />
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
      {/* The upload runs in this page: leaving or reloading stops it (§2.3 shows the leave note once it's done). */}
      {uploadPercent !== undefined ? (
        <p className="mt-8 text-sm">Keep this page open until the upload finishes. Leaving now stops it.</p>
      ) : (
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
      )}
      <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
        {deleteError && <ActionError message={deleteError} />}
        <button type="button" className={btn.danger} disabled={coolingDown}
          // In flight it only looks disabled: the dialog hands focus back to it, and a disabled
          // button would drop focus to the page (WCAG 2.4.3).
          aria-disabled={deleting || undefined}
          onClick={() => {
            if (!deleting) setConfirm(true);
          }}
        >
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
