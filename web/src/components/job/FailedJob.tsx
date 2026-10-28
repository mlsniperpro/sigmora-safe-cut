"use client";
/** A failed job (UI-SPEC §2.6, §10.3): the reason's copy and only the actions it allows. */
import Link from "next/link";
import { useState } from "react";
import { useCooldown } from "@/hooks/useCooldown";
import { useNow } from "@/hooks/useNow";
import { RATE_LIMIT_DEFAULT_MS } from "@/lib/polling";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import type { JobResponse } from "@/lib/contracts";
import { COPY, expiresBefore, failureView, formatLocal, jobRefusalMessage } from "@/lib/copy";
import { ActionError, ConfirmDialog, btn } from "../ui";

export function FailedJob({ jobId, job, onResume, onDeleted }: { jobId: string; job: JobResponse; onResume: () => void; onDeleted: () => void }) {
  const view = failureView(job);
  const [note, setNote] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [blockedUntil, setBlockedUntil] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const { coolingDown, coolDown } = useCooldown();
  const now = useNow(15_000);
  const retryAt = view.retryAt ? Date.parse(view.retryAt) : null;

  const retry = async () => {
    setBusy(true);
    setNote(null);
    try {
      if (view.retry === "render") await getClient().render(jobId);
      else await getClient().startJob(jobId);
      onResume();
    } catch (error) {
      const e = error instanceof ApiError ? error : null;
      // The page decides, not the request: a job page shows the cap line and never deletes (§2.6.1).
      if (e?.status === 401) {
        setNote(jobRefusalMessage(e.code, e.detail?.valid_until, Date.now(), job.has_render));
        setBlocked(true);
      } else if (e?.status === 429 && e.code === "code_cap") setNote(COPY.codeCapJob);
      else if (e?.status === 429 && e.code === "pilot_pool_cap") {
        setNote(COPY.pilotPoolJob);
        setBlocked(true);
      } else if (e?.status === 429 && e.code === "daily_cap") {
        const expiring = expiresBefore(e.detail?.retry_at, job.code_valid_until);
        setNote(expiring ? COPY.dailyCapJobExpiring : COPY.dailyCapJob);
        // Disabled until retry_at (for good when the code expires first, or with no retry_at).
        if (expiring || !e.detail?.retry_at) setBlocked(true);
        else setBlockedUntil(Date.parse(e.detail.retry_at));
      } else if (e?.status === 422) {
        setNote(COPY.jobCapJob);
        setBlocked(true);
      } else if (e?.status === 429) {
        setNote(COPY.rateLimited);
        // The button that sent it waits out Retry-After (or 60 s) (§10.3).
        setBlockedUntil(Date.now() + (e.retryAfterS ?? RATE_LIMIT_DEFAULT_MS / 1000) * 1000);
      }
      else if (e?.status === 503) setNote(e.code === "billing" ? COPY.billing : COPY.auditorUnavailable);
      else if (e?.status === 409) onResume();
      else if (e?.kind === "network" || e?.kind === "timeout") {
        setNote(COPY.unreachable);
        onResume();
      } else setNote(COPY.unexpected);
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setConfirm(false);
    // A fresh attempt: an identical error is announced and focused again.
    setDeleteError(null);
    try {
      await getClient().deleteJob(jobId);
      onDeleted();
    } catch (error) {
      const limited = error instanceof ApiError && error.status === 429;
      if (limited) coolDown(error.retryAfterS);
      setDeleteError(limited ? COPY.rateLimited : COPY.unexpected);
    }
  };

  const waiting = (retryAt !== null && (now === 0 || now < retryAt)) || (blockedUntil !== null && (now === 0 || now < blockedUntil));
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <div role="alert">
        <h1 className="text-xl font-medium">{view.message}</h1>
      </div>
      {/* Answers to the buttons below come before them, so Tab moves on from an answer to its button. */}
      {note && <ActionError message={note} className="mt-3" tone="plain" />}
      {deleteError && <ActionError message={deleteError} className="mt-3" />}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        {view.actions.includes("try_again") && (
          <button type="button" className={btn.primary} disabled={busy || blocked || waiting} onClick={() => void retry()}>
            Try again
          </button>
        )}
        {view.actions.includes("try_again_tomorrow") && (
          <>
            <button type="button" className={btn.primary} disabled={busy || blocked || waiting} onClick={() => void retry()}>
              Try again tomorrow
            </button>
            {waiting && view.retryAt && <span className="text-sm text-muted">Available after {formatLocal(view.retryAt)}.</span>}
          </>
        )}
        {view.actions.includes("try_another") && (
          <Link href="/try" className={btn.secondary}>
            Try another clip
          </Link>
        )}
        {job.has_render && job.result?.video_url && (
          <a href={job.result.video_url} download target="_blank" rel="noopener noreferrer" className={btn.secondary}>
            Download this version
          </a>
        )}
        <button type="button" className={btn.danger} disabled={coolingDown} onClick={() => setConfirm(true)}>
          Delete now
        </button>
      </div>
      <ConfirmDialog
        open={confirm}
        title={job.has_render ? "Delete everything now?" : "Delete this clip?"}
        body={job.has_render ? "Delete the video, the receipt and all working files now? Download anything you need first. This can't be undone." : "Delete this clip and stop processing? This can't be undone."}
        confirm="Delete"
        cancel={job.has_render ? "Cancel" : "Keep going"}
        onConfirm={() => void doDelete()}
        onCancel={() => setConfirm(false)}
      />
    </section>
  );
}
