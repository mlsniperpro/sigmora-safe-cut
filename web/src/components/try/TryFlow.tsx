"use client";
/**
 * `/try` (UI-SPEC §2): access code → drop a clip → upload and start → stage
 * progress, then on to the review panel. Every refusal follows §2.6 / §10.3.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import type { JobResponse } from "@/lib/contracts";
import { getClient } from "@/lib/client";
import { COPY, codeWindowMessage, formatLocal } from "@/lib/copy";
import { CODE_MAX_LENGTH, checkFiles, durationProblem, normaliseCode, sizeMb } from "@/lib/upload";
import { useCooldown } from "@/hooks/useCooldown";
import { useJob } from "@/hooks/useJob";
import { SITE, keptQuery } from "@/lib/site";
import { ProgressView, fmtDuration } from "../job/ProgressView";
import { btn } from "../ui";
import { useMode, useReportMode } from "../mode";

type Step = "code" | "file" | "progress" | "deleted";

interface Refusal {
  message: string;
  /** Start stays disabled (until `until` when set). */
  blockStart: boolean;
  until?: number | null;
  /** Offer [Use a different code] (the step-B refusal pattern). */
  differentCode?: boolean;
  homeLink?: boolean;
  tryAnother?: boolean;
  retryUpload?: boolean;
}

const METADATA_TIMEOUT_MS = 10_000;

/** Reads a clip's duration from a hidden `<video preload="metadata">`; null when unknown (§10.2). */
function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.muted = true;
    const done = (d: number | null) => {
      clearTimeout(t);
      URL.revokeObjectURL(url);
      v.removeAttribute("src");
      resolve(d);
    };
    const t = setTimeout(() => done(null), METADATA_TIMEOUT_MS);
    v.onloadedmetadata = () => done(Number.isFinite(v.duration) ? v.duration : null);
    v.onerror = () => done(null);
    v.src = url;
  });
}


export function TryFlow() {
  const router = useRouter();
  const { report: reportMode } = useMode();
  const [step, setStep] = useState<Step>("code");
  const [code, setCode] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [openWeight, setOpenWeight] = useState(false);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  /** A 429 on Continue holds it until Retry-After (or 60 s), like every other POST (§10.3). */
  const { coolingDown: continueCooling, coolDown: coolContinue } = useCooldown();
  const codeInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [contentType, setContentType] = useState<string>("video/mp4");
  const [duration, setDuration] = useState<number | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [rights, setRights] = useState(false);
  const [rightsError, setRightsError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const chooseButton = useRef<HTMLButtonElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const rightsBox = useRef<HTMLInputElement>(null);

  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState(false);
  const uploadAbort = useRef<AbortController | null>(null);
  const deletedByUser = useRef(false);
  /**
   * A confirmed delete still on its way: whether it worked. Until it answers, nothing new is sent
   * and the page doesn't move on; if it fails, the page carries on as it was (§10.3 Delete row).
   */
  const pendingDelete = useRef<Promise<boolean> | null>(null);
  /** Where the job moved on to while a delete was pending: followed if the delete fails. */
  const heldNavigation = useRef<string | null>(null);
  const [started, setStarted] = useState(false);
  /** `POST /start` timed out or the network failed: the server may have taken it, so poll (§10.3). */
  const [startUnsure, setStartUnsure] = useState(false);
  const section = useRef<HTMLElement>(null);
  const previousStep = useRef<Step>("code");
  // Move focus with the step, so it never falls to <body> when the focused button unmounts (§2.8).
  useEffect(() => {
    if (previousStep.current === step) return;
    previousStep.current = step;
    const target = step === "file" ? chooseButton.current : step === "code" ? codeInput.current : section.current?.querySelector<HTMLElement>("[data-step-heading]");
    target?.focus();
  }, [step]);
  // Only compared against a refusal's `until`, which the timer below refreshes.
  const [now, setNow] = useState(0);
  const ids = { code: useId(), codeErr: useId(), file: useId(), rights: useId(), rightsErr: useId() };

  // A refusal that disables Start would drop focus to the page with it: the refusal takes it (WCAG 2.4.3).
  const refusalBox = useRef<HTMLDivElement>(null);
  const startButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (refusal?.blockStart && step === "file") refusalBox.current?.focus();
  }, [refusal, step]);

  // Re-enable a time-limited Start when its time comes.
  useEffect(() => {
    if (!refusal?.until) return;
    // A time already past (a stale `retry_at`, `Retry-After: 0`) re-enables it at once.
    const t = setTimeout(() => setNow(Date.now()), Math.max(0, refusal.until - Date.now()));
    return () => clearTimeout(t);
  }, [refusal]);

  const deleteQuietly = useCallback((id: string) => {
    // The automatic step-B delete fails silently; the 24 h cleanup is the backstop (§10.3).
    void getClient().deleteJob(id).catch(() => undefined);
  }, []);

  // ------------------------------------------------------------------ step A
  const onContinue = async () => {
    if (checking || continueCooling) return;
    const value = normaliseCode(code);
    if (!value) {
      setCodeError(COPY.emptyCode);
      codeInput.current?.focus();
      return;
    }
    setChecking(true);
    setCodeError(null);
    try {
      const check = await getClient().checkCode(value);
      setOpenWeight(check.open_weight);
      setCode(value);
      setStep("file");
      setRefusal(null);
    } catch (error) {
      const e = error instanceof ApiError ? error : null;
      if (e?.status === 401 && e.code === "code_not_active") {
        setCodeError(codeWindowMessage(e.detail?.valid_from, e.detail?.valid_until, Date.now(), (iso) => formatLocal(iso)));
        codeInput.current?.focus();
      } else if (e?.status === 401) {
        setCodeError(COPY.wrongCode);
        codeInput.current?.focus();
        codeInput.current?.select();
      } else if (e?.status === 429) {
        setCodeError(COPY.rateLimited);
        coolContinue(e.retryAfterS ?? null);
      } else if (e?.kind === "network" || e?.kind === "timeout") {
        setCodeError(COPY.unreachable);
      } else {
        setCodeError(COPY.unexpected);
      }
    } finally {
      setChecking(false);
    }
  };

  // ------------------------------------------------------------------ step B
  const acceptFiles = async (list: FileList | File[]) => {
    const files = Array.from(list);
    setFileError(null);
    setRefusal((r) => (r?.blockStart ? r : null));
    const check = checkFiles(files);
    if (!check.ok) {
      setFile(null);
      setFileError(check.problem.message);
      chooseButton.current?.focus();
      return;
    }
    const f = files[0] as File;
    const d = await readDuration(f);
    const tooLong = durationProblem(d);
    if (tooLong) {
      setFile(null);
      setFileError(tooLong);
      chooseButton.current?.focus();
      return;
    }
    setFile(f);
    setContentType(check.contentType);
    setDuration(d);
    setJobId(null);
    setUploaded(false);
  };

  const refuse = (r: Refusal, id: string | null, deleteJob: boolean) => {
    setRefusal(r);
    if (deleteJob && id) {
      deleteQuietly(id);
      setJobId(null);
      setUploaded(false);
    }
  };

  /** Maps an error on `POST /v1/jobs`, the upload or `POST /start` to the §2.6 row. */
  const handleStartError = (error: unknown, id: string | null) => {
    const e = error instanceof ApiError ? error : null;
    if (e?.status === 401) {
      const message = e.code === "code_not_active" ? codeWindowMessage(e.detail?.valid_from, e.detail?.valid_until, Date.now(), (iso) => formatLocal(iso)) : COPY.wrongCode;
      return refuse({ message, blockStart: true, differentCode: true }, id, true);
    }
    if (e?.status === 413) return refuse({ message: `This file is ${sizeMb(e.detail?.size_bytes ?? file?.size ?? 0)} MB. The limit is 150 MB.`, blockStart: false }, id, false);
    if (e?.status === 409 && e.code === "upload_incomplete") return refuse({ message: COPY.uploadIncomplete, blockStart: true, tryAnother: true }, id, true);
    if (e?.status === 422 && e.code === "job_cap") {
      refuse({ message: COPY.jobCapTry, blockStart: false }, id, true);
      setFile(null);
      return;
    }
    if (e?.status === 429) {
      if (e.code === "daily_cap") return refuse({ message: COPY.dailyCapTry, blockStart: true, until: e.detail?.retry_at ? Date.parse(e.detail.retry_at) : null, homeLink: true }, id, false);
      if (e.code === "code_cap") return refuse({ message: COPY.codeCapTry, blockStart: false }, id, false);
      if (e.code === "pilot_pool_cap") return refuse({ message: COPY.pilotPoolTry, blockStart: true }, id, true);
      return refuse({ message: COPY.rateLimited, blockStart: true, until: Date.now() + (e.retryAfterS ?? 60) * 1000 }, id, false);
    }
    if (e?.status === 503) return refuse({ message: e.code === "billing" ? COPY.billing : COPY.auditorUnavailable, blockStart: false }, id, false);
    if (e?.kind === "network" || e?.kind === "timeout") return refuse({ message: COPY.unreachable, blockStart: false }, id, false);
    return refuse({ message: COPY.unexpected, blockStart: false }, id, false);
  };

  const onStart = async () => {
    if (!file || busy) return;
    if (!rights) {
      setRightsError(COPY.noRights);
      rightsBox.current?.focus();
      return;
    }
    setRightsError(null);
    setRefusal(null);
    setStartUnsure(false);
    setBusy(true);
    const client = getClient();
    let id = jobId;
    try {
      if (!id || !uploaded) {
        const created = await client.createJob({ code, size_bytes: file.size, content_type: contentType, file_name: file.name });
        // Demo mode shows from the first response that says so, not only once polling starts (§6).
        reportMode(created.mode);
        id = created.job_id;
        setJobId(id);
        setStep("progress");
        setUploadPercent(0);
        const controller = new AbortController();
        uploadAbort.current = controller;
        try {
          await client.upload(created.upload_url, file, contentType, (p) => setUploadPercent(Math.round(p * 100)), controller.signal);
        } catch {
          // Cancelled by the creator's own delete: the "Deleted" page stays, nothing is retried.
          if (deletedByUser.current) return;
          setStep("file");
          setUploadPercent(null);
          refuse({ message: COPY.uploadStalled, blockStart: true, retryUpload: true }, id, false);
          return;
        }
        setUploaded(true);
      }
      if (pendingDelete.current) await pendingDelete.current;
      if (deletedByUser.current) return;
      setStep("progress");
      setUploadPercent(100);
      try {
        await client.startJob(id);
      } catch (error) {
        const e = error instanceof ApiError ? error : null;
        if (e?.kind === "network" || e?.kind === "timeout") setStartUnsure(true);
        // A 409 other than an unfinished upload means it's already running (a re-pressed Start
        // after a timeout, §10.3): follow it like an accepted start.
        if (!(e?.status === 409 && e.code !== "upload_incomplete")) throw error;
      }
      if (deletedByUser.current) return;
      // Poll only once the job has really started: before that the server says "created",
      // which stops polling (§10.4).
      setStarted(true);
    } catch (error) {
      if (deletedByUser.current) return;
      setStep("file");
      setUploadPercent(null);
      handleStartError(error, id);
    } finally {
      setBusy(false);
    }
  };

  const retryUpload = async () => {
    if (jobId) deleteQuietly(jobId);
    setJobId(null);
    setUploaded(false);
    setRefusal(null);
    // Its button goes with the refusal: focus moves to Start (enabled again once the refusal has
    // gone), the button the retry stands for, so a refusal of the retry leaves it there (WCAG 2.4.3).
    requestAnimationFrame(() => startButton.current?.focus());
    await onStart();
  };

  const switchCode = () => {
    setStep("code");
    setRefusal(null);
    setTimeout(() => codeInput.current?.focus(), 0);
  };

  /** Back to step A with nothing kept: the same URL, so a link wouldn't remount the page. */
  const startOver = () => {
    deletedByUser.current = false;
    uploadAbort.current = null;
    setFile(null);
    setDuration(null);
    setFileError(null);
    setRights(false);
    setRightsError(null);
    setRefusal(null);
    setJobId(null);
    setUploaded(false);
    setStarted(false);
    setUploadPercent(null);
    setStep("code");
  };

  // Busy only looks disabled (`aria-disabled`): a refusal that keeps this step must leave focus on
  // the button, and a disabled one drops it to the page (WCAG 2.4.3).
  const startDisabled = !file || (refusal?.blockStart === true && !(refusal.until && now >= refusal.until));

  if (step === "deleted") {
    return (
      <section ref={section} className="mx-auto max-w-2xl px-4 py-16">
        <div role="status">
          <h1 data-step-heading tabIndex={-1} className="text-xl font-medium">
            {COPY.deleted}
          </h1>
        </div>
        <button type="button" className={`${btn.secondary} mt-6`} onClick={startOver}>
          Try another clip
        </button>
      </section>
    );
  }

  return (
    <section ref={section} className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Try Safe Cut on your own clip</h1>

      {step === "code" && (
        <form
          className="mt-8"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void onContinue();
          }}
        >
          <label htmlFor={ids.code} className="block font-medium">
            Access code
          </label>
          <div className="mt-2 flex flex-wrap gap-2">
            <input
              ref={codeInput}
              id={ids.code}
              name="access-code"
              type="text"
              className={`min-h-11 w-full max-w-sm rounded-lg border border-field bg-surface px-3 ${showCode ? "" : "masked"}`}
              value={code}
              maxLength={CODE_MAX_LENGTH}
              autoComplete="off"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              aria-invalid={codeError ? true : undefined}
              aria-describedby={`${codeError ? ids.codeErr : ""} code-hint`.trim()}
              onChange={(e) => setCode(e.target.value)}
            />
            <button type="button" className={btn.secondary} aria-pressed={showCode} onClick={() => setShowCode((v) => !v)}>
              {showCode ? "Hide" : "Show"}
            </button>
            <button type="submit" className={btn.primary} aria-disabled={checking || continueCooling || undefined}>
              {checking ? "Checking…" : "Continue"}
            </button>
          </div>
          <p id="code-hint" className="mt-2 text-sm text-muted">
            Judges: the code is in the submission&apos;s testing instructions.
          </p>
          <p id={ids.codeErr} role="alert" className="mt-2 text-danger empty:hidden">
            {codeError}
          </p>
          <DataBullets />
        </form>
      )}

      {step === "file" && (
        <div className="mt-8">
          {refusal && (
            <div ref={refusalBox} role="alert" tabIndex={-1} className="mb-4 rounded-lg border border-danger bg-danger-bg p-3">
              <p>{refusal.message}</p>
              <p className="mt-2 flex flex-wrap gap-3">
                {refusal.differentCode && (
                  <button type="button" className={btn.link} onClick={switchCode}>
                    Use a different code
                  </button>
                )}
                {refusal.homeLink && (
                  <Link href="/" className={btn.link}>
                    Watch the demo on the home page
                  </Link>
                )}
                {refusal.retryUpload && (
                  <button type="button" className={btn.secondary} onClick={() => void retryUpload()}>
                    Try again
                  </button>
                )}
                {refusal.tryAnother && (
                  <button
                    type="button"
                    className={btn.secondary}
                    onClick={() => {
                      setFile(null);
                      setRefusal(null);
                      chooseButton.current?.focus();
                    }}
                  >
                    Try another clip
                  </button>
                )}
              </p>
            </div>
          )}
          <div
            className={`flex flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center ${dragging ? "border-accent bg-surface-2" : "border-border bg-surface"}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              void acceptFiles(e.dataTransfer.files);
            }}
          >
            <p>
              Drop a clip here, or{" "}
              <button ref={chooseButton} type="button" className={btn.secondary} aria-describedby={`${ids.file} limits`} onClick={() => fileInput.current?.click()}>
                Choose a file
              </button>
            </p>
            <p id="limits" className="text-sm text-muted">
              Up to 60 seconds and 150 MB. MP4 or MOV.
            </p>
            <input
              ref={fileInput}
              type="file"
              accept="video/mp4,video/quicktime,.mp4,.mov"
              className="sr-only"
              tabIndex={-1}
              aria-hidden="true"
              onChange={(e) => {
                if (e.target.files) void acceptFiles(e.target.files);
                e.target.value = "";
              }}
            />
            {file && (
              // A long unbroken file name wraps rather than widening the page at 320 px (§9).
              <p className="font-medium [overflow-wrap:anywhere]">
                {file.name}
                {duration !== null ? ` · ${fmtDuration(duration)}` : ""}
              </p>
            )}
            <p id={ids.file} role="alert" className="text-danger empty:hidden">
              {fileError}
            </p>
          </div>
          <p className="mt-4 text-sm text-muted">
            {openWeight ? "Sampled frames of the result also go to Baseten, which runs Muse Spark Open." : "Your clip is never sent to Baseten or any open-weight model."}
          </p>
          <div className="mt-4 flex items-start gap-2">
            <input
              ref={rightsBox}
              id={ids.rights}
              type="checkbox"
              className="mt-1 h-5 w-5"
              checked={rights}
              aria-describedby={rightsError ? ids.rightsErr : undefined}
              onChange={(e) => {
                setRights(e.target.checked);
                if (e.target.checked) setRightsError(null);
              }}
            />
            <label htmlFor={ids.rights}>
              I&apos;m 18 or over, I have the right to upload this clip and the people in it, and I&apos;m not in a{" "}
              <a href={SITE.geoPolicyUrl} className="underline underline-offset-2" target="_blank" rel="noopener noreferrer">
                territory where Meta&apos;s API is restricted
              </a>
              .
            </label>
          </div>
          <p className="mt-1 pl-7 text-sm text-muted">
            By uploading you agree to Meta&apos;s{" "}
            <a href={SITE.metaTermsUrl} className="underline underline-offset-2" target="_blank" rel="noopener noreferrer">
              Terms
            </a>{" "}
            and{" "}
            <a href={SITE.metaAupUrl} className="underline underline-offset-2" target="_blank" rel="noopener noreferrer">
              Acceptable Use Policy
            </a>{" "}
            and our{" "}
            <Link href="/privacy" className="underline underline-offset-2">
              Privacy page
            </Link>
            .
          </p>
          <p id={ids.rightsErr} role="alert" className="mt-1 text-danger empty:hidden">
            {rightsError}
          </p>
          <div className="mt-6 flex justify-end">
            <button ref={startButton} type="button" className={btn.primary} disabled={startDisabled} aria-disabled={busy || undefined} onClick={() => void onStart()}>
              Start
            </button>
          </div>
          <DataBullets />
        </div>
      )}

      {/* A start the server may have taken anyway: the next GET says so (§10.3). */}
      {step === "file" && startUnsure && jobId && (
        <JobPoller
          jobId={jobId}
          onJob={(j) => {
            if (j.status === "created") return;
            setStartUnsure(false);
            setRefusal(null);
            setStep("progress");
            setUploadPercent(100);
            setStarted(true);
          }}
        />
      )}

      {step === "progress" && jobId && <Progress jobId={jobId} started={started} fileName={file?.name ?? ""} duration={duration} uploadPercent={uploadPercent} onDeleting={(done) => {
            pendingDelete.current = done;
            void done.then((ok) => {
              pendingDelete.current = null;
              const held = heldNavigation.current;
              heldNavigation.current = null;
              if (!ok) {
                if (held) router.push(held);
                return;
              }
              deletedByUser.current = true;
              uploadAbort.current?.abort();
            });
          }} onDeleted={() => setStep("deleted")} onNavigate={(path) => {
            if (deletedByUser.current) return;
            // The job page keeps `from` and `demo` (§10.4). Read at navigation time, so /try stays static.
            const href = `${path}${keptQuery(new URLSearchParams(window.location.search))}`;
            if (pendingDelete.current) heldNavigation.current = href;
            else router.push(href);
          }} />}
    </section>
  );
}

function DataBullets() {
  return (
    <div className="mt-10 rounded-xl border border-border bg-surface p-5">
      <h2 className="font-semibold">What happens to your clip</h2>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
        <li>It&apos;s sent to Meta&apos;s Model API using Standard model IDs only, never a Contributor model ID. Meta says it doesn&apos;t use content from its Standard services to train its models.</li>
        <li>Your clip, the result and the receipt are deleted from Safe Cut&apos;s servers after 24 hours, or sooner if you choose.</li>
        <li>Up to 60 seconds and 150 MB. MP4 or MOV.</li>
      </ul>
    </div>
  );
}

/** Polls the job once the upload is done and hands each response up; renders nothing. */
function JobPoller({
  jobId,
  onJob,
  onFailed,
  pollCreated = false,
}: {
  jobId: string;
  onJob: (job: JobResponse) => void;
  /** Polling stopped on an error (§10.3: retries spent, or a second 5xx in a row). */
  onFailed?: () => void;
  pollCreated?: boolean;
}) {
  const { load } = useJob(jobId, { pollCreated });
  const job = load.kind === "ready" ? load.job : null;
  const failed = load.kind !== "ready" && load.kind !== "loading" && load.kind !== "deleted";
  useReportMode(job?.mode, job?.synthetic);
  useEffect(() => {
    if (job) onJob(job);
  }, [job, onJob]);
  useEffect(() => {
    if (failed) onFailed?.();
  }, [failed, onFailed]);
  return null;
}

function Progress({
  jobId,
  started,
  fileName,
  duration,
  uploadPercent,
  onDeleting,
  onDeleted,
  onNavigate,
}: {
  jobId: string;
  started: boolean;
  fileName: string;
  duration: number | null;
  uploadPercent: number | null;
  onDeleting: (done: Promise<boolean>) => void;
  onDeleted: () => void;
  onNavigate: (href: string) => void;
}) {
  const [job, setJob] = useState<JobResponse | null>(null);
  const uploading = uploadPercent !== null && uploadPercent < 100;
  // The upload lives in this page: the browser asks before a reload or close would stop it.
  useEffect(() => {
    if (!uploading) return;
    const hold = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", hold);
    return () => window.removeEventListener("beforeunload", hold);
  }, [uploading]);
  const onJob = useCallback(
    (j: JobResponse) => {
      setJob(j);
      if (!["processing", "retry_later", "created"].includes(j.status)) onNavigate(`/jobs/${encodeURIComponent(jobId)}`);
    },
    [jobId, onNavigate],
  );
  // The job page shows the §7 message with [Try again], and keeps the review link.
  const onFailed = useCallback(() => onNavigate(`/jobs/${encodeURIComponent(jobId)}`), [jobId, onNavigate]);
  const stage = uploading ? "uploading" : started && job?.stage && job.stage !== "review" ? job.stage : "queued";
  return (
    <>
      {started && <JobPoller jobId={jobId} onJob={onJob} onFailed={onFailed} pollCreated />}
      <ProgressView
        fileName={fileName}
        duration={duration}
        active={stage}
        {...(uploading && { uploadPercent: uploadPercent ?? 0 })}
        jobId={jobId}
        etaS={uploading ? null : (job?.eta_s ?? null)}
        busy={job?.status === "retry_later"}
        firstFrameUrl={job?.job?.prepared_url ?? null}
        onDeleting={onDeleting}
        onDeleted={onDeleted}
      />
    </>
  );
}
