#!/usr/bin/env node
// Renders the synthetic sample scene (sample-scene.mjs) into public/sample/:
// prepared.mp4 (raw), redacted.mp4 (Safe Cut result), poster.jpg, Set-of-Mark
// keyframes, the blur-every-face vs Safe Cut stills, captions.vtt, and a
// sample receipt. Needs ffmpeg on PATH. Usage: node scripts/gen-sample.mjs
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { BAR_H, FPS, FRAMES, H, KEYFRAMES, SAMPLE_ITEMS, SAMPLE_TURNS, W, entitiesAt, sampleJob, samplePlan, sampleTracks } from "./sample-scene.mjs";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "sample");
const FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf";
mkdirSync(join(OUT, "som"), { recursive: true });

// ---------------------------------------------------------------- raster helpers (RGB24)
function fillRect(buf, [x1, y1, x2, y2], [r, g, b]) {
  for (let y = Math.max(0, y1); y < Math.min(H, y2); y += 1) {
    let i = (y * W + Math.max(0, x1)) * 3;
    for (let x = Math.max(0, x1); x < Math.min(W, x2); x += 1) {
      buf[i] = r; buf[i + 1] = g; buf[i + 2] = b; i += 3;
    }
  }
}
function fillCircle(buf, { cx, cy, r }, [cr, cg, cb]) {
  for (let y = Math.max(0, Math.floor(cy - r)); y < Math.min(H, Math.ceil(cy + r)); y += 1) {
    for (let x = Math.max(0, Math.floor(cx - r)); x < Math.min(W, Math.ceil(cx + r)); x += 1) {
      if ((x - cx) ** 2 + (y - cy) ** 2 <= r * r) {
        const i = (y * W + x) * 3;
        buf[i] = cr; buf[i + 1] = cg; buf[i + 2] = cb;
      }
    }
  }
}
function pixelate(buf, [x1, y1, x2, y2], [gx, gy, cell]) {
  // Cells are locked to the item's grid origin so they don't shimmer between frames (DESIGN §2.7).
  const startX = gx + Math.floor((x1 - gx) / cell) * cell;
  const startY = gy + Math.floor((y1 - gy) / cell) * cell;
  for (let cy = startY; cy < y2; cy += cell) {
    for (let cx = startX; cx < x2; cx += cell) {
      const bx1 = Math.max(cx, x1, 0), by1 = Math.max(cy, y1, 0), bx2 = Math.min(cx + cell, x2, W), by2 = Math.min(cy + cell, y2, H);
      if (bx2 <= bx1 || by2 <= by1) continue;
      let r = 0, g = 0, b = 0, n = 0;
      for (let y = by1; y < by2; y += 1) for (let x = bx1; x < bx2; x += 1) { const i = (y * W + x) * 3; r += buf[i]; g += buf[i + 1]; b += buf[i + 2]; n += 1; }
      fillRect(buf, [bx1, by1, bx2, by2], [Math.round(r / n), Math.round(g / n), Math.round(b / n)]);
    }
  }
}
function boxBlur(buf, [x1, y1, x2, y2]) {
  // A heavy blur for the "blur every face" baseline still.
  const cell = Math.max(6, Math.round((x2 - x1) / 5));
  pixelate(buf, [x1, y1, x2, y2], [x1, y1, cell]);
  pixelate(buf, [x1, y1, x2, y2], [x1 + Math.round(cell / 2), y1 + Math.round(cell / 2), cell]);
}

const SKIN = [[198, 134, 96], [141, 85, 54], [224, 172, 125], [110, 70, 45]];
const background = (() => {
  const buf = Buffer.alloc(W * H * 3);
  for (let y = 0; y < H; y += 1) {
    const sky = y < 330;
    const c = sky ? [150 + Math.round(y / 6), 178 + Math.round(y / 8), 205] : [128 - Math.round((y - 330) / 9), 120 - Math.round((y - 330) / 10), 112 - Math.round((y - 330) / 11)];
    fillRect(buf, [0, y, W, y + 1], c);
  }
  fillRect(buf, [0, 90, 300, 400], [176, 112, 84]);
  fillRect(buf, [640, 120, 900, 420], [92, 118, 140]);
  fillRect(buf, [960, 60, 1280, 430], [214, 196, 160]);
  fillRect(buf, [40, 140, 120, 220], [70, 80, 96]);
  fillRect(buf, [170, 140, 250, 220], [70, 80, 96]);
  fillRect(buf, [0, 470, W, 478], [210, 204, 190]);
  return buf;
})();

function drawFigure(buf, fig, body, skin) {
  if (!fig) return;
  fillRect(buf, fig.body, body);
  fillCircle(buf, fig.head, skin);
  drawFeatures(buf, fig.head);
}
/** Eyes, brows and a mouth, so a covered face visibly loses its features. */
function drawFeatures(buf, { cx, cy, r }) {
  const e = Math.max(2, Math.round(r / 6));
  const dark = [35, 25, 20];
  for (const side of [-1, 1]) {
    const ex = Math.round(cx + side * r * 0.38);
    const ey = Math.round(cy - r * 0.15);
    fillRect(buf, [ex - e, ey - e, ex + e, ey + e], dark);
    fillRect(buf, [ex - 2 * e, ey - 3 * e, ex + 2 * e, ey - 2 * e], dark);
  }
  fillRect(buf, [Math.round(cx - r * 0.35), Math.round(cy + r * 0.38), Math.round(cx + r * 0.35), Math.round(cy + r * 0.38) + e], [150, 40, 40]);
}

/** The raw prepared frame. */
function rawFrame(f) {
  const buf = Buffer.from(background);
  const e = entitiesAt(f);
  fillRect(buf, e.screen, [32, 40, 56]);
  fillRect(buf, [e.screen[0] + 10, e.screen[1] + 12, e.screen[2] - 50, e.screen[1] + 24], [120, 200, 140]);
  fillRect(buf, [e.screen[0] + 10, e.screen[1] + 36, e.screen[2] - 20, e.screen[1] + 48], [230, 230, 230]);
  fillRect(buf, [e.screen[0] + 10, e.screen[1] + 60, e.screen[2] - 70, e.screen[1] + 72], [120, 200, 140]);
  fillRect(buf, e.car, [52, 96, 160]);
  fillRect(buf, [e.car[0] + 40, e.car[1] - 50, e.car[2] - 60, e.car[1]], [44, 80, 136]);
  fillRect(buf, e.plate, [245, 230, 80]);
  for (let k = 0; k < 6; k += 1) fillRect(buf, [e.plate[0] + 8 + k * 15, e.plate[1] + 7, e.plate[0] + 18 + k * 15, e.plate[3] - 7], [20, 20, 20]);
  drawFigure(buf, e.watcher, [70, 70, 80], SKIN[3]);
  drawFigure(buf, e.child, [220, 60, 120], SKIN[2]);
  // The passer-by crosses in front of the guest between frames 140 and 175, hiding her face (150–165).
  if (!e.passerInFront) drawFigure(buf, e.passer, [60, 130, 90], SKIN[1]);
  drawFigure(buf, e.guest, [232, 120, 40], SKIN[0]);
  if (e.passerInFront) drawFigure(buf, e.passer, [60, 130, 90], SKIN[1]);
  return buf;
}

/** The Safe Cut render: the sample decisions with the re-entry merged into the guest. */
const finalItems = SAMPLE_ITEMS.filter((i) => i.item_id !== "i_7").map((i) => (i.decision === "needs_you" ? { ...i, decision: "hide" } : i));
const finalPlan = samplePlan(finalItems, sampleTracks());
function redact(buf, f) {
  for (const region of finalPlan.frames[String(f)] ?? []) {
    if (region.style === "pixelate" && region.grid) pixelate(buf, region.box, region.grid);
    else fillRect(buf, region.box, [24, 24, 28]);
  }
  return buf;
}

function ffmpeg(args, input) {
  return new Promise((resolve, reject) => {
    const p = spawn("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args], { stdio: ["pipe", "inherit", "inherit"] });
    p.on("close", (code) => (code === 0 ? resolve() : reject(new Error(`ffmpeg exited ${code}`))));
    if (input) {
      (async () => {
        for (const chunk of input()) if (!p.stdin.write(chunk)) await new Promise((r) => p.stdin.once("drain", r));
        p.stdin.end();
      })();
    } else {
      p.stdin.end();
    }
  });
}
const RAW_IN = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", `${W}x${H}`, "-r", String(FPS), "-i", "-"];
const H264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "30", "-movflags", "+faststart", "-an"];

async function main() {
  await ffmpeg([...RAW_IN, ...H264, join(OUT, "prepared.mp4")], function* () { for (let f = 0; f < FRAMES; f += 1) yield rawFrame(f); });
  await ffmpeg([...RAW_IN, ...H264, join(OUT, "redacted.mp4")], function* () { for (let f = 0; f < FRAMES; f += 1) yield redact(rawFrame(f), f); });
  await ffmpeg(["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", `${W}x${H}`, "-i", "-", "-frames:v", "1", "-q:v", "4", join(OUT, "poster.jpg")], function* () { yield redact(rawFrame(0), 0); });

  // Set-of-Mark keyframes exactly as PRE-A specifies: the frame unscaled under a black bar with the frame number, labels burned in.
  const tracks = sampleTracks();
  const esc = (s) => s.replace(/\\/g, "\\\\").replace(/:/g, "\\:").replace(/'/g, "\\'");
  for (const f of KEYFRAMES) {
    const draws = [`drawtext=fontfile=${FONT}:text='F ${String(f).padStart(6, "0")}':x=12:y=8:fontsize=24:fontcolor=white`];
    for (const t of tracks) {
      const box = t.boxes[String(f)];
      if (!box) continue;
      const [x1, y1, x2, y2] = box;
      draws.push(`drawbox=x=${x1}:y=${y1 + BAR_H}:w=${x2 - x1}:h=${y2 - y1}:color=yellow@0.9:t=2`);
      draws.push(`drawtext=fontfile=${FONT}:text='${esc(t.track_id)}':x=${x1 + 2}:y=${Math.max(BAR_H, y1 + BAR_H - 20)}:fontsize=16:fontcolor=black:box=1:boxcolor=yellow@0.9:boxborderw=2`);
    }
    await ffmpeg(["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", `${W}x${H}`, "-i", "-", "-vf", [`pad=${W}:${H + BAR_H}:0:${BAR_H}:black`, ...draws].join(","), "-frames:v", "1", "-q:v", "4", join(OUT, "som", `${String(f).padStart(6, "0")}.jpg`)], function* () { yield rawFrame(f); });
  }

  // The landing side-by-side at the same moment: blur every face (guest hidden, plate visible) vs Safe Cut.
  const still = 120;
  const blurAll = rawFrame(still);
  for (const t of tracks) if (t.concept === "face" && t.boxes[String(still)]) boxBlur(blurAll, t.boxes[String(still)]);
  await ffmpeg(["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", `${W}x${H}`, "-i", "-", "-frames:v", "1", "-q:v", "4", join(OUT, "blur-every-face.jpg")], function* () { yield blurAll; });
  await ffmpeg(["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", `${W}x${H}`, "-i", "-", "-frames:v", "1", "-q:v", "4", join(OUT, "safe-cut.jpg")], function* () { yield redact(rawFrame(still), still); });

  const ts = (s) => `00:00:${s.toFixed(3).padStart(6, "0")}`;
  writeFileSync(join(OUT, "captions.vtt"), `WEBVTT\n\n${SAMPLE_TURNS.map((t, i) => `${i + 1}\n${ts(t.start)} --> ${ts(t.end)}\n${t.speaker === "S1" ? "Host" : "Guest"}: ${t.text}\n`).join("\n")}`);

  const job = sampleJob();
  const receipt = {
    job_id: job.job_id, sample: true,
    items: finalItems.map((i) => ({ item_id: i.item_id, track_ids: i.track_ids, kind: i.kind, decision: i.decision, reason: i.reason, decided_by: i.decided_by, style: i.style })),
    audit: { auditor: "egoblur-gen2", frames_scanned: FRAMES, leaks_found: 1, leaks_patched: 1, unresolved: 0, passes: 2, blocked_reason: null },
    models: job.models,
    data_handling: { mode: "standard", store: false, files_deleted: true },
    approved_by: "creator", approved_at: "2026-10-27T10:20:00Z", cost_usd: null,
  };
  writeFileSync(join(OUT, "receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`);
  const rows = receipt.items.map((i) => `<tr><td>${i.track_ids.join(", ")}</td><td>${i.kind}</td><td>${i.decision === "keep" ? "Kept clear" : "Hidden"}</td><td>${i.reason}</td><td>${i.decided_by === "creator" ? "You" : i.decided_by === "model" ? "Muse Spark" : "Safe Cut's rules"}</td></tr>`).join("");
  writeFileSync(join(OUT, "receipt.html"), `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Privacy receipt (sample)</title><style>body{font:14px/1.5 system-ui,sans-serif;margin:16px;color:#1d1d1f;background:#fff}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}th{font-weight:600}p.note{color:#555}@media (prefers-color-scheme:dark){body{background:#151517;color:#eee}td,th{border-color:#333}p.note{color:#aaa}}</style></head><body><h1>Privacy receipt</h1><p class="note">Sample receipt for the synthetic demo scene. Real receipts are written by the pipeline (WP4) and hash-chained.</p><table><thead><tr><th scope="col">Tracks</th><th scope="col">Kind</th><th scope="col">Decision</th><th scope="col">Reason</th><th scope="col">Decided by</th></tr></thead><tbody>${rows}</tbody></table><h2>Audit</h2><p>${FRAMES} of ${FRAMES} frames checked. 1 leak found and fixed. Nothing left to fix.</p><h2>Models</h2><p>Muse Spark (roles, scene) · SAM 3.1 (tracking) · Muse Voice Transcribe (speech) · EgoBlur Gen 2 (audit)</p><h2>Data handling</h2><p>Meta Model API, requested with Standard model IDs only (never a Contributor model ID); uploaded files deleted after use.</p></body></html>\n`);
  console.log(`wrote sample media to ${OUT}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
