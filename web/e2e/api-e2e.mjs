#!/usr/bin/env node
// E6: the web app in a real browser against the real Safe Cut API, started locally in replay (nothing reaches
// Meta; the demo job's recordings are synthetic and labelled so). Runs the judge's path on desktop and phone:
// landing (the replayed demo job, labelled synthetic) → /try (code, upload of the demo clip) → progress →
// review (hide/keep with undo, merge a new ID into a participant, remove a person, a locked child that can't be
// kept, the Why drawer) → render → result + receipt → delete. Runs axe on every screen and fails on any serious
// or critical violation. Then a cold start (a delayed fake API, so the service "wakes" while the page waits): the
// landing page and /try say "Waking Safe Cut up", then the message goes, the labelled demo plays, and a second
// visit opens at once. Usage: pnpm e2e:api [--shots <dir>] (builds the app against the local API first).
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = join(WEB, "..");
const shotsArg = process.argv.indexOf("--shots");
const SHOTS = shotsArg > 0 ? process.argv[shotsArg + 1] : null;
const AXE = readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
const CODE = "e2e-judge-code";
const MANIFEST = JSON.parse(readFileSync(join(REPO, "fixtures", "jobs", "demo", "raw", "manifest.json"), "utf8"));
const CLIP = join(REPO, MANIFEST.source);

const WAKING = /Waking Safe Cut up\. The first request after a quiet spell takes up to a minute\./;

const results = [];
/** The open page's console errors, printed if the run stops early. */
let pageErrors = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitFor(url, { ms = 120_000, ok = (r) => r.ok } = {}) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try {
      const r = await fetch(url);
      if (ok(r)) return r;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${url} didn't come up within ${ms / 1000} s`);
}

/** axe on WCAG 2.2 AA: every serious or critical violation fails the run; others are reported. */
async function axe(page, label) {
  await page.addScriptTag({ content: AXE });
  const violations = await page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length }));
  });
  const serious = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  check(`axe (no serious or critical): ${label}`, serious.length === 0, serious.map((v) => `${v.id}×${v.nodes}`).join("; "));
  if (violations.length > serious.length) console.log(`     note: minor axe findings on ${label}: ${violations.filter((v) => !serious.includes(v)).map((v) => v.id).join(", ")}`);
}

/**
 * A fake cold start in front of the real API: every JSON request of this page is held until `release()`, the way
 * Modal queues requests while a container starts (it never errors). Media and uploads go straight through.
 */
async function coldApi(page) {
  let released = false;
  let open;
  const ready = new Promise((resolve) => (open = resolve));
  let held = 0;
  await page.route(`${API}/v1/**`, async (route) => {
    if (route.request().resourceType() !== "fetch") return route.continue();
    if (!released) {
      held += 1;
      await ready;
    }
    try {
      await route.fulfill({ response: await route.fetch() });
    } catch {
      // The page closed while the request was held.
    }
  });
  return {
    held: () => held,
    release: () => {
      released = true;
      open();
    },
  };
}

async function newPage(browser, viewport) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [];
  pageErrors = errors;
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  return { context, page, errors };
}

const unexpected = (errors) => errors.filter((e) => !e.includes("Failed to load resource") && !e.includes("status of 404") && !e.includes("status of 401"));

/** The service is cold when the page loads: the landing page and /try wait, say so politely, then carry on. */
async function coldStart(browser) {
  // Landing, on a phone: the demo's first request is held.
  {
    const { context, page, errors } = await newPage(browser, { name: "mobile", width: 390, height: 844 });
    const cold = await coldApi(page);
    await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
    const notice = page.getByText(WAKING);
    await notice.waitFor({ timeout: 20_000 });
    check("cold start, landing: a slow first request says the service is waking up", cold.held() > 0);
    check("cold start, landing: the message is in a polite status region", (await page.getByRole("status").filter({ hasText: WAKING }).count()) === 1);
    check("cold start, landing: the demo is still loading, not failed", await page.getByText("Loading the demo…").isVisible());
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check("cold start, landing: no horizontal page scroll while waking", scrollW <= 0, `${scrollW}px`);
    await shot(page, "cold-1-landing-waking");
    await axe(page, "landing while the service wakes");
    cold.release();
    await page.getByText(/saved results for a synthetic test clip/).waitFor({ timeout: 20_000 });
    check("cold start, landing: the labelled demo opens once the service is up", true);
    check("cold start, landing: the waking message goes once the API answers", (await notice.count()) === 0);
    const played = await page.locator("figure video").evaluate(async (el) => {
      if (el.paused) await el.play().catch(() => undefined);
      await new Promise((resolve) => setTimeout(resolve, 1_500));
      return { error: el.error?.code ?? null, time: el.currentTime };
    });
    check("cold start, landing: the demo plays without error", played.error === null && played.time > 0, `error=${played.error} t=${played.time.toFixed(2)}`);
    check("cold start, landing: no unexpected console errors", unexpected(errors).length === 0, unexpected(errors).slice(0, 3).join(" | "));
    // The service is awake now (the API process is up): a new visit opens the labelled demo at once, with no message.
    const reopened = Date.now();
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByText(/saved results for a synthetic test clip/).waitFor({ timeout: 20_000 });
    const took = Date.now() - reopened;
    check("cold start, landing: after a wake the labelled demo opens at once", took < 4_000 && (await notice.count()) === 0, `${took} ms`);
    await context.close();
  }

  // /try on a desktop: the code check is the first request.
  {
    const { context, page, errors } = await newPage(browser, { name: "desktop", width: 1280, height: 900 });
    const cold = await coldApi(page);
    await page.goto(`${BASE}/try`, { waitUntil: "domcontentloaded" });
    await page.getByLabel("Access code").fill(CODE);
    await page.getByRole("button", { name: "Continue" }).click();
    const notice = page.getByText(WAKING);
    await notice.waitFor({ timeout: 20_000 });
    check("cold start, /try: a slow code check says the service is waking up", cold.held() > 0);
    check("cold start, /try: the button says it is checking, and no error shows", (await page.getByRole("button", { name: "Checking…" }).count()) === 1 && (await page.getByText(/service isn't responding/).count()) === 0);
    await shot(page, "cold-2-try-waking");
    await axe(page, "try while the service wakes");
    cold.release();
    await page.getByRole("button", { name: "Choose a file" }).waitFor({ timeout: 20_000 });
    check("cold start, /try: the code is accepted once the service is up", true);
    check("cold start, /try: the waking message goes once the API answers", (await notice.count()) === 0);
    check("cold start, /try: no unexpected console errors", unexpected(errors).length === 0, unexpected(errors).slice(0, 3).join(" | "));
    await context.close();
  }
}

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true });
}

const jobsDir = mkdtempSync(join(tmpdir(), "safecut-e2e-jobs-"));
const apiPort = await freePort();
const webPort = await freePort();
const API = `http://127.0.0.1:${apiPort}`;
const BASE = `http://127.0.0.1:${webPort}`;
const children = [];

function stopAll() {
  for (const child of children) child.kill("SIGTERM");
  rmSync(jobsDir, { recursive: true, force: true });
}
process.on("exit", stopAll);

let browser;
try {
  // The API, in replay, with one judge code, a high rate limit (the e2e polls a lot) and CORS for this web origin.
  const api = spawn("uv", ["run", "--no-sync", "uvicorn", "--factory", "safecut.api.app:create_app", "--host", "127.0.0.1", "--port", String(apiPort), "--log-level", process.env.E2E_API_LOG ?? "warning", "--no-proxy-headers"], {
    cwd: REPO,
    env: {
      ...process.env,
      SAFECUT_REPLAY: "1",
      SAFECUT_JOBS_DIR: jobsDir,
      SAFECUT_PUBLIC_URL: API,
      SAFECUT_URL_SECRET: "e2e-url-secret",
      SAFECUT_CORS_ORIGINS: JSON.stringify([BASE]),
      SAFECUT_ACCESS_CODES: JSON.stringify([{ code: CODE, kind: "judge" }]),
      SAFECUT_CODE_WINDOWS: JSON.stringify({ judge: [null, null] }),
      SAFECUT_RATE_LIMIT_PER_MIN: "2000",
      SAFECUT_PAID_ACTIONS_PER_HOUR: "200",
    },
    stdio: ["ignore", "inherit", "inherit"],
  });
  children.push(api);
  await waitFor(`${API}/healthz`);
  // The pinned demo job is precomputed at startup (the real stages, replayed in a child process).
  await waitFor(`${API}/v1/demo/demo`, { ms: 300_000 });
  check("the API precomputed the demo job", true);

  const build = spawnSync(process.execPath, [join(WEB, "node_modules", "next", "dist", "bin", "next"), "build"], {
    cwd: WEB,
    env: { ...process.env, NEXT_PUBLIC_SAFECUT_API: API, NEXT_PUBLIC_SAFECUT_HERO_ID: "demo" },
    stdio: ["ignore", "ignore", "inherit"],
  });
  if (build.status !== 0) throw new Error("next build against the local API failed");
  const web = spawn(process.execPath, [join(WEB, "node_modules", "next", "dist", "bin", "next"), "start", "-p", String(webPort), "-H", "127.0.0.1"], {
    cwd: WEB,
    env: { ...process.env },
    stdio: ["ignore", "ignore", "inherit"],
  });
  children.push(web);
  await waitFor(`${BASE}/`);

  if (SHOTS) mkdirSync(SHOTS, { recursive: true });
  browser = await chromium.launch();
  for (const viewport of [
    { name: "desktop", width: 1280, height: 900 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    const page = await context.newPage();
    const errors = [];
    pageErrors = errors;
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    const v = viewport.name;
    if (process.env.E2E_DEBUG) {
      page.on("request", (r) => r.url().includes("/review") && r.method() === "POST" && console.log(`     → ${r.postData()}`));
      page.on("response", async (r) => {
        if (!r.url().includes("/review") || r.request().method() !== "POST") return;
        const body = await r.json().catch(() => null);
        console.log(`     ← ${r.status()} edit_id=${body?.edit_id} status=${body?.status}`);
      });
    }

    // Landing: the replayed demo job, labelled synthetic.
    const landing = await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    const csp = landing?.headers()["content-security-policy"] ?? "";
    check(`${v}: landing sends a CSP with frame-ancestors`, csp.includes("frame-ancestors") && csp.includes("object-src 'none'"));
    await page.getByText(/saved results for a synthetic test clip/).waitFor({ timeout: 20_000 });
    check(`${v}: the demo banner says the replay is synthetic`, true);
    const heroReady = await page.locator("figure video").evaluate((el) => new Promise((res) => (el.readyState >= 1 ? res(true) : el.addEventListener("loadedmetadata", () => res(true), { once: true }))));
    check(`${v}: the demo video loads from the API`, heroReady === true);
    await page.getByRole("radio", { name: "Raw footage" }).click();
    check(`${v}: the raw toggle switches to the prepared clip`, (await page.locator("figure video").getAttribute("src"))?.includes("/media/prepared.mp4") ?? false);
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(`${v}: landing has no horizontal page scroll`, scrollW <= 0, `${scrollW}px`);
    await shot(page, `${v}-1-landing`);
    await axe(page, `${v} landing`);

    // /try: the code, then the demo clip.
    await page.goto(`${BASE}/try`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Continue" }).click();
    check(`${v}: an empty code is refused`, await page.getByText("Enter your access code.").isVisible());
    await page.getByLabel("Access code").fill("not-a-real-code");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByText("That code didn't work. Check it and try again.").waitFor();
    check(`${v}: the API refuses a wrong code`, true);
    await axe(page, `${v} try (code)`);
    await page.getByLabel("Access code").fill(CODE);
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: "Choose a file" }).waitFor();
    await page.locator('input[type="file"]').setInputFiles(CLIP);
    await page.getByText(/SC-A-91-synthetic-20261030\.mp4 · 0:12/).waitFor();
    check(`${v}: the clip's duration is read from its metadata`, true);
    await page.getByRole("checkbox").check();
    await shot(page, `${v}-2-try`);
    await axe(page, `${v} try (file)`);
    await page.getByRole("button", { name: "Start" }).click();
    await page.getByText("Working on your clip").waitFor();
    check(`${v}: the upload went through and progress shows`, true);
    await axe(page, `${v} progress`);

    // Review.
    await page.waitForURL(/\/jobs\/j_[A-Za-z0-9_-]{22}$/, { timeout: 180_000 });
    const jobId = page.url().split("/jobs/")[1];
    await page.getByText(/hidden · \d+ kept clear · \d+ needs? you/).waitFor({ timeout: 60_000 });
    check(`${v}: lands on the review panel`, true);
    check(`${v}: the review page says the replay is synthetic`, await page.getByText(/saved results for a synthetic test clip/).isVisible());
    const job = await (await fetch(`${API}/v1/jobs/${jobId}`)).json();
    const label = (item) => {
      const primary = item.track_ids.find((t) => t.startsWith("face:")) ?? item.track_ids[0];
      const [concept, n] = primary.split(":");
      const words = { face: "Face", person: "Person", "license plate": "Plate", screen: "Screen", phone: "Phone", document: "Document", "name badge": "Badge" };
      return item.audit_label ?? `${words[concept] ?? concept.charAt(0).toUpperCase() + concept.slice(1)} ${n}`;
    };
    await shot(page, `${v}-3-review`);
    await axe(page, `${v} review`);

    const openColumn = async (name) => {
      if (v === "mobile") await page.getByRole("tab", { name }).click();
    };
    // A locked child: hidden, with no Keep clear, and the drawer says why.
    const child = job.items.find((i) => i.kind === "child");
    check(`${v}: the demo job has a child item`, !!child);
    if (child) {
      await openColumn(/Hidden/);
      const name = label(child);
      check(`${v}: a locked child has no Keep clear button`, (await page.getByRole("button", { name: `Keep clear ${name}` }).count()) === 0);
      await page.getByRole("button", { name: new RegExp(`^Why\\? ${name}, hidden`) }).click();
      const drawer = page.getByRole("dialog", { name: new RegExp(`^${name}`) });
      await drawer.getByText(/Children are always hidden/).waitFor();
      check(`${v}: the Why drawer says children are always hidden`, true);
      await shot(page, `${v}-4-why-child`);
      await axe(page, `${v} why drawer`);
      await page.keyboard.press("Escape");
      await drawer.waitFor({ state: "hidden" });
    }

    // Hide/keep toggle with undo, on an item waiting for the creator.
    const needs = job.items.find((i) => i.decision === "needs_you" && !i.locked);
    check(`${v}: the demo job has an item that needs the creator`, !!needs);
    if (needs) {
      await openColumn(/Needs you/);
      const name = label(needs);
      await page.getByRole("button", { name: `Hide ${name}` }).click();
      await page.getByText(`${name} will be hidden.`).waitFor();
      check(`${v}: one tap hides an item, saved by the API`, true);
      await page.getByRole("button", { name: "Undo" }).click({ timeout: 30_000 });
      await page.getByText("Undone.").waitFor();
      check(`${v}: undo reverts it`, true);
    }

    // Merge a re-entered person (a new ID) into the participant it is.
    const trackById = Object.fromEntries(job.tracks.map((t) => [t.track_id, t]));
    const reentry = job.items.find((i) => i.decision !== "keep" && !i.locked && i.track_ids.some((t) => trackById[t]?.reentry_of));
    if (reentry) {
      await openColumn(new RegExp(reentry.decision === "needs_you" ? "Needs you" : "Hidden"));
      const merge = page.getByRole("button", { name: /^Same as .+…$/ }).first();
      if ((await merge.count()) > 0) {
        await merge.click();
        const dialog = page.getByRole("dialog", { name: /^Who is / });
        await dialog.getByRole("button", { name: /Same person as / }).first().click();
        await page.getByText(/merged into .+\. They'll be kept clear like/).waitFor();
        check(`${v}: a new ID merges into a participant`, true);
      } else {
        check(`${v}: a re-entered ID offers a merge`, false, label(reentry));
      }
    } else {
      check(`${v}: the demo job has a re-entered ID`, false, "no track with reentry_of outside the kept items");
    }

    // Remove a kept person from the video.
    const kept = job.items.find((i) => i.decision === "keep" && i.kind === "person");
    if (kept) {
      await openColumn(/Kept clear/);
      const name = label(kept);
      await page.getByRole("button", { name: `More actions for ${name}` }).click();
      await page.getByRole("menuitem", { name: "Remove this person from the video" }).click();
      const saved = page.waitForResponse((r) => r.url().includes("/review") && (r.request().postData() ?? "").includes('"remove_person"'), { timeout: 90_000 });
      const sentAt = Date.now();
      await page.getByRole("dialog", { name: "Remove this person?" }).getByRole("button", { name: "Remove" }).click();
      await page.getByText(`${name} will be fully covered wherever they appear.`).waitFor();
      const ack = await saved;
      check(`${v}: remove person, saved by the API`, ack.status() === 200, `${ack.status()} after ${Date.now() - sentAt} ms`);
      await page.getByRole("button", { name: "Undo" }).click({ timeout: 90_000 });
      await page.getByText("Undone.").waitFor();
    } else {
      check(`${v}: the demo job has a kept person`, false);
    }

    // Approve & render → the result and the receipt.
    await page.getByRole("button", { name: "Approve & render" }).click();
    await page.waitForURL(/\/result$/, { timeout: 240_000 });
    await page.getByText(/frames checked\./).waitFor({ timeout: 60_000 });
    check(`${v}: the result shows the audit summary`, true);
    const hrefs = await page.locator("a[href*='receipt']").evaluateAll((links) => links.map((a) => a.href));
    const htmlHref = hrefs.find((h) => h.includes("receipt.html"));
    const jsonHref = hrefs.find((h) => h.includes("receipt.json"));
    const html = htmlHref ? await (await fetch(htmlHref)).text() : "";
    check(`${v}: the privacy receipt (HTML) opens`, /<html|<!doctype/i.test(html), htmlHref ?? "no receipt.html link");
    const receiptJson = jsonHref ? await (await fetch(jsonHref)).json().catch(() => null) : null;
    check(`${v}: the receipt JSON has its hash`, typeof receiptJson?.hash === "string" && receiptJson.hash.length === 64, jsonHref ?? "no receipt.json link");
    await shot(page, `${v}-5-result`);
    await axe(page, `${v} result`);
    await page.getByRole("button", { name: "Delete everything now" }).click();
    await page.getByRole("dialog", { name: "Delete everything now?" }).getByRole("button", { name: "Delete" }).click();
    await page.getByText("Deleted from Safe Cut's servers.").waitFor();
    const gone = await fetch(`${API}/v1/jobs/${jobId}`);
    check(`${v}: delete removes the job from the API`, gone.status === 404);

    const real = errors.filter((e) => !e.includes("Failed to load resource") && !e.includes("status of 404") && !e.includes("status of 401"));
    check(`${v}: no unexpected console errors`, real.length === 0, real.slice(0, 3).join(" | "));
    await context.close();
  }

  await coldStart(browser);
} catch (error) {
  check("the run finished", false, String(error?.stack ?? error).slice(0, 600));
  if (pageErrors.length) console.log(`     page console errors:\n       ${pageErrors.slice(-8).join("\n       ")}`);
} finally {
  await browser?.close();
  stopAll();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length === 0 ? 0 : 1);
