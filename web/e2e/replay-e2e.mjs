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

/** §9: every control on a phone is at least 44×44 px (inline links in running text are exempt, as in WCAG 2.5.8). */
async function targets(page, label) {
  const small = await page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll('button, a[href], [role="tab"], [role="radio"], [role="menuitem"], summary, select, input:not([type="hidden"])')) {
      const r = el.getBoundingClientRect();
      if (r.width <= 1 || r.height <= 1 || getComputedStyle(el).visibility === "hidden") continue;
      if (el.tagName === "A" && el.closest("p, li") && getComputedStyle(el).display === "inline") continue;
      // A checkbox's target is its whole label.
      if (el.tagName === "INPUT" && el.closest("label")) continue;
      if (r.width < 43.5 || r.height < 43.5) out.push(`"${(el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 30)}" ${Math.round(r.width)}×${Math.round(r.height)}`);
    }
    return out;
  });
  check(`mobile 44 px targets: ${label}`, small.length === 0, small.slice(0, 6).join("; "));
}

/**
 * Reflow (WCAG 1.4.10) for text the API sends: a long URL or ID in any text block, inline label or
 * caption must wrap, not widen the page or a panel. Returns the elements that scroll sideways.
 */
async function longTokenOverflow(page) {
  return page.evaluate(() => {
    const token = "https://example.com/watch?v=dQw4w9WgXcQ&list=PLabcdefghijklmnopqrstuvwxyz0123456789&index=12345";
    for (const el of document.querySelectorAll("main p, main li, main blockquote, main dd, main h1, main h2, main h3, dialog p, dialog li, dialog blockquote, dialog h2, dialog h3")) {
      if (el.closest("button, a, [role=tablist], video")) continue;
      el.append(` ${token}`);
    }
    // API text inside a control (a merge target's description or label) wraps too.
    for (const el of document.querySelectorAll("[data-api-text]")) el.append(` ${token}`);
    const out = [];
    // Next to long text, a control's label still keeps whole words (no "Dismis/s").
    for (const el of document.querySelectorAll("button, a, [role=tab], [role=radio], [role=menuitem]")) {
      if (el.getClientRects().length === 0) continue;
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        for (const m of node.data.matchAll(/\S+/g)) {
          if (m[0].includes(token)) continue;
          const range = document.createRange();
          range.setStart(node, m.index);
          range.setEnd(node, m.index + m[0].length);
          const lines = new Set([...range.getClientRects()].map((r) => Math.round(r.top)));
          if (lines.size > 1) out.push(`"${m[0]}" split in ${el.tagName.toLowerCase()}`);
        }
      }
    }
    if (document.documentElement.scrollWidth > document.documentElement.clientWidth + 1) out.push(`page +${document.documentElement.scrollWidth - document.documentElement.clientWidth}px`);
    for (const el of document.querySelectorAll("*")) {
      if (el.closest("[role=tablist]")) continue;
      const style = getComputedStyle(el);
      if (!/(auto|scroll)/.test(style.overflowX) || el.clientWidth === 0) continue;
      if (el.scrollWidth > el.clientWidth + 1) out.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} +${el.scrollWidth - el.clientWidth}px`);
    }
    return out;
  });
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
    if (v === "mobile") await targets(page, "review with the toast open");
    // The toast's focus ring keeps ≥ 3:1 against the toast's own (inverse) surface (§9).
    // Reached with Tab, so it has the keyboard's :focus-visible ring.
    const undo = page.getByRole("button", { name: "Undo" });
    for (let i = 0; i < 80 && !(await undo.evaluate((el) => document.activeElement === el)); i += 1) await page.keyboard.press("Tab");
    const ringRatio = await undo.evaluate((el) => {
      if (!el.matches(":focus-visible")) return 0;
      const rgb = (c) => (c.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
      const lum = ([r, g, b]) => [r, g, b].map((x) => ((x /= 255) <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)).reduce((acc, x, i) => acc + x * [0.2126, 0.7152, 0.0722][i], 0);
      let surface = el.parentElement;
      while (surface && getComputedStyle(surface).backgroundColor === "rgba(0, 0, 0, 0)") surface = surface.parentElement;
      const [a, b] = [lum(rgb(getComputedStyle(el).outlineColor)), lum(rgb(getComputedStyle(surface).backgroundColor))];
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    });
    check(`${v}: the toast's focus ring is at least 3:1 on the toast`, ringRatio >= 3, ringRatio.toFixed(2));
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
    if (v === "mobile") await targets(page, "Why drawer");
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
    if (v === "desktop") {
      check("the 404 page has its own tab title", (await page.title()) === "Page not found · Safe Cut", await page.title());
      await page.goto(`${BASE}/jobs/error-404-expired`, { waitUntil: "networkidle" });
      await page.getByText(/This clip has been deleted/).waitFor();
      await page.waitForTimeout(300);
      check("a job page's tab title follows its state", (await page.title()) === "This clip has been deleted · Safe Cut", await page.title());
      const cut = await page.goto(`${BASE}/jobs/abc%E0`, { waitUntil: "networkidle" });
      check("a job link cut off mid-escape gets the 404 page, not a 500", cut?.status() === 404 && (await page.getByText("We couldn't find that page.").isVisible()), String(cut?.status()));
    }

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
    // React re-renders after the media event: wait for the button to go (it must, within 5 s).
    const gone = await button.waitFor({ state: "detached", timeout: 5_000 }).then(() => true, () => false);
    check("reduced motion: Play demo leaves while the clip plays", gone);
    check("reduced motion: focus moves to the player, not the page", await page.locator("figure video").evaluate((v) => document.activeElement === v));
    await page.locator("figure video").evaluate((v) => v.pause());
    check("reduced motion: Play demo is back once paused", await button.isVisible());
    await context.close();
  }

  // Phone: the Why drawer's evidence frames and the landing, /try and result pages keep 44 px targets.
  {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    for (const path of ["/", "/try", "/jobs/result-fixed/result", "/privacy"]) {
      await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      await targets(page, path);
    }
    await page.goto(`${BASE}/jobs/job-review-needs-you-only`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /^Why\? / }).first().click();
    const drawer = page.getByRole("dialog");
    await drawer.getByRole("button", { name: "Next evidence frame" }).waitFor();
    await targets(page, "Why drawer with evidence frames");
    // Stepping to the last frame leaves focus on ▶ (now unavailable), inside the open sheet.
    const next = drawer.getByRole("button", { name: "Next evidence frame" });
    await next.focus();
    // Two frames on this item: Enter steps to the last, and Enter again there must keep focus.
    for (let i = 0; i < 2; i += 1) await page.keyboard.press("Enter");
    check("Why drawer: focus stays on ▶ at the last evidence frame", await next.evaluate((el) => document.activeElement === el));
    // Hide in the sheet swaps the button for Keep clear: focus moves to it, not out of the open sheet.
    await drawer.getByRole("button", { name: "Hide", exact: true }).click();
    await page.waitForTimeout(150);
    const inSheet = await drawer.evaluate((d) => d.open && d.contains(document.activeElement) && document.activeElement !== d);
    check("Why drawer: after Hide in the sheet, focus stays in the sheet", inSheet, await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 80) ?? ""));
    await context.close();
  }

  // A failed job's Try again keeps focus while its request is out (aria-disabled, not disabled).
  {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-failed-upstream`, { waitUntil: "networkidle" });
    const again = page.getByRole("button", { name: "Try again", exact: true });
    await again.focus();
    await page.keyboard.press("Enter");
    const held = await again.evaluate((el) => document.activeElement === el && el.getAttribute("aria-disabled") === "true");
    check("failed job: Try again keeps focus while the retry is out", held);
    await context.close();
  }

  // 320 px: a long unbroken file name wraps instead of widening the page (§9, WCAG 1.4.10).
  {
    const context = await browser.newContext({ viewport: { width: 320, height: 640 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/try`, { waitUntil: "networkidle" });
    await page.getByLabel("Access code").fill("judge");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: "Choose a file" }).waitFor();
    const name = "my_street_interview_final_cut_v2_export_1080p_hevc_master.mp4";
    await page.locator('input[type="file"]').setInputFiles({ name, mimeType: "video/mp4", buffer: readFileSync(join(ROOT, "public", "sample", "prepared.mp4")) });
    await page.getByText(name, { exact: false }).waitFor();
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check("320 px: a long file name doesn't scroll the page sideways", over <= 0, `${over}px`);
    // Every chip reason shows in full on a phone (no clamp hides its end).
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    let clipped = 0;
    for (const tab of await page.getByRole("tab").all()) {
      await tab.click();
      clipped += await page.evaluate(() => [...document.querySelectorAll("[data-chip-id] p")].filter((p) => p.scrollHeight > p.clientHeight + 1).length);
    }
    check("320 px: no chip reason is cut off", clipped === 0, `${clipped} clipped`);
    // A reason with a long URL or ID wraps inside its chip instead of widening the page.
    await page.locator("[data-chip-id] p.text-sm").first().evaluate((p) => (p.textContent = "Screen shows www.somebank-online-banking.example/login/session?id=12345678901234567890123456789012345678901234567890"));
    const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check("320 px: a long token in a chip reason doesn't scroll the page sideways", wide <= 0, `${wide}px`);
    await context.close();
  }

  // Forced colours (Windows High Contrast): selection and the primary button stay visible without colour or shadow.
  {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, forcedColors: "active" });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-hero1`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    const tabBg = async (name) => page.getByRole("tab", { name }).evaluate((el) => getComputedStyle(el).backgroundColor);
    const selected = (await page.getByRole("tab", { name: /Needs you/ }).getAttribute("aria-selected")) === "true" ? /Needs you/ : /Hidden/;
    const other = selected.source === "Needs you" ? /Hidden/ : /Needs you/;
    check("forced colours: the open tab looks different from the others", (await tabBg(selected)) !== (await tabBg(other)));
    const primary = await page.getByRole("button", { name: "Approve & render" }).evaluate((el) => parseFloat(getComputedStyle(el).borderTopWidth));
    check("forced colours: the primary button has a visible edge", primary > 0, `${primary}px`);
    // Hidden holds two chips here: select one and compare it with the other.
    await page.getByRole("tab", { name: /Hidden/ }).click();
    await page.getByRole("article").first().click({ position: { x: 4, y: 4 } });
    const widths = await page.evaluate(() => [...document.querySelectorAll("[data-chip-id]")].map((el) => [el.hasAttribute("data-selected"), getComputedStyle(el).borderTopWidth]));
    const sel = widths.find(([s]) => s)?.[1];
    const unsel = widths.find(([s]) => !s)?.[1];
    check("forced colours: the selected chip stands out", !!sel && !!unsel && sel !== unsel, `${sel} vs ${unsel}`);
    // The Why sheet's drag handle (Expand/Collapse) stays visible.
    await page.getByRole("button", { name: /^Why\? / }).first().click();
    const handle = await page.getByRole("button", { name: /^(Expand|Collapse)$/ }).evaluate((b) => [getComputedStyle(b.querySelector("span")).backgroundColor, getComputedStyle(b.closest("dialog")).backgroundColor]);
    check("forced colours: the Why sheet's handle is visible", handle[0] !== handle[1], handle.join(" vs "));
    await page.keyboard.press("Escape");
    await context.close();
  }

  // 320 px: long URLs or IDs in API text wrap everywhere, in pages and in the Why drawer.
  {
    const context = await browser.newContext({ viewport: { width: 320, height: 640 } });
    const page = await context.newPage();
    for (const path of ["/", "/jobs/job-review-why-rows", "/jobs/result-fixed/result", "/jobs/job-failed-roles", "/jobs/job-processing-track", "/privacy"]) {
      await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      await page.locator("main h1").first().waitFor({ state: "attached" });
      const wide = await longTokenOverflow(page);
      check(`320 px: long tokens wrap on ${path}`, wide.length === 0, wide.slice(0, 4).join("; "));
    }
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByRole("tab", { name: /Hidden/ }).click();
    await page.getByRole("button", { name: /^Why\? / }).first().click();
    await page.getByRole("dialog").waitFor();
    const drawer = await longTokenOverflow(page);
    check("320 px: long tokens wrap in the Why drawer", drawer.length === 0, drawer.slice(0, 4).join("; "));
    await page.keyboard.press("Escape");
    // The merge dialog's options carry Muse Spark's description of each person.
    await page.getByRole("button", { name: /^Same as / }).first().click();
    await page.getByRole("dialog").waitFor();
    const merge = await longTokenOverflow(page);
    check("320 px: long tokens wrap in the merge dialog", merge.length === 0, merge.slice(0, 4).join("; "));
    await context.close();
  }

  // A chip's ⋯ menu opens on screen even when its trigger wraps onto its own line.
  for (const [label, viewport, path, tab] of [
    ["320", { width: 320, height: 800 }, "/jobs/job-review-cafe", /Needs you/],
    ["1280", { width: 1280, height: 900 }, "/jobs/job-review-sample", null],
  ]) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    if (tab) await page.getByRole("tab", { name: tab }).click();
    const off = [];
    for (const trigger of await page.getByRole("button", { name: /^More actions for / }).all()) {
      if (!(await trigger.isVisible())) continue;
      await trigger.scrollIntoViewIfNeeded();
      await trigger.click();
      const box = await page.getByRole("menu").boundingBox();
      if (!box || box.x < 0 || box.x + box.width > viewport.width) off.push(`${await trigger.getAttribute("aria-label")} x=${box ? Math.round(box.x) : "?"}`);
      // Every item is visible, not under the fixed bottom bar.
      const hidden = await page.getByRole("menuitem").evaluateAll((items) =>
        items.filter((el) => {
          const r = el.getBoundingClientRect();
          return !el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
        }).length,
      );
      if (hidden) off.push(`${await trigger.getAttribute("aria-label")}: ${hidden} item(s) covered`);
      await page.keyboard.press("Escape");
    }
    check(`${label} px: every chip's ⋯ menu opens on screen, all items visible`, off.length === 0, off.slice(0, 3).join("; "));
    // The merge button reads as one phrase, with its space ("Same as Face 1…", not "Same asFace 1…").
    const mergeText = await page.locator("[data-btn=merge]").evaluateAll((els) => els.filter((e) => e.getClientRects().length).map((e) => e.innerText.trim()));
    check(`${label} px: the merge button reads "Same as …"`, mergeText.every((t) => /^Same as \S/.test(t)), mergeText.join(" | "));
    await context.close();
  }

  // 200% default text (a browser font setting, not zoom): the sticky player and fixed bar step aside on a phone (WCAG 1.4.4).
  {
    const big = await chromium.launch({ args: ["--blink-settings=defaultFontSize=32,minimumFontSize=0"] });
    const page = await (await big.newContext({ viewport: { width: 390, height: 844 } })).newPage();
    await page.goto(`${BASE}/jobs/job-review-cafe`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    await page.waitForTimeout(300);
    const band = await page.evaluate(() => {
      const css = getComputedStyle(document.documentElement);
      const top = parseFloat(css.getPropertyValue("--sticky-top")) || 0;
      const bottom = parseFloat(css.getPropertyValue("--sticky-bottom")) || 0;
      return { free: innerHeight - top - bottom, height: innerHeight };
    });
    check("200% text: the review page leaves room for the chips", band.free >= band.height * 0.4, `${Math.round(band.free)} of ${band.height}px free`);
    const tab = page.getByRole("tab", { name: /Needs you/ });
    await tab.scrollIntoViewIfNeeded();
    const reachable = await tab.evaluate((el) => {
      const r = el.getBoundingClientRect();
      return el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
    });
    check("200% text: the column tabs aren't covered", reachable);
    // The ⋯ menu stays within the screen though its rem width grows past a phone's.
    const off = [];
    for (const trigger of await page.getByRole("button", { name: /^More actions for / }).all()) {
      if (!(await trigger.isVisible())) continue;
      await trigger.scrollIntoViewIfNeeded();
      await trigger.click();
      const box = await page.getByRole("menu").boundingBox();
      if (!box || box.x < 0 || box.x + box.width > 390) off.push(`x=${box ? Math.round(box.x) : "?"} w=${box ? Math.round(box.width) : "?"}`);
      await page.keyboard.press("Escape");
    }
    check("200% text: every ⋯ menu stays on screen", off.length === 0, off.slice(0, 3).join("; "));
    // On a short landscape screen the Why sheet scrolls as a whole, not through a sliver.
    const landscape = await (await big.newContext({ viewport: { width: 844, height: 390 } })).newPage();
    await landscape.goto(`${BASE}/jobs/job-review-cafe`, { waitUntil: "networkidle" });
    await landscape.getByText(/hidden · /).waitFor();
    await landscape.getByRole("button", { name: /^Why\? / }).first().click();
    await landscape.getByRole("dialog").waitFor();
    const sheet = await landscape.locator("[data-drawer-body]").evaluate((el) => ({ h: el.clientHeight, overflow: getComputedStyle(el).overflowY, vh: innerHeight }));
    check("200% text, 844×390: the Why sheet's body isn't squeezed", sheet.overflow === "visible" || sheet.h >= sheet.vh * 0.4, `${sheet.h}px of ${sheet.vh} (${sheet.overflow})`);
    // A ⋯ menu left open while the screen turns keeps its cap.
    await landscape.keyboard.press("Escape");
    const turn = landscape.getByRole("button", { name: /^More actions for / }).first();
    await turn.scrollIntoViewIfNeeded();
    await turn.click();
    await landscape.setViewportSize({ width: 390, height: 844 });
    await landscape.waitForTimeout(200);
    const turned = await landscape.getByRole("menu").boundingBox();
    check("200% text: an open ⋯ menu stays on screen when the phone turns", !!turned && turned.x >= 0 && turned.x + turned.width <= 390, turned ? `x=${Math.round(turned.x)} w=${Math.round(turned.width)}` : "no menu");
    // 320 px at 200% text: a failed keyframe's message shows whole, and the sheet's title keeps a readable width.
    const narrow = await (await big.newContext({ viewport: { width: 320, height: 640 } })).newPage();
    await narrow.goto(`${BASE}/jobs/job-review-cafe`, { waitUntil: "networkidle" });
    await narrow.getByText(/hidden · /).waitFor();
    await narrow.getByRole("tab", { name: /Needs you/ }).click();
    await narrow.getByRole("button", { name: /^Why\? Screen 3,/ }).click();
    const failed = narrow.getByRole("dialog").getByText("The keyframe didn't load.");
    await failed.waitFor();
    const fit = await failed.evaluate((p) => p.parentElement.clientHeight >= p.offsetHeight);
    check("200% text, 320 px: a failed keyframe's message isn't cut off", fit);
    const title = await narrow.locator("#why-title").evaluate((h) => Math.round(h.getBoundingClientRect().width));
    check("200% text, 320 px: the Why sheet's title has room", title >= 150, `${title}px`);
    // Two evidence frames: the ◀ frames ▶ row wraps instead of widening the sheet.
    await narrow.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await narrow.getByText(/hidden · /).waitFor();
    await narrow.getByRole("button", { name: /^Why\? / }).first().click();
    await narrow.getByRole("button", { name: "Next evidence frame" }).waitFor();
    const sideways = await narrow.getByRole("dialog").evaluate((d) => d.scrollWidth - d.clientWidth);
    check("200% text, 320 px: the evidence-frame row fits the sheet", sideways <= 1, `${sideways}px`);
    // The header and the landing hero reflow too (Menu wraps under the wordmark; the hero's column can shrink).
    for (const path of ["/", "/privacy"]) {
      await narrow.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      const wide = await narrow.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      check(`200% text, 320 px: ${path} doesn't scroll sideways`, wide <= 0, `${wide}px`);
    }
    await big.close();
    // 125% text on a 1100 px screen: the layout JS and CSS agree, so the columns keep their names (headings or tabs).
    const mid = await chromium.launch({ args: ["--blink-settings=defaultFontSize=20,minimumFontSize=0"] });
    const wide = await (await mid.newContext({ viewport: { width: 1100, height: 800 } })).newPage();
    await wide.goto(`${BASE}/jobs/job-review-cafe`, { waitUntil: "networkidle" });
    await wide.getByText(/hidden · /).waitFor();
    const named = await wide.evaluate(() => ({
      tabs: document.querySelectorAll('[role="tab"]').length,
      headings: [...document.querySelectorAll("section h2")].filter((h) => getComputedStyle(h).display !== "none").length,
    }));
    check("125% text, 1100 px: the review columns are named", named.tabs === 3 || named.headings === 3, JSON.stringify(named));
    await mid.close();
    // At the default text size the phone layout keeps its sticky player.
    const normal = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
    await normal.goto(`${BASE}/jobs/job-review-cafe`, { waitUntil: "networkidle" });
    await normal.getByText(/hidden · /).waitFor();
    const position = await normal.locator("video").first().evaluate((el) => getComputedStyle(el.closest("[class*='bg-bg']")).position);
    check("100% text: the phone's player stays sticky", position === "sticky", position);
    await normal.context().close();
  }

  // A paused seek (Enter on a chip) redraws once the frame is decoded, so a pixelate cover shows as a
  // mosaic like the render (§3.6), not the solid stand-in drawn while the frame loads.
  {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    await page.locator("video").first().evaluate((el) => new Promise((res) => (el.readyState >= 2 ? res(true) : el.addEventListener("loadeddata", () => res(true), { once: true }))));
    const seeked = page.locator("video").first().evaluate((el) => new Promise((res) => el.addEventListener("seeked", () => res(true), { once: true })));
    await page.locator('[data-chip-id="i_2"]').focus();
    await page.keyboard.press("Enter");
    await seeked;
    await page.waitForTimeout(500);
    const colours = await page.evaluate(() => {
      const canvas = document.querySelector("canvas");
      const s = canvas.width / 1280;
      // The passer-by's padded face box on frame 75 (job-review-sample plan, style pixelate).
      const [x1, y1, x2, y2] = [826, 261, 904, 339].map((n) => Math.round(n * s));
      const data = canvas.getContext("2d").getImageData(x1, y1, x2 - x1, y2 - y1).data;
      const seen = new Set();
      for (let i = 0; i < data.length; i += 4) if (data[i + 3] > 200) seen.add(`${data[i] >> 3},${data[i + 1] >> 3},${data[i + 2] >> 3}`);
      return seen.size;
    });
    check("a paused seek draws a pixelate cover as a mosaic", colours >= 20, `${colours} colours`);
    await context.close();
  }

  // A paused scrub late in a frame (0.8 in) shows that frame: the overlay follows the frame on screen,
  // after the seek and after the Raw/Safe Cut toggle (§3.6 maps mediaTime, not currentTime).
  {
    const context = await browser.newContext({ viewport: { width: 1600, height: 1900 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    await page.locator("video").first().evaluate((el) => new Promise((res) => (el.readyState >= 2 ? res(true) : el.addEventListener("loadeddata", () => res(true), { once: true }))));
    // The passer-by's cover starts at x 39 on frame 202 and at x 32 on frame 203 (job-review-sample plan).
    const coveredAt = (x) =>
      page.evaluate((x) => {
        const canvas = document.querySelector("canvas");
        const s = canvas.width / 1280;
        return canvas.getContext("2d").getImageData(Math.round(x * s), Math.round(300 * s), 1, 1).data[3] > 200;
      }, x);
    await page.evaluate(async () => {
      const video = document.querySelector("video");
      video.pause();
      video.currentTime = 202.8 / 30;
      await new Promise((r) => video.addEventListener("seeked", r, { once: true }));
      await new Promise((r) => setTimeout(r, 400));
    });
    const afterSeek = [await coveredAt(34), await coveredAt(60)];
    await page.getByRole("radio", { name: "Raw" }).click();
    await page.getByRole("radio", { name: "Safe Cut" }).click();
    await page.waitForTimeout(300);
    const afterToggle = [await coveredAt(34), await coveredAt(60)];
    check("a paused scrub late in a frame draws that frame's covers, also after the toggle", !afterSeek[0] && afterSeek[1] && !afterToggle[0] && afterToggle[1], JSON.stringify({ afterSeek, afterToggle }));
    await context.close();
  }

  // Turning a tablet across the desktop breakpoint swaps tabs and columns: the focused chip keeps focus.
  {
    const context = await browser.newContext({ viewport: { width: 800, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/jobs/job-review-sample`, { waitUntil: "networkidle" });
    await page.getByText(/hidden · /).waitFor();
    const first = await page.locator("[data-chip-id]").first().getAttribute("data-chip-id");
    await page.locator(`[data-chip-id="${first}"]`).focus();
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.waitForTimeout(300);
    const wide = await page.evaluate(() => document.activeElement?.getAttribute("data-chip-id"));
    await page.setViewportSize({ width: 800, height: 900 });
    await page.waitForTimeout(300);
    const narrow = await page.evaluate(() => document.activeElement?.getAttribute("data-chip-id"));
    check("crossing the desktop breakpoint keeps focus on the chip", wide === first && narrow === first, `${first} → ${wide} → ${narrow}`);
    // Once the viewer clicks away (blank page, nothing focused), a later flip leaves focus alone.
    await page.mouse.click(5, 450);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.waitForTimeout(300);
    const after = await page.evaluate(() => document.activeElement?.getAttribute("data-chip-id") ?? null);
    check("after a click away, crossing the breakpoint doesn't pull focus back", after === null, String(after));
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
    // A 429 holds Continue until Retry-After (§10.3); it stays focusable.
    check("/try: a rate-limited Continue is held", (await cont.getAttribute("aria-disabled")) === "true");
    // A refusal that disables Start (401 on POST /v1/jobs: the `expired` mock code) takes focus itself.
    // A fresh page, so the held Continue doesn't wait out its minute.
    await page.goto(`${BASE}/try`, { waitUntil: "networkidle" });
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
    check("/try: the expired code says it expired, on any date", await page.getByText(/^This code has expired\. It worked until /).isVisible());
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
