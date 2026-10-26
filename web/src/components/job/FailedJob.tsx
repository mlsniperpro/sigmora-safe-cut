"use client";
/** A failed job (UI-SPEC §2.6, §10.3): the reason's copy and only the actions it allows. */
import Link from "next/link";
import { useState } from "react";
import { useNow } from "@/hooks/useNow";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import type { JobResponse } from "@/lib/contracts";
import { COPY, expiresBefore, failureView, formatLocal, jobRefusalMessage } from "@/lib/copy";
import { ConfirmDialog, btn } from "../ui";

export function FailedJob({ job, onResume, onDeleted }: { job: JobResponse; onResume: () => void; onDeleted: () => void }) {
  const view = failureView(job);
  const [note, setNote] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const now = useNow(15_000);
  const retryAt = view.retryAt ? Date.parse(view.retryAt) : null;

  const retry = async () => {
    setBusy(true);
    setNote(null);
    try {
      if (view.retry === "render") await getClient().render(job.job_id);
      else await getClient().startJob(job.job_id);
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
        setNote(expiresBefore(e.detail?.retry_at, job.code_valid_until) ? COPY.dailyCapJobExpiring : COPY.dailyCapJob);
        setBlocked(true);
      } else if (e?.status === 422) {
        setNote(COPY.jobCapJob);
        setBlocked(true);
      } else if (e?.status === 429) setNote(COPY.rateLimited);
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
    try {
      await getClient().deleteJob(job.job_id);
      onDeleted();
    } catch (error) {
      setDeleteError(error instanceof ApiError && error.status === 429 ? COPY.rateLimited : COPY.unexpected);
    }
  };

  const waiting = retryAt !== null && (now === 0 || now < retryAt);
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <p role="alert" className="text-xl font-medium">
        {view.message}
      </p>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        {view.actions.includes("try_again") && (
          <button type="button" className={btn.primary} disabled={busy || blocked} onClick={() => void retry()}>
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
          <a href={job.result.video_url} download className={btn.secondary}>
            Download this version
          </a>
        )}
        <button type="button" className={btn.danger} onClick={() => setConfirm(true)}>
          Delete now
        </button>
      </div>
      {note && (
        <p role="status" className="mt-3">
          {note}
        </p>
      )}
      {deleteError && (
        <p role="alert" className="mt-3 text-danger">
          {deleteError}
        </p>
      )}
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
