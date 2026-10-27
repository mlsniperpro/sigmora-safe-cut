import { describe, expect, it } from "vitest";
import cleanResult from "../../mocks/result-clean.json";
import fixedResult from "../../mocks/result-fixed.json";
import yunetResult from "../../mocks/result-clean-yunet.json";
import unresolvedResult from "../../mocks/result-unresolved.json";
import auditFailed from "../../mocks/result-audit-failed.json";
import auditFailedLeak from "../../mocks/result-audit-failed-with-leak.json";
import overBudget from "../../mocks/result-audit-over-budget.json";
import failedRoles from "../../mocks/job-failed-roles.json";
import failedTooLong from "../../mocks/job-failed-too-long.json";
import failedDaily from "../../mocks/job-failed-daily-cap.json";
import failedDailyExpiring from "../../mocks/job-failed-daily-cap-expiring.json";
import failedCodeNotActive from "../../mocks/job-failed-code-not-active.json";
import failedRender from "../../mocks/job-failed-render.json";
import failedDeterministic from "../../mocks/job-failed-deterministic.json";
import { auditSchema, jobResponseSchema } from "./contracts";
import { auditStepBody, auditSummary, budgetCauseLine, codeWindowMessage, failureView, jobRefusalMessage } from "./copy";

const audit = (raw: { audit: unknown }) => auditSchema.parse(raw.audit);
const job = (raw: unknown) => jobResponseSchema.parse(raw);
const fmt = (iso: string) => iso.slice(0, 16).replace("T", " ");

describe("audit summary (UI-SPEC §5.3, §5.6)", () => {
  it("clean, fixed (distinct items), unresolved", () => {
    expect(auditSummary(audit(cleanResult), 12)).toMatchObject({ state: "clean", lines: ["12 of 12 frames checked.", "No leaks found."], publishable: true });
    // The open-weight line joins the §5.3 detail only when the second opinion ran (§1.3 copy notes).
    const withOpen = (status: string, model = "meta-models/muse-spark-open-1026") => ({ ...audit(cleanResult), open_weight: { model, status } });
    expect(auditSummary(withOpen("ok"), 12).detail).toContain("Muse Spark looked at sampled frames and tried to read or recognise anything. Muse Spark Open, an open-weight model running on Baseten, gives a second opinion and can only add covers. Anything they found");
    expect(auditSummary(withOpen("ok", "other/model"), 12).detail).toContain("An open-weight model running on Baseten gives a second opinion and can only add covers.");
    for (const status of ["off", "failed"]) expect(auditSummary(withOpen(status), 12).detail).not.toContain("Baseten");
    expect(auditSummary(audit(cleanResult), 12).detail).not.toContain("Baseten");
    expect(auditSummary(audit(fixedResult), 12)).toMatchObject({ state: "fixed", leaksFixed: 1, lines: ["12 of 12 frames checked.", "1 leak found and fixed. Nothing left to fix."] });
    expect(auditSummary(audit(unresolvedResult), 12)).toMatchObject({ state: "unresolved", publishable: false, lines: ["12 of 12 frames checked.", "1 spot couldn't be fixed automatically. Publishing is off until each is fixed."] });
  });

  it("counts unchecked frames without the unresolved leak rows", () => {
    expect(auditSummary(audit(auditFailed), 12).lines[0]).toBe("The final check couldn't finish on 4 frames. Publishing is off until it runs.");
    expect(auditSummary(audit(auditFailedLeak), 12)).toMatchObject({ uncheckedFrames: 4, unfixedSpots: 1 });
    expect(auditSummary(audit(overBudget), 12, "x").lines).toEqual(["The final check ran out of budget on 4 frames. Publishing is off.", "x"]);
  });

  it("names the auditor by the model actually used", () => {
    expect(auditSummary(audit(yunetResult), 12).detail).toMatch(/^A face detector \(YuNet\) looked for faces on 12 of the result's 12 frames\./);
    expect(auditSummary(audit(cleanResult), 12).detail).toMatch(/^Meta's EgoBlur looked for faces and number plates/);
    expect(auditStepBody("yunet-face")).toContain("number plates are checked by Muse Spark only");
    expect(auditStepBody("egoblur-gen2")).toContain("Meta's EgoBlur checks the final render for faces and number plates");
    expect(auditStepBody("egoblur-gen2")).toMatch(/Any leak it can fix is covered and recorded on your privacy receipt; anything it can't fix stops publishing\.$/);
    expect(auditStepBody("egoblur-gen2", { model: "meta-models/muse-spark-open-1026", status: "ok" })).toMatch(/ Muse Spark Open, an open-weight model running on Baseten, gives a second opinion and can only add covers\.$/);
    expect(auditStepBody("egoblur-gen2", { model: "other-open", status: "ok" })).toMatch(/ An open-weight model running on Baseten gives a second opinion and can only add covers\.$/);
    expect(auditStepBody("egoblur-gen2", { model: "meta-models/muse-spark-open-1026", status: "failed" })).not.toContain("Baseten");
  });

  it("budget cause lines, with the expiry rule", () => {
    expect(budgetCauseLine("daily_cap", "2026-10-28T00:00:00Z", null, fmt)).toBe("Today's limit was reached. You can run it again after 2026-10-28 00:00.");
    expect(budgetCauseLine("daily_cap", "2026-11-11T00:00:00Z", "2026-11-10T23:59:59Z", fmt)).toBe("Today's limit was reached, and this access code expires before then, so this can't be run again.");
    expect(budgetCauseLine("job_cap", null, null, fmt)).toBe("This clip used up its processing budget. You can download this version, or try a shorter clip.");
    expect(budgetCauseLine(null, null, null, fmt)).toBeNull();
  });
});

describe("failed jobs (UI-SPEC §2.6, §10.3)", () => {
  it("a stage failure names the stage and offers Try again", () => {
    expect(failureView(job(failedRoles))).toMatchObject({ message: "Something went wrong while working out who's part of the story. Your clip hasn't been published anywhere. You can try again, or delete it now.", actions: ["try_again", "delete"], retry: "start" });
    expect(failureView(job(failedRender)).retry).toBe("render");
  });

  it("too long rounds up, and deterministic failures offer no retry", () => {
    expect(failureView(job(failedTooLong))).toMatchObject({ message: "This clip is 60.4 seconds long. The limit is 60 seconds. Trim it and try again.", actions: ["try_another", "delete"] });
    for (const reason of ["config", "bad_request", "refusal", "incomplete"] as const) {
      const v = failureView({ ...job(failedDeterministic), failure: { stage: "scene", reason } });
      expect(v.message).toBe("Safe Cut couldn't process this clip. Your clip hasn't been published anywhere. We've logged the problem.");
      expect(v.actions).not.toContain("try_again");
    }
  });

  it("daily cap waits until retry_at, or hides the retry when the code expires first", () => {
    expect(failureView(job(failedDaily))).toMatchObject({ actions: ["try_again_tomorrow", "delete"], retryAt: "2026-10-28T00:00:00Z" });
    expect(failureView(job(failedDailyExpiring))).toMatchObject({ actions: ["delete"], message: expect.stringContaining("expires before the limit resets") });
  });

  it("an expired code offers delete only, and says download only with a render", () => {
    expect(failureView(job(failedCodeNotActive))).toMatchObject({ actions: ["delete"], message: "This access code has expired, so Safe Cut can't run more work on this clip. You can still delete it." });
    expect(failureView({ ...job(failedCodeNotActive), has_render: true }).message).toContain("You can still download or delete it.");
  });
});

describe("access-code messages (UI-SPEC §2.6)", () => {
  const from = "2026-11-05T00:00:00Z";
  const until = "2026-11-10T23:59:59Z";
  it("chooses by the device clock", () => {
    expect(codeWindowMessage(from, until, Date.parse("2026-11-01T00:00:00Z"), fmt)).toBe("This code isn't active yet. It works from 2026-11-05 00:00 to 2026-11-10 23:59.");
    expect(codeWindowMessage(null, "2026-11-03T23:59:59Z", Date.parse("2026-11-04T00:00:00Z"), fmt)).toBe("This code has expired. It worked until 2026-11-03 23:59.");
    expect(codeWindowMessage(from, until, Date.parse("2026-11-06T00:00:00Z"), fmt)).toBe("This code isn't active right now. Check the dates that came with it.");
  });

  it("job-page refusal: expired vs revoked", () => {
    expect(jobRefusalMessage("code_not_active", until, Date.parse("2026-11-12T00:00:00Z"), true)).toBe("This access code has expired, so Safe Cut can't run more work on this clip. You can still download or delete it.");
    expect(jobRefusalMessage("unauthorized", null, 0, false)).toBe("The access code for this clip no longer works, so Safe Cut can't process it further. Nothing has been published.");
  });
});
