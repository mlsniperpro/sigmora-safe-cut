"use client";
/**
 * `/jobs/[id]` (UI-SPEC §10.4): one page, many states, driven by the server's
 * status. `done` moves to the result unless opened with `?view=review`.
 */
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { COPY } from "@/lib/copy";
import { keptQuery } from "@/lib/site";
import { checkTimeline } from "@/lib/time";
import { useJob, type JobLoad } from "@/hooks/useJob";
import { useReportMode } from "../mode";
import { ReviewPanel } from "../review/ReviewPanel";
import { StageList } from "../StageList";
import { MessagePage } from "../ui";
import { FailedJob } from "./FailedJob";

export function loadMessage(kind: Exclude<JobLoad["kind"], "loading" | "ready">, retry: () => void): React.ReactNode {
  switch (kind) {
    case "expired":
      return <MessagePage message={COPY.expired} actions={[{ label: "Try another clip", href: "/try" }]} />;
    case "not_found":
      return <MessagePage message={COPY.notFound} actions={[{ label: "Try another clip", href: "/try" }]} />;
    case "unreachable":
      return <MessagePage message={COPY.unreachable} actions={[{ label: "Try again", onClick: retry }, { label: "Watch the demo", href: "/" }]} />;
    case "deleted":
      return <MessagePage message={COPY.deleted} actions={[{ label: "Try another clip", href: "/try" }]} />;
    case "unexpected":
      return <MessagePage message={COPY.unexpected} actions={[{ label: "Try again", onClick: retry }, { label: "Go to the home page", href: "/" }]} />;
  }
}

export function JobSkeleton() {
  return (
    <div aria-busy="true" className="mx-auto max-w-6xl px-4 pt-6">
      <div className="aspect-video w-full rounded-xl bg-surface-2" />
      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-40 rounded-xl bg-surface-2" />
        ))}
      </div>
      <span className="sr-only">Loading your clip…</span>
    </div>
  );
}

export function JobPage() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const viewReview = params.get("view") === "review";
  const { load, resume, patch, markDeleted } = useJob(id);
  const job = load.kind === "ready" ? load.job : null;
  useReportMode(job?.mode);

  const toResult = job?.status === "done" && !viewReview;
  useEffect(() => {
    if (toResult) router.replace(`/jobs/${encodeURIComponent(id)}/result${keptQuery(params)}`);
  }, [toResult, router, id, params]);

  if (load.kind === "loading") return <JobSkeleton />;
  if (load.kind !== "ready") return loadMessage(load.kind, resume);
  const j = load.job;
  if (j.job && checkTimeline(j.job) !== null) {
    console.error(`job ${id}: prepared timeline failed the §3.6 checks`);
    return loadMessage("unexpected", resume);
  }
  switch (j.status) {
    case "created":
      return <MessagePage message={COPY.created} actions={[{ label: "Upload again", href: "/try" }]} />;
    case "processing":
    case "retry_later":
      return (
        <section className="mx-auto max-w-3xl px-4 py-10">
          <h1 className="text-2xl font-semibold">Working on your clip</h1>
          {j.status === "retry_later" && (
            <p role="status" className="mt-4 rounded-lg bg-needs-bg p-3 text-needs-fg">
              {COPY.metaBusy}
            </p>
          )}
          <div className="mt-6">
            <StageList kind="pipeline" active={j.stage && j.stage !== "review" ? j.stage : "queued"} etaS={j.eta_s ?? null} />
          </div>
          <p className="mt-6 text-sm text-muted">You can leave this page and come back with this link.</p>
        </section>
      );
    case "failed":
      return <FailedJob job={j} onResume={resume} onDeleted={markDeleted} />;
    case "done":
      if (!viewReview) return <JobSkeleton />;
      return <ReviewPanel job={j} viewReview onPatchJob={patch} onResume={resume} onDeleted={markDeleted} />;
    default:
      return <ReviewPanel job={j} viewReview={viewReview} onPatchJob={patch} onResume={resume} onDeleted={markDeleted} />;
  }
}
