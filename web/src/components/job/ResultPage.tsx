"use client";
/**
 * `/jobs/[id]/result` (UI-SPEC §5): the redacted video, the audit summary, the
 * embedded privacy receipt, and Publish to Sigmora only when opened from it.
 */
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { getClient } from "@/lib/client";
import { URL_REFRESH_MS } from "@/lib/polling";
import type { ResultResponse } from "@/lib/contracts";
import { COPY, auditSummary, formatLocal } from "@/lib/copy";
import { SITE, fromSigmora, keptQuery } from "@/lib/site";
import { useCooldown } from "@/hooks/useCooldown";
import { useJob } from "@/hooks/useJob";
import { useRemoteCaptions } from "@/hooks/useRemoteCaptions";
import { CheckIcon, WarningIcon } from "../icons";
import { useMode, useReportMode } from "../mode";
import { StageList } from "../StageList";
import { ActionError, ConfirmDialog, MessagePage, btn } from "../ui";
import { FailedJob } from "./FailedJob";
import { JobSkeleton, loadMessage } from "./JobPage";

const RECEIPT_TIMEOUT_MS = 15_000;

/** `video` and `receipt` are the URLs the player and the iframe use: a link refresh leaves them alone. */
type ResultLoad = { kind: "idle" } | { kind: "ready"; result: ResultResponse; video: string; receipt: string } | { kind: "error"; error: unknown };

/** Tells Sigmora the result is approved: to the opener when there is one, otherwise by returning to Sigmora. */
export function publishToSigmora(result: Pick<ResultResponse, "job_id" | "video_url" | "receipt_json_url">): void {
  const origin = new URL(SITE.sigmoraUrl).origin;
  const message = { type: "safecut:publish", job_id: result.job_id, video_url: result.video_url, receipt_json_url: result.receipt_json_url };
  if (window.opener && window.opener !== window) {
    (window.opener as Window).postMessage(message, origin);
    return;
  }
  window.open(new URL(`/safecut/return?job_id=${encodeURIComponent(result.job_id)}`, SITE.sigmoraUrl).toString(), "_self");
}

export function ResultPage() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const sigmora = fromSigmora(params);
  const { load, resume, markDeleted } = useJob(id);
  const job = load.kind === "ready" ? load.job : null;
  const [result, setResult] = useState<ResultLoad>({ kind: "idle" });
  /** Signed URLs expire: a media error refetches the result once for fresh ones (§10.7). */
  const [mediaRefreshes, setMediaRefreshes] = useState(0);
  const [mediaFailed, setMediaFailed] = useState(false);
  /** Refetches for fresh download and receipt links, without reloading what's already playing. */
  const [linkRefreshes, setLinkRefreshes] = useState(0);
  const keepMedia = useRef(false);
  const [receiptFailed, setReceiptFailed] = useState(false);
  const [receiptLoaded, setReceiptLoaded] = useState(false);
  const receiptRetried = useRef(false);
  const receiptLoadedRef = useRef(false);
  const videoRetried = useRef(false);
  /** Bumped by "Try again" on a result error: a fresh fetch with its one-time retries restored. */
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    videoRetried.current = false;
    receiptRetried.current = false;
    receiptLoadedRef.current = false;
    keepMedia.current = false;
  }, [attempt]);
  const latest = result.kind === "ready" ? result.result : null;
  const captions = useRemoteCaptions(latest?.captions_url);
  // An iframe fires no error event for HTTP failures, so a receipt that hasn't loaded in time counts
  // as failed (§5.4), after one refetch in case its signed URL had expired (§10.7).
  useEffect(() => {
    if (!latest || receiptLoaded) return;
    const t = setTimeout(() => {
      if (receiptRetried.current) {
        setReceiptFailed(true);
        return;
      }
      receiptRetried.current = true;
      keepMedia.current = true;
      setLinkRefreshes((n) => n + 1);
    }, RECEIPT_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [latest, receiptLoaded]);
  useEffect(() => {
    if (!latest) return;
    const t = setTimeout(() => {
      keepMedia.current = true;
      setLinkRefreshes((n) => n + 1);
    }, URL_REFRESH_MS);
    return () => clearTimeout(t);
  }, [latest]);
  const [published, setPublished] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const { coolingDown, coolDown } = useCooldown();
  const { replay } = useMode();
  useReportMode(job?.mode ?? (result.kind === "ready" ? result.result.mode : null));

  const status = job?.status;
  const redirect = status === "processing" || status === "review" || status === "needs_you" || status === "retry_later";
  useEffect(() => {
    if (redirect) router.replace(`/jobs/${encodeURIComponent(id)}${keptQuery(params)}`);
  }, [redirect, router, id, params]);

  useEffect(() => {
    if (status !== "done") return;
    const controller = new AbortController();
    const keep = keepMedia.current;
    keepMedia.current = false;
    getClient()
      .getResult(id, controller.signal)
      .then((r) => {
        setResult((prev) =>
          keep && prev.kind === "ready"
            ? { kind: "ready", result: r, video: prev.video, receipt: receiptLoadedRef.current ? prev.receipt : r.receipt_html_url }
            : { kind: "ready", result: r, video: r.video_url, receipt: r.receipt_html_url },
        );
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        // A failed link refresh keeps the page; only the receipt it was retrying gives up.
        if (keep && receiptRetried.current && !receiptLoadedRef.current) setReceiptFailed(true);
        setResult((prev) => (keep && prev.kind === "ready" ? prev : { kind: "error", error }));
      });
    return () => controller.abort();
  }, [id, status, mediaRefreshes, linkRefreshes, attempt]);

  /** "Try again" on a result error: start over with fresh URLs and fresh retries. */
  const retryResult = () => {
    setMediaFailed(false);
    setReceiptFailed(false);
    setReceiptLoaded(false);
    setResult({ kind: "idle" });
    setAttempt((n) => n + 1);
    resume();
  };

  if (load.kind === "loading" || redirect) return <JobSkeleton />;
  if (load.kind !== "ready") return loadMessage(load.kind, resume);
  const j = load.job;
  if (j.status === "rendering") {
    return (
      <section className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-2xl font-semibold">Your clip is being rendered</h1>
        <div className="mt-6">
          <StageList kind="render" active={j.stage === "audit" || j.stage === "receipt" ? j.stage : "render"} auditPatch={j.stage_reason === "audit_patch"} />
        </div>
      </section>
    );
  }
  if (j.status === "failed") return <FailedJob jobId={id} job={j} onResume={resume} onDeleted={markDeleted} />;
  if (j.status === "created") return <MessagePage message={COPY.created} actions={[{ label: "Upload again", href: "/try" }]} />;
  if (j.status !== "done") return loadMessage("unexpected", resume);
  if (result.kind === "error") {
    const e = result.error instanceof ApiError ? result.error : null;
    return loadMessage(e?.status === 404 ? (e.code === "expired" ? "expired" : "not_found") : e?.kind === "network" || e?.kind === "timeout" ? "unreachable" : "unexpected", retryResult);
  }
  if (result.kind !== "ready") return <JobSkeleton />;

  if (mediaFailed) return loadMessage("unexpected", retryResult);
  const r = result.result;
  const summary = auditSummary(r.audit, j.job?.frames ?? r.frames);
  const doDelete = async () => {
    setConfirm(false);
    // A fresh attempt: an identical error is announced and focused again.
    setDeleteError(null);
    try {
      await getClient().deleteJob(id);
      markDeleted();
    } catch (error) {
      const limited = error instanceof ApiError && error.status === 429;
      if (limited) coolDown(error.retryAfterS);
      setDeleteError(limited ? COPY.rateLimited : COPY.unexpected);
    }
  };

  return (
    <section className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="text-3xl font-semibold tracking-tight">Your clip is ready</h1>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div>
          <video
            className="aspect-video w-full rounded-xl bg-black"
            src={result.video}
            controls
            playsInline
            preload="metadata"
            aria-label="Your clip after Safe Cut"
            // A source that loads re-arms the one refresh, for when its signed URL expires later.
            onLoadedMetadata={() => {
              videoRetried.current = false;
            }}
            onError={() => {
              if (videoRetried.current) {
                setMediaFailed(true);
                return;
              }
              videoRetried.current = true;
              setMediaRefreshes((n) => n + 1);
            }}
          >
            {captions && <track kind="captions" src={captions} srcLang="en" label="English" default />}
          </video>
        </div>
        <div className="flex flex-col gap-4">
          <div role="status" className={`rounded-xl border p-4 ${summary.publishable ? "border-kept-fg/30 bg-kept-bg text-kept-fg" : "border-needs-fg/30 bg-needs-bg text-needs-fg"}`}>
            <p className="flex items-center gap-2 font-semibold">
              {summary.publishable ? <CheckIcon /> : <WarningIcon />} {summary.title}
            </p>
            {summary.lines.map((l) => (
              <p key={l} className="mt-1">
                {l}
              </p>
            ))}
            {summary.state === "unresolved" && (
              <Link href={`/jobs/${encodeURIComponent(id)}?view=review${sigmora ? "&from=sigmora" : ""}`} className={`${btn.secondary} mt-3`}>
                Review them
              </Link>
            )}
            <button type="button" className="mt-2 min-h-11 text-sm underline underline-offset-2 lg:min-h-8" aria-expanded={detailOpen} onClick={() => setDetailOpen((v) => !v)}>
              What the check does →
            </button>
            {detailOpen && <p className="mt-1 text-sm">{summary.detail}</p>}
          </div>
          {/* Browsers ignore `download` on another origin's URL: a new tab beats leaving this page. */}
          <a href={r.video_url} download target="_blank" rel="noopener noreferrer" className={btn.primary}>
            Download video
          </a>
          {!summary.publishable && <p className="text-sm text-muted">This version has {summary.unfixedSpots} unfixed {summary.unfixedSpots === 1 ? "spot" : "spots"}.</p>}
          {sigmora &&
            (replay ? (
              <p className="text-sm text-muted">Publishing is off in demo mode.</p>
            ) : published ? (
              <p role="status">Sent to Sigmora. You can close this tab.</p>
            ) : (
              <button
                type="button"
                className={btn.secondary}
                disabled={!summary.publishable}
                title={summary.publishable ? undefined : "Publishing is off until every spot is fixed."}
                aria-describedby={summary.publishable ? undefined : "publish-off"}
                onClick={() => {
                  publishToSigmora(r);
                  setPublished(true);
                }}
              >
                Publish to Sigmora
              </button>
            ))}
          {sigmora && !summary.publishable && (
            <p id="publish-off" className="text-sm text-muted">
              Publishing is off until every spot is fixed.
            </p>
          )}
          <Link href={`/jobs/${encodeURIComponent(id)}?view=review${sigmora ? "&from=sigmora" : ""}`} className={btn.link}>
            Back to review
          </Link>
        </div>
      </div>

      <div className="mt-10">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold">Privacy receipt</h2>
          <a href={r.receipt_json_url} download target="_blank" rel="noopener noreferrer" className={btn.secondary}>
            Download receipt (JSON)
          </a>
        </div>
        <p className="mt-1 text-muted">A record of what was hidden, why, and who approved it. Keep it if anyone asks about this video.</p>
        {receiptFailed ? (
          <p className="mt-3">The receipt didn&apos;t load. You can still download it as JSON.</p>
        ) : (
          <iframe
            title="Privacy receipt"
            src={result.receipt}
            sandbox=""
            referrerPolicy="no-referrer"
            className="mt-3 h-[28rem] w-full rounded-xl border border-border bg-white"
            onLoad={() => {
              receiptLoadedRef.current = true;
              setReceiptLoaded(true);
            }}
          />
        )}
        <a href={r.receipt_html_url} target="_blank" rel="noopener noreferrer" className={btn.link}>
          Open the receipt in a new tab
        </a>
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6">
        <p className="text-sm text-muted">This clip and everything Safe Cut made from it will be deleted from Safe Cut&apos;s servers by {formatLocal(r.deletes_at)}.</p>
        <div className="flex items-center gap-3">
          {deleteError && <ActionError message={deleteError} className="text-sm" />}
          <button type="button" className={btn.danger} disabled={coolingDown} onClick={() => setConfirm(true)}>
            Delete everything now
          </button>
        </div>
      </div>
      <ConfirmDialog
        open={confirm}
        title="Delete everything now?"
        body="Delete the video, the receipt and all working files now? Download anything you need first. This can't be undone."
        confirm="Delete"
        cancel="Cancel"
        onConfirm={() => void doDelete()}
        onCancel={() => setConfirm(false)}
      />
    </section>
  );
}
