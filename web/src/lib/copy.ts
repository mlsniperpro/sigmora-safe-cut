/**
 * Copy-deck strings that depend on data (UI-SPEC §2.5, §2.6, §5.3, §7), kept in
 * one place so pages and tests agree on every word.
 */
import type { Audit, JobResponse, Stage } from "./contracts";
import { tooLongMessage, sizeMb } from "./upload";

export type ProgressStage = "uploading" | Stage;

export const STAGE_ROWS: ReadonlyArray<{ stage: ProgressStage; label: string; detail: string }> = [
  { stage: "uploading", label: "Uploading your clip", detail: "" },
  { stage: "queued", label: "Waiting to start", detail: "Usually a few seconds." },
  { stage: "prepare", label: "Getting your clip ready", detail: "Converting to a standard format and reading its frames." },
  { stage: "track", label: "Finding people and objects", detail: "SAM 3.1 is looking for faces, people, plates, screens and documents." },
  { stage: "transcribe", label: "Listening for who's speaking", detail: "Muse Voice Transcribe is noting who speaks, and when." },
  { stage: "scene", label: "Watching the whole clip", detail: "Muse Spark is working out what's happening and who the host is." },
  { stage: "roles", label: "Working out who's part of the story", detail: "Muse Spark is ruling on each labelled person and object, three times over." },
  { stage: "miss_loop", label: "Looking again for anything missed", detail: "Muse Spark spotted something SAM 3.1 didn't. Tracking it now." },
  { stage: "decide", label: "Deciding what to hide", detail: "Anything uncertain stays hidden until you decide." },
  { stage: "guard", label: "Adding a safety margin", detail: "Extending each cover a little in space and time so nothing slips out at the edges." },
];

export const RENDER_ROWS: ReadonlyArray<{ stage: Stage; label: string; detail: string }> = [
  { stage: "render", label: "Applying your choices", detail: "Covering each hidden item on every frame it appears in." },
  { stage: "audit", label: "Checking the result", detail: "Safe Cut's final check looks for anything that slipped through." },
  { stage: "receipt", label: "Writing your privacy receipt", detail: "" },
];

export const AUDIT_PATCH_ROW = { label: "Covering what the check found", detail: "The final check found something; covering it and checking again." };

export function stageLabel(stage: Stage | null | undefined): string {
  const row = [...STAGE_ROWS, ...RENDER_ROWS].find((r) => r.stage === stage);
  return row?.label ?? "Working on your clip";
}

// ------------------------------------------------------------------ failed jobs (§2.6, §10.3)

export type FailureAction = "try_again" | "try_again_tomorrow" | "try_another" | "delete";

export interface FailureView {
  message: string;
  actions: FailureAction[];
  /** For "Try again": re-render when the failed stage is render/audit/receipt, otherwise restart. */
  retry: "render" | "start" | null;
  /** [Try again tomorrow] stays disabled until this time. */
  retryAt: string | null;
}

export function failureView(job: Pick<JobResponse, "failure" | "retry_at" | "code_valid_until" | "has_render" | "stage">): FailureView {
  const reason = job.failure?.reason ?? null;
  const stage = job.failure?.stage ?? job.stage ?? null;
  const retry = stage === "render" || stage === "audit" || stage === "receipt" ? "render" : "start";
  const canStill = job.has_render ? "You can still download or delete it." : "You can still delete it.";
  const view = (message: string, actions: FailureAction[], r: FailureView["retry"] = null, retryAt: string | null = null): FailureView => ({ message, actions, retry: r, retryAt });
  switch (reason) {
    case "too_long":
      return view(tooLongMessage(job.failure?.duration_s), ["try_another", "delete"]);
    case "too_large":
      return view(job.failure?.size_bytes ? `This file is ${sizeMb(job.failure.size_bytes)} MB. The limit is 150 MB.` : "This file is larger than 150 MB.", ["try_another", "delete"]);
    case "bad_media":
      return view("Safe Cut couldn't read this video file. Try exporting it again as MP4 or MOV. Your clip hasn't been published anywhere.", ["try_another", "delete"]);
    case "job_cap":
      return view("This clip needs more processing than one job allows. Your clip hasn't been published anywhere. Try a shorter clip.", ["try_another", "delete"]);
    case "daily_cap": {
      if (expiresBefore(job.retry_at, job.code_valid_until)) {
        return view("Safe Cut has reached today's limit for the public demo, and this access code expires before the limit resets, so this can't be run again. Nothing has been published.", ["delete"]);
      }
      return view("Safe Cut has reached today's limit for the public demo. Your clip is fine; try it again tomorrow. Nothing has been published.", ["try_again_tomorrow", "delete"], retry, job.retry_at ?? null);
    }
    case "code_cap":
      return view("This access code ran out of budget. Ask the person who gave it to you to add more, then try again. Your clip hasn't been published anywhere.", ["try_again", "delete"], retry);
    case "code_not_active":
      return view(`This access code has expired, so Safe Cut can't run more work on this clip. ${canStill}`, ["delete"]);
    case "pilot_pool_cap":
      return view("The pilot budget has been used up, so this clip couldn't finish. Thank you for helping. Your clip hasn't been published anywhere.", ["delete"]);
    case "upstream":
      return view("Meta's service didn't recover in time. Nothing was published. You can try again.", ["try_again", "delete"], retry);
    case "config":
    case "bad_request":
    case "refusal":
    case "incomplete":
      return view("Safe Cut couldn't process this clip. Your clip hasn't been published anywhere. We've logged the problem.", ["try_another", "delete"]);
    case "internal":
    case null:
    default: {
      const label = stageLabel(stage);
      const lower = label.charAt(0).toLowerCase() + label.slice(1);
      return view(`Something went wrong while ${lower}. Your clip hasn't been published anywhere. You can try again, or delete it now.`, ["try_again", "delete"], retry);
    }
  }
}

/** §2.6.1 expiry rule: the earliest retry lands after the code's window closes. */
export function expiresBefore(retryAt: string | null | undefined, codeValidUntil: string | null | undefined): boolean {
  if (!retryAt || !codeValidUntil) return false;
  return Date.parse(retryAt) > Date.parse(codeValidUntil);
}

// ------------------------------------------------------------------ audit (§5.3, §5.6, §1.3)

export interface AuditSummary {
  state: "clean" | "fixed" | "unresolved" | "failed" | "over_budget";
  title: string;
  lines: string[];
  detail: string;
  publishable: boolean;
  uncheckedFrames: number;
  unfixedSpots: number;
  leaksFixed: number;
}

export function auditorName(model: string): "egoblur" | "yunet" {
  return model === "yunet-face" ? "yunet" : "egoblur";
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function auditSummary(audit: Audit, frames: number, budgetLine?: string | null): AuditSummary {
  const leaksFixed = new Set(audit.leaks.filter((l) => l.patched_item).map((l) => l.patched_item)).size;
  const unresolvedRows = audit.leaks.filter((l) => l.unresolved).length;
  const uncheckedFrames = Math.max(0, audit.unresolved - unresolvedRows);
  const unfixedSpots = audit.spots.length;
  const checked = `${audit.frames_scanned} of ${frames} frames checked.`;
  const who = auditorName(audit.egoblur.model);
  const detector =
    who === "yunet"
      ? `A face detector (YuNet) looked for faces on ${audit.frames_scanned} of the result's ${frames} frames.`
      : `Meta's EgoBlur looked for faces and number plates on ${audit.frames_scanned} of the result's ${frames} frames.`;
  const muse =
    who === "yunet"
      ? "Muse Spark looked at sampled frames for number plates and anything else it could read or recognise."
      : "Muse Spark looked at sampled frames and tried to read or recognise anything.";
  const detail = `${detector} It's meant to scan all of them; any frame it couldn't check counts as not checked, and publishing stays off until it is. ${muse} Anything they found that wasn't kept clear on purpose was covered, and the clip was rendered again.`;
  const base = { detail, uncheckedFrames, unfixedSpots, leaksFixed };
  switch (audit.blocked_reason) {
    case "unresolved_leaks":
      return {
        ...base,
        state: "unresolved",
        title: "Not ready to publish",
        lines: [checked, `${plural(unfixedSpots, "spot", "spots")} couldn't be fixed automatically. Publishing is off until they're fixed.`],
        publishable: false,
      };
    case "audit_failed":
      return { ...base, state: "failed", title: "Not ready to publish", lines: [`The final check couldn't finish on ${plural(uncheckedFrames, "frame", "frames")}. Publishing is off until it runs.`], publishable: false };
    case "over_budget":
      return {
        ...base,
        state: "over_budget",
        title: "Not ready to publish",
        lines: [`The final check ran out of budget on ${plural(uncheckedFrames, "frame", "frames")}. Publishing is off.`, ...(budgetLine ? [budgetLine] : [])],
        publishable: false,
      };
    default:
      if (audit.unresolved > 0) {
        return { ...base, state: "failed", title: "Not ready to publish", lines: [checked], publishable: false };
      }
      return leaksFixed > 0
        ? { ...base, state: "fixed", title: "Checked", lines: [checked, `${plural(leaksFixed, "leak", "leaks")} found and fixed. Nothing left to fix.`], publishable: true }
        : { ...base, state: "clean", title: "Checked", lines: [checked, "No leaks found."], publishable: true };
  }
}

/** The §5.3 second line for an over-budget audit. */
export function budgetCauseLine(cause: string | null | undefined, retryAt: string | null | undefined, codeValidUntil: string | null | undefined, formatTime: (iso: string) => string): string | null {
  switch (cause) {
    case "daily_cap":
      if (expiresBefore(retryAt, codeValidUntil)) return "Today's limit was reached, and this access code expires before then, so this can't be run again.";
      return retryAt ? `Today's limit was reached. You can run it again after ${formatTime(retryAt)}.` : "Today's limit was reached.";
    case "job_cap":
      return "This clip used up its processing budget. You can download this version, or try a shorter clip.";
    case "code_cap":
      return "This access code ran out of budget.";
    case "pilot_pool_cap":
      return "The pilot budget ran out.";
    default:
      return null;
  }
}

/** Landing step 3 copy, by the auditor-name rule (§1.3). */
export function auditStepBody(model: string | null): string {
  if (model === "yunet-face") {
    return "Before anything is published, a face detector (YuNet) checks every frame of the final render for faces; number plates are checked by Muse Spark only, and a second Muse Spark pass tries to read or recognise anything left. Any leak is fixed and recorded on your privacy receipt.";
  }
  return `Before anything is published, Meta's EgoBlur checks the final render for faces and number plates, and a second Muse Spark pass tries to read or recognise anything left. Any leak is fixed and recorded on your privacy receipt.`;
}

// ------------------------------------------------------------------ errors on actions (§2.6, §2.6.1, §10.3)

export const COPY = {
  wrongCode: "That code didn't work. Check it and try again.",
  emptyCode: "Enter your access code.",
  codeRefusedJob: "The access code for this clip no longer works, so Safe Cut can't process it further. Nothing has been published.",
  dailyCapTry: "Safe Cut has reached today's limit for the public demo. Try again tomorrow, or watch the demo on the home page.",
  dailyCapJob: "Safe Cut has reached today's limit for the public demo. Try again tomorrow.",
  dailyCapJobExpiring: "Safe Cut has reached today's limit for the public demo, and this access code expires before the limit resets, so this can't be run again.",
  codeCapTry: "This access code doesn't have enough budget left for this clip. Ask the person who gave it to you to add more, then press Start again.",
  codeCapJob: "This access code ran out of budget.",
  pilotPoolTry: "The pilot budget has been used up, so Safe Cut can't take more pilot clips. Thank you for helping. Your timings and answers so far still count.",
  pilotPoolJob: "The pilot budget ran out.",
  jobCapTry: "This clip would cost more than the per-clip limit to process. Try a shorter clip.",
  jobCapJob: "This clip needs more processing than one job allows.",
  rateLimited: "Too many tries in a short time. Wait a minute and try again.",
  uploadStalled: "The upload stopped. Check your connection and try again; nothing was processed.",
  uploadIncomplete: "The upload didn't finish, so nothing was processed. Choose the clip again to upload it.",
  auditorUnavailable: "Safe Cut's final check isn't available right now, so it can't start new clips. Try again later.",
  billing: "Safe Cut can't start new clips right now. Try again later.",
  noRights: "Tick the box to confirm you can use this clip.",
  deleted: "Deleted. Nothing from this clip is kept.",
  unreachable: "Safe Cut's service isn't responding right now. Your clip is safe and nothing has been published. Try again in a minute.",
  unexpected: "Something went wrong on our side. Nothing has been published.",
  expired: "This clip has been deleted. Safe Cut deletes everything automatically after 24 hours.",
  notFound: "We couldn't find that clip. Check the link, or try another clip.",
  metaBusy: "Meta's service is busy right now. Safe Cut will try once more in a few minutes on its own; you can leave this page and come back with your review link. Nothing has been published.",
  created: "This clip hasn't finished uploading. Upload it again to start.",
  pausedWhileRendering: "Changes are paused while we render.",
} as const;

/** "Code outside its dates" (§2.6), chosen by comparing the device clock with the window. */
export function codeWindowMessage(validFrom: string | null | undefined, validUntil: string | null | undefined, now: number, formatTime: (iso: string) => string): string {
  if (validFrom && now < Date.parse(validFrom)) {
    return `This code isn't active yet. It works from ${formatTime(validFrom)}${validUntil ? ` to ${formatTime(validUntil)}` : ""}.`;
  }
  if (validUntil && now > Date.parse(validUntil)) return `This code has expired. It worked until ${formatTime(validUntil)}.`;
  return "This code isn't active right now. Check the dates that came with it.";
}

/** The job-page variant for a 401 on start/render/audit (§2.6 "Code refused on a job page"). */
export function jobRefusalMessage(code: string | null, validUntil: string | null | undefined, now: number, hasRender: boolean): string {
  if (code === "code_not_active" && validUntil && now > Date.parse(validUntil)) {
    return `This access code has expired, so Safe Cut can't run more work on this clip. ${hasRender ? "You can still download or delete it." : "You can still delete it."}`;
  }
  return COPY.codeRefusedJob;
}

/** A viewer-local date and time ("28 Oct, 11:00"). */
export function formatLocal(iso: string, locale?: string): string {
  const d = new Date(iso);
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(d);
}
