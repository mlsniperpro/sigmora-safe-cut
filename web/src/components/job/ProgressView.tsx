"use client";
/**
 * The pipeline progress view (UI-SPEC §2.3, §2.5): stage rows, the review link
 * and Cancel and delete. Shared by `/try` step C and `/jobs/[id]` while processing.
 */
import { useState } from "react";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import { COPY } from "@/lib/copy";
import { StageList } from "../StageList";
import { ConfirmDialog, btn } from "../ui";

export function fmtDuration(s: number): string {
  const whole = Math.round(s);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function ProgressView({
  fileName,
  duration,
  active,
  uploadPercent,
  jobId,
  etaS,
  busy,
  onDeleted,
}: {
  fileName: string | null;
  duration: number | null;
  active: Parameters<typeof StageList>[0]["active"];
  uploadPercent?: number;
  jobId: string;
  etaS?: number | null;
  busy?: boolean;
  onDeleted: () => void;
}) {
  const [confirm, setConfirm] = useState(false);
  // Once the optional miss-loop row has appeared it stays, so the list doesn't jump (§2.5).
  const [seenMissLoop, setSeenMissLoop] = useState(false);
  if (active === "miss_loop" && !seenMissLoop) setSeenMissLoop(true);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const link = typeof window === "undefined" ? `/jobs/${jobId}` : `${window.location.origin}/jobs/${encodeURIComponent(jobId)}`;
  const doDelete = async () => {
    setConfirm(false);
    try {
      await getClient().deleteJob(jobId);
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
      <h2 data-step-heading tabIndex={-1} className="mt-4 text-xl font-semibold">
        Working on your clip
      </h2>
      {busy && (
        <p role="status" className="mt-3 rounded-lg bg-needs-bg p-3 text-needs-fg">
          {COPY.metaBusy}
        </p>
      )}
      <div className="mt-4">
        <StageList active={active} kind="pipeline" showMissLoop={seenMissLoop} {...(uploadPercent !== undefined && { uploadPercent })} etaS={etaS ?? null} />
      </div>
      <div className="mt-8 flex flex-wrap items-center gap-3 text-sm">
        <span>You can leave this page. Your review link:</span>
        <code className="rounded bg-surface-2 px-2 py-1">{link}</code>
        <button
          type="button"
          className={btn.secondary}
          onClick={() => {
            void navigator.clipboard?.writeText(link).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy link"}
        </button>
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
