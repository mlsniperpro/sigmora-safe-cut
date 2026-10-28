#!/usr/bin/env node
// End-to-end check in a real browser against the production build in mock
// mode (no API configured, so nothing leaves the machine). Runs the judge's
// path: landing → /try → upload the sample clip → progress → review (edit,
// overlay, Why drawer) → render → result → delete. Also runs axe on every
// screen and saves screenshots. Usage: pnpm build && pnpm e2e [--shots <dir>]
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PORT = Number(process.env.E2E_PORT ?? 3217);
const BASE = `http://127.0.0.1:${PORT}`;
const shotsArg = process.argv.indexOf("--shots");
const SHOTS = shotsArg > 0 ? process.argv[shotsArg + 1] : null;
const AXE = readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
}

async function waitForServer(url, ms = 60_000) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`server at ${url} didn't start`);
}

async function axe(page, label) {
  await page.addScriptTag({ content: AXE });
  const violations = await page.evaluate(async () => {
    // Video frames have no text to check; everything else is WCAG 2.2 AA.
    const r = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } });
    return r.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`);
  });
  check(`axe WCAG 2.2 AA: ${label}`, violations.length === 0, violations.join("; "));
}

async function shot(page, name, fullPage = true) {
  if (!SHOTS) return;
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage });
}

const server = spawn(process.execPath, [join(ROOT, "node_modules", "next", "dist", "bin", "next"), "start", "-p", String(PORT), "-H", "127.0.0.1"], {
  cwd: ROOT,
  env: { ...process.env, NEXT_PUBLIC_SAFECUT_API: "" },
  stdio: ["ignore", "ignore", "inherit"],
});

let browser;
try {
  if (SHOTS) mkdirSync(SHOTS, { recursive: true });
  await waitForServer(`${BASE}/`);
  browser = await chromium.launch();
  for (const viewport of [
    { name: "desktop", width: 1280, height: 900 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    const v = viewport.name;

    // Landing
    const response = await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    const csp = response?.headers()["content-security-policy"] ?? "";
    check(`${v}: landing sends a CSP with frame-ancestors`, csp.includes("frame-ancestors") && csp.includes("object-src 'none'"));
    await page.getByRole("radio", { name: "■ Safe Cut" }).waitFor();
    const heroReady = await page.locator("figure video").evaluate((el) => new Promise((res) => (el.readyState >= 1 ? res(true) : el.addEventListener("loadedmetadata", () => res(true), { once: true }))));
    check(`${v}: hero video loads`, heroReady === true);
    await page.getByRole("radio", { name: "Raw footage" }).click();
    check(`${v}: raw toggle switches the source`, (await page.locator("figure video").getAttribute("src"))?.endsWith("prepared.mp4") ?? false);
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(`${v}: landing has no horizontal page scroll`, scrollW <= 0, `${scrollW}px`);
    await shot(page, `${v}-1-landing`);
    await axe(page, `${v} landing`);

    // /try
    await page.goto(`${BASE}/try`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Continue" }).click();
    check(`${v}: empty code is refused`, await page.getByText("Enter your access code.").isVisible());
    await page.getByLabel("Access code").fill("wrong");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByText("That code didn't work. Check it and try again.").waitFor();
    check(`${v}: a wrong code is refused`, true);
    await shot(page, `${v}-2-try-code`);
    await axe(page, `${v} try (code)`);
    await page.getByLabel("Access code").fill("judge-demo");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: "Choose a file" }).waitFor();
    await page.locator('input[type="file"]').setInputFiles(join(ROOT, "public", "sample", "prepared.mp4"));
    await page.getByText(/prepared\.mp4 · 0:08/).waitFor();
    check(`${v}: the real clip's duration is read from its metadata`, true);
    await page.getByRole("checkbox").check();
    await shot(page, `${v}-3-try-file`);
    await axe(page, `${v} try (file)`);
    await page.getByRole("button", { name: "Start" }).click();
    await page.getByText("Working on your clip").waitFor();
    // Polling every 2 s can skip a 1.2 s mock stage, so accept whichever pipeline row is active.
    const active = page.locator('li[aria-current="step"]');
    await active.waitFor({ timeout: 15_000 });
    const label = (await active.innerText()).split("\n").find((l) => l && !l.startsWith("Now"));
    check(`${v}: progress shows the active pipeline stage`, true, label ?? "");
    await shot(page, `${v}-4-progress`);

    // Review
    await page.waitForURL(/\/jobs\/j_mock\d+$/, { timeout: 30_000 });
    await page.getByText(/hidden · \d+ kept clear · \d+ needs? you/).waitFor();
    check(`${v}: lands on the review panel`, true);
    if (v === "desktop") {
      // Browser Back from the review panel shows a fresh /try, never a page that bounces forward again.
      await page.goBack();
      await page.getByLabel("Access code").waitFor();
      await page.waitForTimeout(2500);
      check(`${v}: Back from the review panel lands on a fresh /try`, page.url().endsWith("/try"));
      await page.goForward();
      await page.getByText(/hidden · \d+ kept clear · \d+ needs? you/).waitFor();
    }
    await page.locator("video").first().evaluate((el) => new Promise((res) => (el.readyState >= 2 ? res(true) : el.addEventListener("loadeddata", () => res(true), { once: true }))));
    // Seek to the plate's first evidence frame and read the overlay pixels over the plate.
    const covered = await page.evaluate(async () => {
      const video = document.querySelector("video");
      const canvas = document.querySelector("canvas");
      video.currentTime = 15.5 / 30;
      await new Promise((r) => video.addEventListener("seeked", r, { once: true }));
      await new Promise((r) => setTimeout(r, 300));
      const s = canvas.width / 1280;
      const px = canvas.getContext("2d").getImageData(Math.round(1080 * s), Math.round(652 * s), 1, 1).data;
      return px[3] > 200;
    });
    check(`${v}: the overlay covers the hidden plate on its frame`, covered);
    await shot(page, `${v}-5-review`);
    await axe(page, `${v} review`);
    if (v === "mobile") await page.getByRole("tab", { name: /Needs you/ }).click();
    await page.getByRole("button", { name: "Hide Face 6" }).click();
    await page.getByText("Face 6 will be hidden.").waitFor();
    check(`${v}: one tap hides an item with a toast`, true);
    await page.getByRole("button", { name: "Undo" }).click({ timeout: 5_000 });
    await page.getByText("Undone.").waitFor();
    check(`${v}: undo works`, true);
    if (v === "mobile") await page.getByRole("tab", { name: /Hidden/ }).click();
    await page.getByRole("button", { name: "Same as Face 1…" }).click();
    await page.getByRole("dialog", { name: "Who is Face 8?" }).getByRole("button", { name: /Same person as Face 1/ }).click();
    await page.getByText("Face 8 merged into Face 1. They'll be kept clear like Face 1.").waitFor();
    check(`${v}: re-entry merge into the kept guest`, true);
    // On mobile the merge opened the Kept clear tab, where the guest now is (focus follows the edit).
    if (v === "mobile") {
      check(`${v}: the merge opens the tab the edited chip moved to`, (await page.getByRole("tab", { name: /Kept clear/ }).getAttribute("aria-selected")) === "true");
      await page.getByRole("tab", { name: /Hidden/ }).click();
    }
    await page.getByRole("button", { name: "Why? Face 4, hidden" }).click();
    const drawer = page.getByRole("dialog", { name: "Face 4 · Child" });
    await drawer.getByText("Children are always hidden. You can't change this, because Safe Cut can't check a parent's consent.").waitFor();
    await drawer.locator("img").evaluate((img) => (img.complete ? true : new Promise((r) => img.addEventListener("load", r, { once: true }))));
    await page.waitForTimeout(200);
    const ring = await drawer.locator('[aria-hidden="true"].border-white').count();
    check(`${v}: the Why drawer rings the item on the Set-of-Mark keyframe`, ring === 1);
    await shot(page, `${v}-6-why-drawer`, false);
    await axe(page, `${v} why drawer`);
    await page.keyboard.press("Escape");
    await drawer.waitFor({ state: "hidden" });
    check(`${v}: Esc closes the drawer`, true);

    // Render → result
    await page.getByRole("button", { name: "Approve & render" }).click();
    await page.getByRole("listitem").filter({ hasText: "Applying your choices" }).waitFor();
    check(`${v}: render shows the render stages`, true);
    await page.waitForURL(/\/result$/, { timeout: 30_000 });
    await page.getByText(/frames checked\./).waitFor();
    check(`${v}: the result shows the audit summary`, await page.getByText("1 leak found and fixed. Nothing left to fix.").isVisible());
    check(`${v}: no Publish button outside Sigmora`, (await page.getByRole("button", { name: "Publish to Sigmora" }).count()) === 0);
    await shot(page, `${v}-7-result`);
    await axe(page, `${v} result`);
    await page.getByRole("button", { name: "Delete everything now" }).click();
    await page.getByRole("dialog", { name: "Delete everything now?" }).getByRole("button", { name: "Delete" }).click();
    await page.getByText("Deleted from Safe Cut's servers.").waitFor();
    check(`${v}: delete everything now`, true);

    // States reachable by URL
    for (const [id, text] of [
      ["job-replay", "You're seeing saved results from a real run"],
      ["result-audit-failed", "The final check couldn't finish on 4 frames."],
      ["error-404-expired", "This clip has been deleted."],
    ]) {
      await page.goto(`${BASE}/jobs/${id}`, { waitUntil: "networkidle" });
      await page.getByText(text).first().waitFor();
      check(`${v}: /jobs/${id} shows its state`, true);
      if (id === "job-replay") await shot(page, `${v}-8-demo-mode`, false);
    }
    await page.goto(`${BASE}/nope`, { waitUntil: "networkidle" });
    check(`${v}: unknown routes get the 404 copy`, await page.getByText("We couldn't find that page.").isVisible());

    const real = errors.filter((e) => !e.includes("example.invalid") && !e.includes("ERR_NAME_NOT_RESOLVED") && !e.includes("ERR_TUNNEL_CONNECTION_FAILED") && !e.includes("load failed (404)") && !e.includes("Failed to load resource"));
    check(`${v}: no unexpected console errors`, real.length === 0, real.slice(0, 3).join(" | "));
    await context.close();
  }

  // Region check (UI-SPEC §7): restricted territories get the unavailable page on /try; the landing stays open.
  {
    const context = await browser.newContext({ extraHTTPHeaders: { "x-vercel-ip-country": "UA", "x-vercel-ip-country-region": "43" } });
    const page = await context.newPage();
    await page.goto(`${BASE}/try`, { waitUntil: "networkidle" });
    check("region: a restricted territory gets the unavailable page on /try", await page.getByText(/Safe Cut isn't available in your region/).isVisible());
    check("region: no upload form is served there", (await page.getByLabel("Access code").count()) === 0);
    const home = await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    check("region: the landing page stays open", home?.status() === 200);
    await page.goto(`${BASE}/privacy`, { waitUntil: "networkidle" });
    check("privacy page is reachable", await page.getByRole("heading", { name: "Privacy", level: 1 }).isVisible());
    await axe(page, "privacy");
    await context.close();
  }

  // Reduced motion (§1.4): no autoplay; "Play demo" plays and hands focus to the player, then stays out of the way until paused.
  {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    const button = page.getByRole("button", { name: "Play demo" });
    await button.waitFor();
    check("reduced motion: the hero doesn't autoplay", await page.locator("figure video").evaluate((v) => v.paused));
    await button.click();
    await page.locator("figure video").evaluate((v) => new Promise((r) => (v.paused ? v.addEventListener("playing", r, { once: true }) : r())));
    check("reduced motion: Play demo leaves while the clip plays", (await button.count()) === 0);
    check("reduced motion: focus moves to the player, not the page", await page.locator("figure video").evaluate((v) => document.activeElement === v));
    await page.locator("figure video").evaluate((v) => v.pause());
    check("reduced motion: Play demo is back once paused", await button.isVisible());
    await context.close();
  }

  // A short landscape screen (or 200% zoom): the player isn't sticky, so the chips can scroll into view.
  {
    const context = await browser.newContext({ viewport: { width: 844, height: 390 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    const position = await page.locator("video").first().evaluate((el) => getComputedStyle(el.closest("[class*='bg-bg']")).position);
    check("landscape 844×390: the player isn't sticky", position !== "sticky", position);
    const chip = page.getByRole("article").first();
    await chip.focus();
    const box = await chip.boundingBox();
    check("landscape 844×390: a focused chip is on screen", !!box && box.y >= 0 && box.y < 390, box ? `y=${Math.round(box.y)}` : "no box");
    await context.close();
  }

  // Desktop: the player isn't sticky, so it never covers the chip columns (§3.1, WCAG 2.4.11).
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1366, height: 768 }]) {
    const label = `${viewport.width}×${viewport.height}`;
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    const position = await page.locator("video").first().evaluate((el) => getComputedStyle(el.closest("[class*='bg-bg']")).position);
    check(`${label}: the desktop player isn't sticky`, position !== "sticky", position);
    // §3.1: chips start on the first screen, beside a player that is still in view.
    const firstChipTop = await page.getByRole("article").first().evaluate((el) => Math.round(el.getBoundingClientRect().top));
    check(`${label}: the first chip row starts on the first screen`, firstChipTop < viewport.height - 120, `top=${firstChipTop}`);
    await page.getByRole("article").first().focus();
    const playerVisible = await page.locator("video").first().evaluate((el) => el.getBoundingClientRect().bottom > 80);
    check(`${label}: the player is still in view with the first chip focused`, playerVisible);
    const buttons = page.locator("article button");
    const n = Math.min(await buttons.count(), 12);
    let hidden = 0;
    for (let i = 0; i < n; i++) {
      await buttons.nth(i).focus();
      const covered = await buttons.nth(i).evaluate((el) => {
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !hit || !el.contains(hit);
      });
      if (covered) hidden += 1;
    }
    check(`${label}: focused chip buttons aren't covered by the player or the bar`, hidden === 0, `${hidden} of ${n} covered`);
    await context.close();
  }

  // A refusal that keeps the /try step leaves focus on the pressed button (§10.2; a disabled
  // button would drop it to the page, which jsdom doesn't model).
  {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/try`, { waitUntil: "networkidle" });
    await page.getByLabel("Access code").fill("rate-limited");
    const cont = page.getByRole("button", { name: "Continue" });
    await cont.focus();
    await page.keyboard.press("Enter");
    await page.getByText("Too many tries in a short time. Wait a minute and try again.").first().waitFor();
    const focused = await cont.evaluate((el) => document.activeElement === el);
    check("/try: a refused Continue keeps focus on the button", focused);
    // A refusal that disables Start (401 on POST /v1/jobs: the `expired` mock code) takes focus itself.
    await page.getByLabel("Access code").fill("expired");
    await cont.click();
    await page.getByRole("button", { name: "Choose a file" }).waitFor();
    await page.locator('input[type="file"]').setInputFiles(join(ROOT, "public", "sample", "prepared.mp4"));
    await page.getByText(/prepared\.mp4 · 0:08/).waitFor();
    await page.getByRole("checkbox").check();
    const start = page.getByRole("button", { name: "Start" });
    await start.focus();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Use a different code" }).waitFor();
    const inAlert = await page.evaluate(() => !!document.activeElement?.closest('[role="alert"]'));
    check("/try: a refusal that disables Start takes focus", inAlert && (await start.isDisabled()));
    await context.close();
  }

  // Narrow phones: the open tab (often "Needs you", the last) is scrolled fully into its strip.
  for (const width of [320, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 700 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-200-items`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    await page.waitForTimeout(100);
    const inside = await page.evaluate(() => {
      const tab = document.querySelector('[role="tab"][aria-selected="true"]');
      const strip = tab?.parentElement;
      if (!tab || !strip) return null;
      const t = tab.getBoundingClientRect();
      const s = strip.getBoundingClientRect();
      return t.left >= s.left - 1 && t.right <= s.right + 1;
    });
    check(`${width} px: the open tab is fully visible in the tab strip`, inside === true);
    await context.close();
  }

  // Short narrow screens (400% zoom): the static player adds no scroll padding, so focus stays clear of the bar.
  for (const viewport of [{ width: 320, height: 400 }, { width: 480, height: 270 }]) {
    const label = `${viewport.width}×${viewport.height}`;
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-200-items`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    const pad = await page.evaluate(() => getComputedStyle(document.documentElement).scrollPaddingTop);
    check(`${label}: no top scroll padding for a static player`, pad === "0px", pad);
    const chips = page.getByRole("article");
    let hidden = 0;
    const n = Math.min(await chips.count(), 8);
    for (let i = 0; i < n; i++) {
      await chips.nth(i).focus();
      const clear = await chips.nth(i).evaluate((el) => {
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + 8, r.top + 8);
        return !!hit && el.contains(hit);
      });
      if (!clear) hidden += 1;
    }
    check(`${label}: focused chips aren't under the bottom bar`, n > 1 && hidden === 0, `${hidden} of ${n} covered`);
    await context.close();
  }

  // The review page's fixed bottom bar never covers the footer, even scrolled to the end (WCAG 2.4.11).
  for (const [label, viewport] of [["desktop", { width: 1280, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(200);
    const gap = await page.evaluate(() => {
      const privacy = [...document.querySelectorAll("footer a")].find((a) => a.textContent?.trim() === "Privacy");
      const bar = [...document.querySelectorAll("div")].find((d) => getComputedStyle(d).position === "fixed" && d.textContent?.includes("Approve & render"));
      if (!privacy || !bar) return null;
      return Math.round(bar.getBoundingClientRect().top - privacy.getBoundingClientRect().bottom);
    });
    check(`${label}: the bottom bar leaves the footer's Privacy link clear at the end of the page`, gap !== null && gap >= 0, gap === null ? "not found" : `gap=${gap}px`);
    await context.close();
  }

  // Browsers without requestVideoFrameCallback: the rAF fallback still covers, and says it may lag (§3.6).
  {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await context.addInitScript(() => {
      delete HTMLVideoElement.prototype.requestVideoFrameCallback;
      delete HTMLVideoElement.prototype.cancelVideoFrameCallback;
    });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    check("no rVFC: the lag note shows", await page.getByText("Preview may lag by a frame in this browser. The final render isn't affected.").isVisible());
    await page.locator("video").first().evaluate((el) => new Promise((res) => (el.readyState >= 2 ? res(true) : el.addEventListener("loadeddata", () => res(true), { once: true }))));
    const covered = await page.evaluate(async () => {
      const video = document.querySelector("video");
      const canvas = document.querySelector("canvas");
      video.currentTime = 15.5 / 30;
      await new Promise((r) => video.addEventListener("seeked", r, { once: true }));
      await new Promise((r) => setTimeout(r, 300));
      const s = canvas.width / 1280;
      return canvas.getContext("2d").getImageData(Math.round(1080 * s), Math.round(652 * s), 1, 1).data[3] > 200;
    });
    check("no rVFC: the rAF fallback still covers the plate", covered);
    await context.close();
  }
} catch (error) {
  check("e2e run", false, String(error?.message ?? error).split("\n").slice(0, 4).join(" | "));
  // Leave evidence of where it stopped.
  const page = browser?.contexts().at(-1)?.pages().at(-1);
  if (page) {
    const where = SHOTS ?? ROOT;
    await page.screenshot({ path: join(where, "e2e-failure.png"), fullPage: true }).catch(() => undefined);
    console.log(`failed at ${page.url()}: ${(await page.locator("main").innerText().catch(() => "")).slice(0, 400).replace(/\s+/g, " ")}`);
  }
} finally {
  await browser?.close();
  server.kill();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
