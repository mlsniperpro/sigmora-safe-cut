// A synthetic street-interview scene for mock mode: drawn shapes, no real
// people, so it needs no release. The motion here drives both the rendered
// media (gen-sample.mjs) and the job JSON (gen-mocks.mjs), so boxes, plan and
// pixels always agree.

export const W = 1280;
export const H = 720;
export const FPS = 30;
export const FRAMES = 240;
export const BAR_H = 40;
export const KEYFRAMES = [15, 75, 135, 195];

const clampBox = ([x1, y1, x2, y2]) => [Math.max(0, Math.round(x1)), Math.max(0, Math.round(y1)), Math.min(W, Math.round(x2)), Math.min(H, Math.round(y2))];
const visible = ([x1, y1, x2, y2]) => x2 - x1 >= 4 && y2 - y1 >= 4;

/** A person drawn as a head circle on a body block. */
function figure(cx, headY, r, bodyH, bodyW) {
  return {
    head: { cx, cy: headY, r },
    face: clampBox([cx - r, headY - r, cx + r, headY + r]),
    body: clampBox([cx - bodyW / 2, headY - r, cx + bodyW / 2, headY + r + bodyH]),
  };
}

/** Per-frame geometry of every entity, or null when off screen. */
export function entitiesAt(f) {
  const sway = Math.sin(f / 9) * 4;
  const guest = figure(450 + sway, 232, 38, 380, 120);
  const passerX = 1330 - f * 6.2;
  const passer = passerX > -60 && passerX < W + 60 ? figure(passerX, 300, 24, 230, 70) : null;
  const childX = f >= 60 && f <= 200 ? 620 + (f - 60) * 3.1 : null;
  const child = childX === null ? null : figure(childX, 430, 17, 120, 44);
  const watcher = f >= 90 ? figure(1110, 250, 31, 300, 96) : null;
  return {
    guest,
    // The tracker loses the guest's face while the passer-by crosses in front (frames 150–165).
    guestFaceVisible: !(f >= 150 && f <= 165),
    passer,
    child,
    watcher,
    plate: clampBox([1030, 638, 1130, 668]),
    car: clampBox([880, 520, 1262, 690]),
    screen: clampBox([690, 170, 850, 280]),
  };
}

/** Track ID → per-frame box, plus first/last. Mirrors what WP1's tracker would emit. */
export function sampleTracks() {
  const tracks = new Map();
  const put = (id, concept, f, box, reentryOf = null) => {
    if (!box || !visible(box)) return;
    let t = tracks.get(id);
    if (!t) {
      t = { track_id: id, concept, first: f, last: f, reentry_of: reentryOf, boxes: {} };
      tracks.set(id, t);
    }
    t.last = f;
    t.boxes[String(f)] = box;
  };
  for (let f = 0; f < FRAMES; f += 1) {
    const e = entitiesAt(f);
    if (f < 150) put("face:1", "face", f, e.guest.face);
    if (f > 165) put("face:8", "face", f, e.guest.face, "face:1");
    put("person:1", "person", f, e.guest.body);
    if (e.passer) {
      put("face:3", "face", f, e.passer.face);
      put("person:2", "person", f, e.passer.body);
    }
    if (e.child) put("face:4", "face", f, e.child.face);
    if (e.watcher) {
      put("face:6", "face", f, e.watcher.face);
      put("person:5", "person", f, e.watcher.body);
    }
    put("license plate:1", "license plate", f, e.plate);
    put("screen:2", "screen", f, e.screen);
  }
  return [...tracks.values()];
}

export const SAMPLE_TURNS = [
  { speaker: "S1", start: 0.2, end: 1.6, text: "So, what brings you to the market today?" },
  { speaker: "S2", start: 1.8, end: 4.4, text: "Hi, I'm Amina. I come here every Saturday for the spices." },
  { speaker: "S1", start: 4.6, end: 5.6, text: "And which stall is the best?" },
  { speaker: "S2", start: 5.8, end: 7.6, text: "The one at the corner. Ask for the red pepper." },
];

/** The decisions WP3 would make for this scene (UI-SPEC §3.3 chip states, one of each). */
export const SAMPLE_ITEMS = [
  { item_id: "i_1", track_ids: ["face:1", "person:1"], kind: "person", decision: "keep", reason: "the guest: introduces herself at the start, speaks to camera", evidence_frames: [15, 75], style: null, decided_by: "policy", locked: false, removed_by_creator: false },
  { item_id: "i_2", track_ids: ["face:3", "person:2"], kind: "person", decision: "hide", reason: "passer-by: walks behind the guest, never addresses the camera", evidence_frames: [75], style: "pixelate", decided_by: "policy", locked: false, removed_by_creator: false },
  { item_id: "i_3", track_ids: ["face:4"], kind: "child", decision: "hide", reason: "child in the background, not addressed", evidence_frames: [135], style: "solid", decided_by: "policy", locked: true, removed_by_creator: false },
  { item_id: "i_4", track_ids: ["license plate:1"], kind: "plate", decision: "hide", reason: "number plate on a parked car, characters legible", evidence_frames: [15], style: "solid", decided_by: "policy", locked: false, removed_by_creator: false },
  { item_id: "i_5", track_ids: ["face:6", "person:5"], kind: "person", decision: "needs_you", reason: "looks at the camera; checks disagreed", evidence_frames: [135, 195], style: "pixelate", decided_by: "model", locked: false, removed_by_creator: false },
  { item_id: "i_6", track_ids: ["screen:2"], kind: "screen", decision: "hide", reason: "shop screen showing a chat with names", evidence_frames: [75], style: "solid", decided_by: "policy", locked: false, removed_by_creator: false },
  { item_id: "i_7", track_ids: ["face:8"], kind: "person", decision: "hide", reason: "appeared again after the tracker lost them; might be Face 1", evidence_frames: [195], style: "pixelate", decided_by: "policy", locked: false, removed_by_creator: false },
];

export const SAMPLE_ROLES = {
  status: "ok",
  model: "muse-spark-1.3",
  tracks: [
    { track_id: "face:1", role: "participant", votes: ["participant", "participant", "participant"], failed_votes: 0, escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: 0, evidence: "introduces herself at F 000015 (\"Hi, I'm Amina\"), answers the host at F 000075", frames: [15, 75] },
    { track_id: "face:3", role: "bystander", votes: ["bystander", "bystander", "bystander"], failed_votes: 0, escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: null, evidence: "walks behind the guest at F 000075, never looks at or addresses the camera", frames: [75] },
    { track_id: "face:4", role: "child", votes: ["child", "child", "child"], failed_votes: 0, escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: null, evidence: "small child crossing behind the guest at F 000135", frames: [135] },
    { track_id: "face:6", role: "unsure", votes: ["bystander", "participant", "bystander"], failed_votes: 0, escalated: true, suggested_role: "bystander", escalation_evidence: "faces the lens at F 000135 and F 000195 but is never addressed and never speaks", escalation_frames: [135, 195], matches_participant: null, evidence: "stands at the right and looks at the camera at frames 135 and 195, never speaks", frames: [135, 195] },
    { track_id: "face:8", role: "unsure", votes: ["participant", "unsure", "participant"], failed_votes: 0, escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: 0, evidence: "same jacket and position as the guest at F 000195", frames: [195] },
  ],
  objects: [
    { track_id: "license plate:1", sensitive: true, content: "number plate, characters legible", frames: [15] },
    { track_id: "screen:2", sensitive: true, content: "chat window with names and messages", frames: [75] },
  ],
  missed: [],
  keyframes: KEYFRAMES.map((f) => `som/${String(f).padStart(6, "0")}.jpg`),
};

export const SAMPLE_SCENE = {
  status: "ok",
  model: "muse-spark-1.3",
  summary: "street interview at a market: the host (off camera) talks to a guest; people pass behind",
  participants: [
    { description: "woman in the orange jacket", evidence: "introduces herself: \"Hi, I'm Amina\"", speaker: "S2", introduced_in_turn: 1, introduction_quote: "I'm Amina", is_creator: false },
    { description: "the host holding the camera", evidence: "asks the questions", speaker: "S1", introduced_in_turn: null, introduction_quote: null, is_creator: true },
  ],
  children: [{ description: "small child crossing behind the guest" }],
  others_present: "a passer-by and a man watching from the right",
  candidate_objects: [
    { what: "parked car with a visible number plate", approx_time: "throughout" },
    { what: "shop screen showing a chat", approx_time: "throughout" },
  ],
};

export function padBox([x1, y1, x2, y2], frac, px) {
  const dx = (x2 - x1) * frac + px;
  const dy = (y2 - y1) * frac + px;
  return clampBox([x1 - dx, y1 - dy, x2 + dx, y2 + dy]);
}

/**
 * plan.json for the given items: each hidden or needs-you item covered on every
 * frame its tracks are visible (face padding 15%, others 8%, plus 8 px; WP3).
 * `wholePerson` items use their person track.
 */
export function samplePlan(items, tracks) {
  const byId = new Map(tracks.map((t) => [t.track_id, t]));
  const frames = {};
  for (const item of items) {
    if (item.decision === "keep") continue;
    const ids = item.style === "person_solid" ? item.track_ids.filter((t) => t.startsWith("person:")) : item.track_ids.filter((t) => !t.startsWith("person:"));
    for (const id of ids.length ? ids : item.track_ids) {
      const track = byId.get(id);
      if (!track) continue;
      let grid = null;
      for (const [f, box] of Object.entries(track.boxes)) {
        const padded = padBox(box, track.concept === "face" ? 0.15 : 0.08, 8);
        if (item.style === "pixelate" && grid === null) grid = [padded[0], padded[1], Math.max(4, Math.ceil((padded[2] - padded[0]) / 6))];
        (frames[f] ??= []).push({ item_id: item.item_id, shape: "box", box: padded, mask: null, style: item.style ?? "solid", grid: item.style === "pixelate" ? grid : null });
      }
    }
  }
  return { padding: { face: 0.15, default: 0.08, px: 8 }, temporal: { extend: 8, backfill: 15, gap_hold_s: 2.0 }, frames, crowd_fills: [] };
}

/** The sample job as `GET /v1/jobs/{id}` would return it in `review`. */
export function sampleJob(mediaBase = "/sample") {
  const tracks = sampleTracks();
  const kf = (f) => `${mediaBase}/som/${String(f).padStart(6, "0")}.jpg`;
  return {
    job_id: "job-review-sample",
    mode: "live",
    status: "review",
    stage: "review",
    progress: 1,
    deletes_at: "2026-10-28T11:00:00Z",
    has_render: false,
    job: {
      fps: FPS, width: W, height: H, frames: FRAMES, audio: true,
      times: Array.from({ length: FRAMES }, (_, i) => i / FPS),
      created_at: "2026-10-27T10:00:00Z",
      prepared_url: `${mediaBase}/prepared.mp4`,
      source_name: "market-interview.mp4",
    },
    items: SAMPLE_ITEMS,
    tracks,
    roles: SAMPLE_ROLES,
    plan: samplePlan(SAMPLE_ITEMS, tracks),
    transcript: { status: "ok", source: "muse-voice-transcribe-1.0", source_kind: "primary", degraded: false, turns: SAMPLE_TURNS },
    scene: SAMPLE_SCENE,
    keyframe_geometry: { bar_h: BAR_H, frame_width: W, frame_height: H, image_width: W, image_height: H + BAR_H },
    keyframe_urls: Object.fromEntries(KEYFRAMES.map((f) => [String(f), kf(f)])),
    models: { scene: "muse-spark-1.3", roles: "muse-spark-1.3", sam: "sam-3.1", asr: "muse-voice-transcribe-1.0" },
  };
}
