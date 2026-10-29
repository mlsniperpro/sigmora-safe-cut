#!/usr/bin/env node
// Builds web/mocks/*.json from the UI-SPEC §10.1 hero, café and speech mocks.
// Every other fixture is derived from those three, so they can't drift apart.
// Usage: node scripts/gen-mocks.mjs [--check]
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { sampleJob } from "./sample-scene.mjs";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "mocks");
const clone = (v) => structuredClone(v);
const DELETES_AT = "2026-10-28T11:00:00Z";
const times = (n, fps) => Array.from({ length: n }, (_, i) => i / fps);
const kfUrl = (job, f) => `https://example.invalid/${job}/som/${String(f).padStart(6, "0")}.jpg`;
const kfName = (f) => `som/${String(f).padStart(6, "0")}.jpg`;

// ---------------------------------------------------------------- UI-SPEC §10.1 hero mock (verbatim)
const hero = {
  job_id: "j_hero1", mode: "live", status: "review", stage: "review", progress: 1.0,
  deletes_at: DELETES_AT,
  job: {
    fps: 30, width: 1280, height: 720, frames: 12, audio: true,
    times: [0.0, 0.03333333333333333, 0.06666666666666667, 0.1, 0.13333333333333333, 0.16666666666666666, 0.2, 0.23333333333333334, 0.26666666666666666, 0.3, 0.3333333333333333, 0.36666666666666664],
    created_at: "2026-10-27T10:00:00Z",
    prepared_url: "https://example.invalid/j_hero1/prepared.mp4",
  },
  items: [
    { item_id: "i_1", track_ids: ["face:2", "person:1"], kind: "person", decision: "keep",
      reason: "the guest: introduced at the start, speaks to camera", evidence_frames: [3, 9],
      style: null, decided_by: "policy", locked: false, removed_by_creator: false },
    { item_id: "i_2", track_ids: ["face:4"], kind: "child", decision: "hide",
      reason: "child in the background, not addressed", evidence_frames: [6],
      style: "solid", decided_by: "policy", locked: true, removed_by_creator: false },
    { item_id: "i_3", track_ids: ["license plate:1"], kind: "plate", decision: "hide",
      reason: "number plate on a parked car", evidence_frames: [1],
      style: "solid", decided_by: "policy", locked: false, removed_by_creator: false },
    { item_id: "i_4", track_ids: ["face:6"], kind: "person", decision: "needs_you",
      reason: "looks at the camera; checks disagreed", evidence_frames: [9],
      style: "pixelate", decided_by: "model", locked: false, removed_by_creator: false },
  ],
  tracks: [
    { track_id: "face:2", concept: "face", first: 0, last: 11, reentry_of: null,
      boxes: { 3: [400, 120, 470, 210], 9: [410, 122, 480, 212] } },
    { track_id: "person:1", concept: "person", first: 0, last: 11, reentry_of: null,
      boxes: { 3: [360, 100, 560, 700], 9: [370, 102, 570, 700] } },
    { track_id: "face:4", concept: "face", first: 4, last: 10, reentry_of: null,
      boxes: { 6: [900, 200, 940, 250] } },
    { track_id: "license plate:1", concept: "license plate", first: 0, last: 11, reentry_of: null,
      boxes: { 1: [1050, 560, 1150, 590] } },
    { track_id: "face:6", concept: "face", first: 8, last: 11, reentry_of: null,
      boxes: { 9: [700, 150, 750, 215] } },
  ],
  roles: {
    status: "ok",
    tracks: [
      { track_id: "face:2", role: "participant", votes: ["participant", "participant", "participant"], escalated: false,
        suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: 0,
        evidence: "introduced at F 000003, speaks to camera at F 000003 and F 000009", frames: [3, 9] },
      { track_id: "face:4", role: "child", votes: ["child", "child", "child"], escalated: false,
        suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: null,
        evidence: "small person walking with an adult behind the guest at F 000006", frames: [6] },
      { track_id: "face:6", role: "unsure", votes: ["bystander", "participant", "bystander"], escalated: true,
        suggested_role: "bystander", escalation_evidence: "faces the lens at F 000009 but is never addressed and never speaks", escalation_frames: [9],
        matches_participant: null, evidence: "Judges disagreed: looks at the camera at frame 9, never speaks", frames: [9] },
    ],
    objects: [{ track_id: "license plate:1", sensitive: true, content: "number plate, characters legible", frames: [1] }],
    missed: [], keyframes: [kfName(1), kfName(3), kfName(6), kfName(9)],
  },
  keyframe_geometry: { bar_h: 40, frame_width: 1280, frame_height: 720, image_width: 1280, image_height: 760 },
  keyframe_urls: { 1: kfUrl("j_hero1", 1), 3: kfUrl("j_hero1", 3), 6: kfUrl("j_hero1", 6), 9: kfUrl("j_hero1", 9) },
  plan: {
    frames: {
      1: [{ item_id: "i_3", shape: "box", box: [1042, 552, 1158, 598], mask: null, style: "solid", grid: null }],
      6: [{ item_id: "i_2", shape: "box", box: [894, 193, 946, 257], mask: null, style: "solid", grid: null }],
      9: [{ item_id: "i_4", shape: "box", box: [692, 140, 758, 225], mask: null, style: "pixelate", grid: [692, 140, 11] }],
    },
    crowd_fills: [],
  },
  transcript: {
    status: "ok", source: "muse-voice-transcribe-1.0", source_kind: "primary", degraded: false,
    turns: [
      { speaker: "S1", start: 0.0, end: 0.1, text: "So, who are you?" },
      { speaker: "S2", start: 0.1, end: 0.3, text: "Hi, I'm Amina, and today…" },
    ],
  },
  scene: {
    status: "ok", model: "muse-spark-1.3", summary: "street interview with a guest",
    participants: [
      { description: "woman in yellow jacket", evidence: "introduces herself at the start: \"Hi, I'm Amina\"", speaker: "S2", introduced_in_turn: 1, introduction_quote: "I'm Amina", is_creator: false },
      { description: "man holding the microphone", evidence: "asks the questions", speaker: "S1", introduced_in_turn: null, introduction_quote: null, is_creator: true },
    ],
    children: [{ description: "small child walking with an adult behind the guest" }],
    others_present: "a few passers-by behind the guest",
    candidate_objects: [{ what: "parked car with a visible number plate", approx_time: "throughout" }],
  },
};

// ---------------------------------------------------------------- UI-SPEC §10.1 speech-fallback mock (verbatim)
const speech = {
  job_id: "j_speech", mode: "live", status: "review", stage: "review", progress: 1.0, deletes_at: DELETES_AT,
  job: { fps: 10, width: 1280, height: 720, frames: 40, audio: true, times: times(40, 10), created_at: "2026-10-27T10:00:00Z", prepared_url: "https://example.invalid/j_speech/prepared.mp4" },
  items: [
    { item_id: "i_1", track_ids: ["face:1"], kind: "person", decision: "keep", reason: "the host, talks to camera throughout", evidence_frames: [10, 30], style: null, decided_by: "policy", locked: false, removed_by_creator: false },
    { item_id: "i_4", track_ids: ["face:4"], kind: "person", decision: "hide", reason: "passer-by, never addressed", evidence_frames: [30], style: "pixelate", decided_by: "policy", locked: false, removed_by_creator: false },
  ],
  tracks: [
    { track_id: "face:1", concept: "face", first: 0, last: 39, reentry_of: null, boxes: { 10: [400, 120, 470, 210], 30: [410, 122, 480, 212] } },
    { track_id: "face:4", concept: "face", first: 25, last: 39, reentry_of: null, boxes: { 30: [900, 200, 940, 250] } },
  ],
  roles: {
    status: "ok",
    tracks: [
      { track_id: "face:1", role: "participant", votes: ["participant", "participant", "participant"], escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: 0, evidence: "talks to camera at F 000010 and F 000030", frames: [10, 30] },
      { track_id: "face:4", role: "bystander", votes: ["bystander", "bystander", "bystander"], escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: null, evidence: "walks behind the host at F 000030, never addressed", frames: [30] },
    ],
    objects: [], missed: [], keyframes: [kfName(10), kfName(30)],
  },
  keyframe_geometry: { bar_h: 40, frame_width: 1280, frame_height: 720, image_width: 1280, image_height: 760 },
  keyframe_urls: { 10: kfUrl("j_speech", 10), 30: kfUrl("j_speech", 30) },
  plan: { frames: { 30: [{ item_id: "i_4", shape: "box", box: [894, 193, 946, 257], mask: null, style: "pixelate", grid: [894, 193, 9] }] }, crowd_fills: [] },
  transcript: { status: "ok", source: "muse-spark-1.2", source_kind: "fallback", degraded: false, turns: [{ speaker: "S1", start: 1.2, end: 1.8, text: "Welcome back to the market." }] },
  scene: { status: "ok", model: "muse-spark-1.3", summary: "walk-and-talk vlog in a market", participants: [{ description: "man holding the camera", evidence: "talks to camera throughout", speaker: "S1", introduced_in_turn: null, introduction_quote: null, is_creator: true }], children: [], others_present: "shoppers passing behind the host", candidate_objects: [] },
};

// ---------------------------------------------------------------- UI-SPEC §10.1 café mock (fields not shown come from the hero)
const cafe = {
  ...clone(hero),
  job_id: "j_cafe",
  items: [
    { item_id: "i_1", track_ids: ["face:1"], kind: "person", decision: "keep", reason: "the host: speaks to camera throughout", evidence_frames: [2, 7], style: null, decided_by: "policy", locked: false, removed_by_creator: false },
    { item_id: "i_5", track_ids: ["screen:2"], kind: "screen", decision: "hide", reason: "laptop showing an email inbox with names", evidence_frames: [4], style: "solid", decided_by: "policy", locked: false, removed_by_creator: false },
    { item_id: "i_6", track_ids: ["screen:3"], kind: "screen", decision: "needs_you", reason: "menu, nothing personal", evidence_frames: [4, 7], style: "solid", decided_by: "policy", locked: false, removed_by_creator: false },
  ],
  tracks: [
    { track_id: "face:1", concept: "face", first: 0, last: 11, reentry_of: null, boxes: { 2: [300, 120, 370, 210], 7: [305, 121, 375, 211] } },
    { track_id: "screen:2", concept: "screen", first: 0, last: 11, reentry_of: null, boxes: { 4: [700, 400, 900, 520] } },
    { track_id: "screen:3", concept: "screen", first: 0, last: 11, reentry_of: null, boxes: { 4: [950, 410, 1150, 530], 7: [950, 410, 1150, 530] } },
  ],
  roles: {
    status: "ok",
    tracks: [{ track_id: "face:1", role: "participant", votes: ["participant", "participant", "participant"], escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null, matches_participant: 0, evidence: "speaks to camera at F 000002 and F 000007", frames: [2, 7] }],
    objects: [
      { track_id: "screen:2", sensitive: true, content: "email inbox with names", frames: [4] },
      { track_id: "screen:3", sensitive: false, content: "café menu", frames: [4, 7] },
    ],
    missed: [], keyframes: [kfName(2), kfName(4), kfName(7)],
  },
  keyframe_urls: { 2: kfUrl("j_cafe", 2), 4: kfUrl("j_cafe", 4), 7: kfUrl("j_cafe", 7) },
  plan: {
    frames: {
      4: [
        { item_id: "i_5", shape: "box", box: [684, 384, 916, 536], mask: null, style: "solid", grid: null },
        { item_id: "i_6", shape: "box", box: [934, 394, 1166, 546], mask: null, style: "solid", grid: null },
      ],
      7: [{ item_id: "i_6", shape: "box", box: [934, 394, 1166, 546], mask: null, style: "solid", grid: null }],
    },
    crowd_fills: [],
  },
  scene: {
    status: "ok", model: "muse-spark-1.3", summary: "café vlog",
    participants: [{ description: "the host", evidence: "speaks to camera", speaker: "S1", introduced_in_turn: null, introduction_quote: null, is_creator: true }],
    children: [], others_present: "café customers at other tables",
    candidate_objects: [{ what: "two laptop screens", approx_time: "throughout" }],
  },
};
cafe.job.prepared_url = "https://example.invalid/j_cafe/prepared.mp4";

// ---------------------------------------------------------------- helpers
const withJob = (base, over) => ({ ...clone(base), ...clone(over) });
/** With no transcript turns there's nothing to point an introduction at (UI-SPEC §10.1). */
const noIntro = (scene) => ({ ...clone(scene), participants: scene.participants.map((p) => ({ ...p, introduced_in_turn: null, introduction_quote: null, speaker: null })) });
const statusOnly = (id, over) => ({
  job_id: id, mode: "live", deletes_at: DELETES_AT, has_render: false,
  job: { ...clone(hero.job), source_name: "street-interview.mp4", prepared_url: `https://example.invalid/${id}/prepared.mp4` },
  ...over,
});
const err = (status, code, extra = {}, headers) => ({ status, ...(headers ? { headers } : {}), body: { error: { code, message: `${code} (for logs only)`, ...extra } } });
const region = (item_id, box, style = "solid") => ({ item_id, shape: "box", box, mask: null, style, grid: style === "pixelate" ? [box[0], box[1], 11] : null });
const addRegion = (m, f, r) => { (m.plan.frames[f] ??= []).push(r); };
const addKeyframe = (m, f) => {
  if (!m.roles.keyframes.includes(kfName(f))) m.roles.keyframes.push(kfName(f));
  m.keyframe_urls[f] = kfUrl(m.job_id, f);
};
const roleTrack = (track_id, role, votes, extra = {}) => ({
  track_id, role, votes, escalated: false, suggested_role: null, escalation_evidence: null, escalation_frames: null,
  matches_participant: null, evidence: `seen at F ${String(extra.frames?.[0] ?? 5).padStart(6, "0")}`, frames: [5], ...extra,
});
const RESULT_URLS = (id) => ({
  video_url: `https://example.invalid/${id}/redacted.mp4`,
  captions_url: `https://example.invalid/${id}/captions.vtt`,
  receipt_html_url: `https://example.invalid/${id}/receipt.html`,
  receipt_json_url: `https://example.invalid/${id}/receipt.json`,
});
const auditClean = { frames_scanned: 12, egoblur: { model: "egoblur-gen2", faces: 0, plates: 0 }, leaks: [], redteam: [{ frame: 0, finding: "none" }], unresolved: 0, passes: 1, blocked_reason: null, sample_step: 30, spots: [] };

const mocks = {};

// ---------------------------------------------------------------- processing / failed job pages
mocks["job-processing-track"] = statusOnly("j_proc", { status: "processing", stage: "track", progress: 0.3, eta_s: 40 });
mocks["job-processing-miss-loop"] = statusOnly("j_proc", { status: "processing", stage: "miss_loop", progress: 0.7, eta_s: null });
mocks["job-failed-roles"] = statusOnly("j_failed", { status: "failed", stage: "roles", failure: { stage: "roles", reason: "internal" } });
mocks["job-retry-later"] = statusOnly("j_busy", { status: "retry_later", stage: "track", retry_at: "2026-10-27T10:05:00Z" });
mocks["job-failed-job-cap"] = statusOnly("j_failed", { status: "failed", stage: "track", failure: { stage: "track", reason: "job_cap" } });
mocks["job-created"] = statusOnly("j_created", { status: "created", stage: null });
mocks["job-failed-daily-cap-expiring"] = statusOnly("j_failed", { status: "failed", stage: "track", failure: { stage: "track", reason: "daily_cap" }, retry_at: "2026-11-11T00:00:00Z", code_valid_until: "2026-11-10T23:59:59Z" });
mocks["job-failed-code-not-active"] = statusOnly("j_failed", { status: "failed", stage: "track", failure: { stage: "track", reason: "code_not_active" }, has_render: false });
mocks["job-failed-daily-cap"] = statusOnly("j_failed", { status: "failed", stage: "track", failure: { stage: "track", reason: "daily_cap" }, retry_at: "2026-10-28T00:00:00Z", code_valid_until: null });
mocks["job-failed-code-cap"] = statusOnly("j_failed", { status: "failed", stage: "track", failure: { stage: "track", reason: "code_cap" } });
mocks["job-failed-upstream"] = statusOnly("j_failed", { status: "failed", stage: "track", failure: { stage: "track", reason: "upstream" } });
mocks["job-failed-deterministic"] = statusOnly("j_failed", { status: "failed", stage: "scene", failure: { stage: "scene", reason: "refusal" } });
mocks["job-failed-pilot-pool-cap"] = statusOnly("j_failed", { status: "failed", stage: "track", failure: { stage: "track", reason: "pilot_pool_cap" } });
mocks["job-failed-render"] = withJob(hero, { job_id: "j_hero1", status: "failed", stage: "render", has_render: false, failure: { stage: "render", reason: "internal" } });
mocks["job-failed-too-long"] = statusOnly("j_failed", { status: "failed", stage: "prepare", failure: { stage: "prepare", reason: "too_long", duration_s: 60.4 } });

// ---------------------------------------------------------------- review panel
mocks["job-review-hero1"] = clone(hero);
mocks["job-review-cafe"] = clone(cafe);
mocks["job-review-speech-fallback"] = clone(speech);
{
  const m = clone(hero);
  m.items = []; m.tracks = []; m.roles.tracks = []; m.roles.objects = []; m.roles.keyframes = [];
  m.keyframe_urls = {}; m.plan.frames = {};
  mocks["job-review-empty"] = m;
}
{
  const m = clone(hero);
  m.items = m.items.filter((i) => i.item_id !== "i_2");
  const i1 = m.items.find((i) => i.item_id === "i_1");
  Object.assign(i1, { decision: "needs_you", style: "pixelate", decided_by: "model", hold: "no_speech_link", reason: "all three checks said part of the story, but nothing links them to speech" });
  const i3 = m.items.find((i) => i.item_id === "i_3");
  Object.assign(i3, { decision: "needs_you", reason: "number plate, characters not legible" });
  m.roles.objects[0] = { track_id: "license plate:1", sensitive: false, content: "number plate, characters not legible", frames: [1] };
  m.roles.tracks[0].matches_participant = null;
  m.tracks = m.tracks.filter((t) => t.track_id !== "face:4");
  m.roles.tracks = m.roles.tracks.filter((t) => t.track_id !== "face:4");
  m.plan.frames = { 1: [region("i_3", [1042, 552, 1158, 598])], 3: [region("i_1", [390, 106, 480, 224], "pixelate")], 9: [region("i_4", [692, 140, 758, 225], "pixelate")] };
  mocks["job-review-needs-you-only"] = m;
}
{
  const m = clone(hero);
  m.items = m.items.filter((i) => i.item_id === "i_2");
  m.tracks = m.tracks.filter((t) => t.track_id === "face:4");
  m.roles.tracks = m.roles.tracks.filter((t) => t.track_id === "face:4");
  m.roles.objects = [];
  m.plan.frames = { 6: hero.plan.frames[6] };
  mocks["job-review-locked-child"] = m;
}
{
  // a kept guest (face:2, i_1) plus a NEW hidden face:9 re-acquired after the guest left the frame
  const m = clone(hero);
  m.items = m.items.filter((i) => i.item_id === "i_1");
  m.tracks = m.tracks.filter((t) => ["face:2", "person:1"].includes(t.track_id));
  for (const t of m.tracks) t.last = 9;
  m.tracks.push({ track_id: "face:9", concept: "face", first: 10, last: 11, reentry_of: "face:2", boxes: { 11: [600, 130, 668, 220] } });
  m.items.push({ item_id: "i_9", track_ids: ["face:9"], kind: "person", decision: "hide", reason: "appeared again after leaving; might be Face 2", evidence_frames: [11], style: "pixelate", decided_by: "policy", locked: false, removed_by_creator: false });
  m.roles.tracks = m.roles.tracks.filter((t) => t.track_id === "face:2");
  m.roles.tracks.push(roleTrack("face:9", "unsure", ["participant", "unsure", "participant"], { evidence: "walks back into frame at F 000011", frames: [11] }));
  m.roles.objects = [];
  m.roles.keyframes = [kfName(3), kfName(9)]; m.keyframe_urls = { 3: kfUrl("j_hero1", 3), 9: kfUrl("j_hero1", 9) };
  addKeyframe(m, 11);
  m.plan.frames = { 11: [region("i_9", [590, 120, 678, 232], "pixelate")] };
  mocks["job-review-reentry"] = m;
}
{
  // the H1B van case: a hidden bystander (face:5) re-acquired as face:8; no merge offered
  const m = clone(hero);
  m.items = m.items.filter((i) => i.item_id === "i_1");
  m.tracks = m.tracks.filter((t) => ["face:2", "person:1"].includes(t.track_id));
  m.tracks.push({ track_id: "face:5", concept: "face", first: 0, last: 5, reentry_of: null, boxes: { 1: [980, 180, 1030, 245] } });
  m.tracks.push({ track_id: "face:8", concept: "face", first: 8, last: 11, reentry_of: "face:5", boxes: { 9: [1000, 182, 1050, 247] } });
  m.items.push({ item_id: "i_5", track_ids: ["face:5"], kind: "person", decision: "hide", reason: "passer-by behind the van, never addressed", evidence_frames: [1], style: "pixelate", decided_by: "policy", locked: false, removed_by_creator: false });
  m.items.push({ item_id: "i_8", track_ids: ["face:8"], kind: "person", decision: "hide", reason: "appeared again after leaving", evidence_frames: [9], style: "pixelate", decided_by: "policy", locked: false, removed_by_creator: false });
  m.roles.tracks = m.roles.tracks.filter((t) => t.track_id === "face:2");
  m.roles.tracks.push(roleTrack("face:5", "bystander", ["bystander", "bystander", "bystander"], { evidence: "walks behind the van at F 000001", frames: [1] }));
  m.roles.tracks.push(roleTrack("face:8", "bystander", ["bystander", "bystander", "bystander"], { evidence: "walks past again at F 000009", frames: [9] }));
  m.roles.objects = [];
  m.plan.frames = { 1: [region("i_5", [972, 170, 1038, 255], "pixelate")], 9: [region("i_8", [992, 172, 1058, 257], "pixelate")] };
  mocks["job-review-reentry-bystander"] = m;
}
mocks["job-done-edited"] = withJob(hero, { status: "review", has_render: true, result: { video_url: RESULT_URLS("j_hero1").video_url } });
{
  const m = clone(hero);
  m.job_id = "j_many";
  m.items = []; m.tracks = []; m.roles.tracks = []; m.roles.objects = []; m.plan.frames = {};
  m.roles.keyframes = [kfName(5)]; m.keyframe_urls = { 5: kfUrl("j_many", 5) };
  for (let n = 1; n <= 200; n += 1) {
    const col = (n - 1) % 20, row = Math.floor((n - 1) / 20);
    const box = [10 + col * 63, 10 + row * 70, 60 + col * 63, 70 + row * 70];
    const decision = n % 3 === 0 ? "keep" : n % 3 === 1 ? "hide" : "needs_you";
    m.tracks.push({ track_id: `face:${n}`, concept: "face", first: 0, last: 11, reentry_of: null, boxes: { 5: box } });
    m.items.push({ item_id: `i_${n}`, track_ids: [`face:${n}`], kind: "person", decision, reason: decision === "keep" ? "speaks to camera" : decision === "hide" ? "passer-by, never addressed" : "checks disagreed", evidence_frames: [5], style: decision === "keep" ? null : "pixelate", decided_by: "policy", locked: false, removed_by_creator: false });
    m.roles.tracks.push(roleTrack(`face:${n}`, decision === "keep" ? "participant" : decision === "hide" ? "bystander" : "unsure", decision === "keep" ? ["participant", "participant", "participant"] : decision === "hide" ? ["bystander", "bystander", "bystander"] : ["participant", "bystander", "unsure"]));
    if (decision !== "keep") addRegion(m, 5, region(`i_${n}`, box, "pixelate"));
  }
  mocks["job-review-200-items"] = m;
}
mocks["job-review-no-audio"] = withJob(hero, { job: { ...hero.job, audio: false }, transcript: { status: "ok", source: null, source_kind: null, degraded: false, turns: [] }, scene: noIntro(hero.scene) });
{
  const m = clone(hero);
  m.transcript = { status: "ok", source: "muse-spark-1.2", source_kind: "fallback", degraded: true, turns: [] };
  m.scene = noIntro(m.scene);
  Object.assign(m.items[0], { decision: "needs_you", hold: "no_speech", reason: "speech check was limited, so not kept automatically", style: "pixelate", decided_by: "policy" });
  addRegion(m, 3, { item_id: "i_1", shape: "box", box: [390, 106, 480, 224], mask: null, style: "pixelate", grid: [390, 106, 15] });
  addRegion(m, 9, { item_id: "i_1", shape: "box", box: [400, 108, 490, 226], mask: null, style: "pixelate", grid: [390, 106, 15] });
  mocks["job-review-speech-limited"] = m;
}
mocks["job-review-keyframe-mismatch"] = withJob(hero, { keyframe_geometry: { ...hero.keyframe_geometry, image_height: 720 } });
mocks["job-replay"] = withJob(hero, { mode: "replay" });
mocks["job-rendering-audit"] = withJob(hero, { status: "rendering", stage: "audit", progress: 0.8 });
mocks["job-audit-rerun-patch"] = withJob(hero, { status: "rendering", stage: "render", stage_reason: "audit_patch", has_render: true, result: { video_url: RESULT_URLS("j_hero1").video_url } });
mocks["job-audit-rerun-receipt"] = withJob(hero, { status: "rendering", stage: "receipt", has_render: true, result: { video_url: RESULT_URLS("j_hero1").video_url } });
mocks["job-audit-rerun-done"] = withJob(hero, { status: "done", stage: "done", has_render: true, result: { video_url: RESULT_URLS("j_hero1").video_url }, audit: clone(auditClean) });

// ---------------------------------------------------------------- the Why-drawer rows no other mock drives
{
  const m = clone(hero);
  m.job_id = "j_why";
  addKeyframe(m, 5); addKeyframe(m, 7);
  const grid = (n) => [40 + ((n - 10) % 7) * 170, 300 + Math.floor((n - 10) / 7) * 130, 110 + ((n - 10) % 7) * 170, 390 + Math.floor((n - 10) / 7) * 130];
  const add = (n, item, rt, frameNo = 5) => {
    const id = `face:${n}`;
    const box = grid(n);
    m.tracks.push({ track_id: id, concept: "face", first: 2, last: 9, reentry_of: null, boxes: { [frameNo]: box } });
    m.items.push({ item_id: `i_${n}`, track_ids: [id], kind: "person", evidence_frames: [frameNo], style: "pixelate", decided_by: "policy", locked: false, removed_by_creator: false, ...item });
    if (rt) m.roles.tracks.push({ ...roleTrack(id, rt.role, rt.votes), evidence: `seen at F 00000${frameNo}`, frames: [frameNo], ...rt.extra });
    if (item.decision !== "keep") addRegion(m, frameNo, region(`i_${n}`, box, item.style ?? "pixelate"));
  };
  add(10, { decision: "needs_you", hold: "no_roles", reason: "checks couldn't run" }, { role: "unsure", votes: ["unsure", "unsure", "unsure"], extra: { failed_votes: 3 } });
  add(11, { decision: "needs_you", hold: "no_scene", reason: "scene check didn't run" }, { role: "participant", votes: ["participant", "participant", "participant"] });
  add(12, { decision: "needs_you", hold: "no_speech", reason: "speech check didn't work" }, { role: "participant", votes: ["participant", "participant", "participant"] });
  add(13, { decision: "needs_you", hold: "unmatched_child", reason: "a child may be in this video" }, { role: "participant", votes: ["participant", "participant", "participant"] });
  add(14, { decision: "needs_you", hold: "no_speech_link", reason: "not linked to anyone speaking" }, { role: "participant", votes: ["participant", "participant", "participant"] });
  add(17, { kind: "child", decision: "hide", locked: true, style: "solid", reason: "may be under 18" }, { role: "child", votes: ["bystander", "child", "unsure"], extra: { escalated: true, suggested_role: "child", escalation_evidence: "school uniform and height at F 000005", escalation_frames: [5] } });
  add(18, { decision: "needs_you", reason: "checks disagreed" }, { role: "unsure", votes: ["participant", "bystander", "unsure"], extra: { escalated: true, suggested_role: null, escalation_evidence: null, escalation_frames: null } });
  add(19, { decision: "needs_you", reason: "part of the story on one keyframe only" }, { role: "unsure", votes: ["participant", "participant", "participant"] });
  add(20, { decision: "hide", style: "person_solid", decided_by: "creator", removed_by_creator: true, reason: "removed at your request" }, { role: "participant", votes: ["participant", "participant", "participant"] });
  add(21, { decision: "keep", style: null, decided_by: "creator", reason: "passer-by in the background" }, { role: "bystander", votes: ["bystander", "bystander", "bystander"] });
  add(22, { decision: "hide", decided_by: "creator", reason: "the guest's friend" }, { role: "participant", votes: ["participant", "participant", "participant"] });
  add(23, { decision: "hide", reason: "passer-by, never addressed" }, { role: "bystander", votes: ["bystander", "bystander", "unsure"], extra: { failed_votes: 1 } });
  // origin: static (a miss-loop item SAM 3.1 couldn't track: a static track, no votes, no keyframe)
  m.tracks.push({ track_id: "envelope:1", concept: "envelope", first: 4, last: 7, reentry_of: null, boxes: { 5: [200, 600, 300, 680] } });
  m.items.push({ item_id: "i_15", track_ids: ["envelope:1"], kind: "other", origin: "static", decision: "hide", reason: "possible missed object at F5", evidence_frames: [], style: "solid", decided_by: "policy", locked: false, removed_by_creator: false });
  addRegion(m, 5, region("i_15", [190, 590, 310, 690]));
  // kind other from the miss loop, with an object ruling
  m.tracks.push({ track_id: "envelope:2", concept: "envelope", first: 6, last: 11, reentry_of: null, boxes: { 7: [520, 600, 640, 690] } });
  m.items.push({ item_id: "i_16", track_ids: ["envelope:2"], kind: "other", decision: "hide", reason: "addressed envelope on the table", evidence_frames: [7], style: "solid", decided_by: "policy", locked: false, removed_by_creator: false });
  m.roles.objects.push({ track_id: "envelope:2", sensitive: true, content: "envelope with a handwritten address", frames: [7] });
  m.roles.missed.push({ what: "addressed envelope", sam_phrase: "envelope", frame: 7, point: { x: 580, y: 645 }, track_ids: ["envelope:2"] });
  addRegion(m, 7, region("i_16", [510, 590, 650, 700]));
  mocks["job-review-why-rows"] = m;
}

// ---------------------------------------------------------------- audit and result
const resultBase = (id, audit, over = {}) => ({ job_id: id, mode: "live", status: "done", deletes_at: DELETES_AT, frames: 12, ...RESULT_URLS(id), audit, code_valid_until: null, ...over });
mocks["result-clean"] = resultBase("j_hero1", clone(auditClean));
mocks["result-clean-yunet"] = resultBase("j_hero1", { ...clone(auditClean), egoblur: { model: "yunet-face", faces: 0, plates: null } });
mocks["result-fixed"] = resultBase("j_hero1", {
  ...clone(auditClean), passes: 2,
  leaks: [
    { frame: 8, box: [700, 150, 750, 215], kind: "face", detector: "egoblur", patched_item: "i_4", unresolved: false },
    { frame: 9, box: [702, 151, 752, 216], kind: "face", detector: "egoblur", patched_item: "i_4", unresolved: false },
  ],
});
const spotS1 = { spot_id: "s1", first: 7, last: 7, boxes: { 7: [600, 200, 660, 250] }, covered_by: null };
const leakS1 = { frame: 7, box: [600, 200, 660, 250], kind: "face", detector: "egoblur", patched_item: null, unresolved: true };
const auditUnresolved = { ...clone(auditClean), passes: 2, leaks: [clone(leakS1)], unresolved: 1, blocked_reason: "unresolved_leaks", spots: [clone(spotS1)] };
mocks["result-unresolved"] = resultBase("j_hero1", clone(auditUnresolved));
{
  const m = withJob(hero, { status: "done", stage: "done", has_render: true, result: { video_url: RESULT_URLS("j_hero1").video_url }, audit: clone(auditUnresolved) });
  addKeyframe(m, 7);
  mocks["result-unresolved-review"] = m;
}
const needsYou = (audit, over = {}) => withJob(hero, { status: "needs_you", stage: "audit", has_render: true, result: { video_url: RESULT_URLS("j_hero1").video_url }, audit, ...over });
mocks["result-audit-failed"] = needsYou({ ...clone(auditClean), frames_scanned: 8, unresolved: 4, blocked_reason: "audit_failed" });
mocks["result-audit-failed-with-leak"] = needsYou({ ...clone(auditClean), frames_scanned: 8, unresolved: 5, blocked_reason: "audit_failed", leaks: [clone(leakS1)], spots: [clone(spotS1)] });
mocks["result-audit-over-budget"] = needsYou({ ...clone(auditClean), frames_scanned: 8, unresolved: 4, blocked_reason: "over_budget", audit_budget_cause: "daily_cap" }, { audit_budget_cause: "daily_cap", retry_at: "2026-10-28T00:00:00Z" });
mocks["result-audit-over-budget-code"] = needsYou({ ...clone(auditClean), frames_scanned: 8, unresolved: 4, blocked_reason: "over_budget", audit_budget_cause: "code_cap" }, { audit_budget_cause: "code_cap" });
mocks["result-audit-over-budget-jobcap"] = needsYou({ ...clone(auditClean), frames_scanned: 8, unresolved: 4, blocked_reason: "over_budget", audit_budget_cause: "job_cap" }, { audit_budget_cause: "job_cap" });

// ---------------------------------------------------------------- acks and errors (envelopes: {status, headers?, body})
mocks["render-ack"] = { status: 202, body: { job_id: "j_hero1", status: "rendering", stage: "render", mode: "live" } };
mocks["audit-ack"] = { status: 202, body: { job_id: "j_hero1", status: "rendering", stage: "audit", mode: "live" } };
mocks["delete-ok"] = { status: 204, body: null };
mocks["error-404-delete"] = err(404, "expired");
mocks["error-500-delete"] = err(500, "internal");
{
  const base = mocks["result-unresolved-review"];
  const plan = clone(base.plan);
  for (let f = 0; f <= 11; f += 1) addRegion({ plan }, f, region("p_1", [600, 200, 660, 250]));
  mocks["review-ack-cover-spot"] = {
    status: 200,
    body: {
      edit_id: "e_cover_s1", mode: "live", status: "review", has_render: true,
      items: [...clone(base.items), { item_id: "p_1", origin: "audit_patch", audit_label: "A1", track_ids: [], spot_id: "s1", kind: "person", decision: "hide", locked: true, reason: "Added by the audit: the final check found this after rendering and covered it.", evidence_frames: [7], box: [600, 200, 660, 250], first: 0, last: 11, style: "solid", decided_by: "policy", removed_by_creator: false }],
      plan,
      audit: { spots: [{ ...clone(spotS1), covered_by: "p_1" }] },
    },
  };
}
{
  const items = clone(hero.items);
  Object.assign(items[3], { decision: "hide", decided_by: "creator" });
  mocks["review-ack"] = { status: 200, body: { edit_id: "e_hide_i4", mode: "live", status: "review", has_render: false, items, plan: clone(hero.plan), audit: null } };
}
mocks["code-check-ok"] = { status: 200, body: { kind: "judge", valid_from: "2026-11-05T00:00:00Z", valid_until: "2026-11-10T23:59:59Z", open_weight: false } };
mocks["code-check-ok-open-weight"] = { status: 200, body: { kind: "owner", valid_from: null, valid_until: "2026-11-10T23:59:59Z", open_weight: true } };
mocks["error-401"] = err(401, "unauthorized");
mocks["error-401-job-render"] = err(401, "unauthorized");
// Expired codes end over a day before the fixtures' moment (2026-10-27T10:00Z), so the mock's
// whole-day time shift keeps them expired on any date.
mocks["error-401-job-expired-audit"] = err(401, "code_not_active", { valid_from: "2026-10-19T00:00:00Z", valid_until: "2026-10-25T23:59:59Z" });
mocks["error-401-not-yet-active"] = err(401, "code_not_active", { valid_from: "2026-11-05T00:00:00Z", valid_until: "2026-11-10T23:59:59Z" });
mocks["error-401-expired"] = err(401, "code_not_active", { valid_from: null, valid_until: "2026-10-25T23:59:59Z" });
mocks["error-401-revoked-start"] = err(401, "unauthorized");
mocks["error-429-cap"] = err(429, "daily_cap", { retry_at: "2026-10-28T00:00:00Z" });
mocks["error-429-rate"] = err(429, "rate_limited", {}, { "Retry-After": "30" });
mocks["error-404-expired"] = err(404, "expired");
mocks["error-404-not-found"] = err(404, "not_found");
mocks["error-429-render-code-cap"] = err(429, "code_cap");
mocks["error-429-render-daily-cap-expiring"] = err(429, "daily_cap", { retry_at: "2026-11-11T00:00:00Z" });
mocks["error-429-render-daily-cap"] = err(429, "daily_cap", { retry_at: "2026-10-28T00:00:00Z" });
mocks["error-429-code-cap"] = err(429, "code_cap");
mocks["error-429-pilot-pool-cap"] = err(429, "pilot_pool_cap");
mocks["error-413"] = err(413, "too_large", { size_bytes: 157286401 });
mocks["error-409-upload-incomplete"] = err(409, "upload_incomplete");
mocks["error-422-job-cap"] = err(422, "job_cap");
mocks["error-409-rendering"] = err(409, "rendering");
mocks["error-503-auditor-unavailable"] = err(503, "auditor_unavailable");
mocks["error-503-billing"] = err(503, "billing");
mocks["error-500"] = err(500, "internal");
mocks["create-job-ok"] = { status: 201, body: { job_id: "j_new", mode: "live", upload_url: "https://example.invalid/upload/j_new", upload_expires_at: "2026-10-27T10:15:00Z" } };

// ---------------------------------------------------------------- landing
const demo = (model, plates) => ({
  hero_id: "hero1", mode: "replay",
  job: { prepared_url: "https://example.invalid/hero1/prepared.mp4", fps: 30, frames: 12, times: clone(hero.job.times) },
  video_url: "https://example.invalid/hero1/redacted.mp4",
  poster_url: "https://example.invalid/hero1/poster.jpg",
  captions_url: "https://example.invalid/hero1/captions.vtt",
  audit: { ...clone(auditClean), egoblur: { model, faces: 0, plates } },
});
mocks["demo-hero"] = demo("egoblur-gen2", 0);
mocks["demo-hero-yunet"] = demo("yunet-face", null);
mocks["demo-hero-open-weight"] = { ...demo("egoblur-gen2", 0), audit: { ...demo("egoblur-gen2", 0).audit, open_weight: { model: "meta-models/muse-spark-open-1026", status: "ok", frames: 12, findings: 0 } } };
const row = (method, variant, v) => ({ method, variant, recall: v, exposure: v === null ? null : 1 - v, leak_bursts: v === null ? null : 0, over_blur: v === null ? null : 0.5 });
mocks["results-no-egoblur"] = {
  run_id: "fixture-run", rows: [row("Blur every face", "blur_all", 0.5), row("Detector only", "detector", 0.5), row("Muse Spark, no tracking", "muse_no_tracking", 0.5), row("Safe Cut", "full", 0.5)],
  n_clips: 2, n_public: 1, n_staged: 1, runs_per_clip_min: 1, runs_per_clip_max: 1, labellers: 1,
};
mocks["results-two-labellers"] = {
  ...clone(mocks["results-no-egoblur"]), rows: [...clone(mocks["results-no-egoblur"].rows), row("EgoBlur Gen 2", "egoblur", 0.5)],
  labellers: 2, percent_agreement: 0.9, n_entities: 10, a: 4, b: 1, c: 0, d: 5, kappa: 0.8,
};
mocks["results-kappa-undefined"] = { ...clone(mocks["results-two-labellers"]), a: 10, b: 0, c: 0, d: 0, percent_agreement: 1, kappa: null };

mocks["job-review-sample"] = sampleJob("/sample");

// ---------------------------------------------------------------- reducer fixture (UI-SPEC §10.5; not an API response)
mocks["reducer-state"] = {
  items: {
    i_1: { label: "Face 2", track_ids: ["face:2", "person:1"], decision: "keep", decided_by: "policy", locked: false, kind: "person", role: "participant", reentry_target: null, merged_into: null, removed: false },
    i_2: { label: "Face 4", track_ids: ["face:4"], decision: "hide", decided_by: "policy", locked: true, kind: "child", role: "child", reentry_target: null, merged_into: null, removed: false },
    i_3: { label: "Plate 1", track_ids: ["license plate:1"], decision: "hide", decided_by: "policy", locked: false, kind: "plate", role: null, reentry_target: null, merged_into: null, removed: false },
    i_4: { label: "Face 6", track_ids: ["face:6"], decision: "needs_you", decided_by: "model", locked: false, kind: "person", role: "unsure", reentry_target: null, merged_into: null, removed: false },
    i_5: { label: "Face 5", track_ids: ["face:5"], decision: "hide", decided_by: "policy", locked: false, kind: "person", role: "bystander", reentry_target: null, merged_into: null, removed: false },
    i_7: { label: "Face 7", track_ids: ["face:7"], decision: "keep", decided_by: "creator", locked: false, kind: "person", role: "bystander", reentry_target: null, merged_into: null, removed: false },
    i_8: { label: "Face 8", track_ids: ["face:8"], decision: "hide", decided_by: "policy", locked: false, kind: "person", role: "bystander", reentry_target: "i_5", merged_into: null, removed: false },
    i_9: { label: "Face 9", track_ids: ["face:9"], decision: "hide", decided_by: "policy", locked: false, kind: "person", role: "unsure", reentry_target: "i_1", merged_into: null, removed: false },
  },
  confirm: null, pending: {}, undo: [], status: "review", has_render: false, spots: {}, refusal: null, capNote: null,
};

// ---------------------------------------------------------------- write or check
const check = process.argv.includes("--check");
const COMPACT = new Set(["job-review-sample", "job-review-200-items"]);
mkdirSync(OUT, { recursive: true });
const want = new Set(Object.keys(mocks).map((k) => `${k}.json`));
let drift = 0;
for (const [name, value] of Object.entries(mocks)) {
  const path = join(OUT, `${name}.json`);
  // Large generated fixtures stay compact; hand-shaped ones are indented for review.
  const text = `${COMPACT.has(name) ? JSON.stringify(value) : JSON.stringify(value, null, 2)}\n`;
  if (check) {
    let current = "";
    try { current = readFileSync(path, "utf8"); } catch { current = ""; }
    if (current !== text) { drift += 1; console.error(`drift: ${name}.json`); }
  } else {
    writeFileSync(path, text);
  }
}
const names = Object.keys(mocks).sort();
const index = [
  "// Generated by scripts/gen-mocks.mjs. Lazy loaders, so mock data is only fetched in mock mode.",
  "export const MOCK_LOADERS = {",
  ...names.map((n) => `  "${n}": () => import("./${n}.json"),`),
  "} as const;",
  "",
  "export type MockName = keyof typeof MOCK_LOADERS;",
  "",
].join("\n");
const indexPath = join(OUT, "index.ts");
if (check) {
  let current = "";
  try { current = readFileSync(indexPath, "utf8"); } catch { current = ""; }
  if (current !== index) { drift += 1; console.error("drift: index.ts"); }
} else {
  writeFileSync(indexPath, index);
}
for (const f of readdirSync(OUT)) {
  if (f.endsWith(".json") && !want.has(f)) { drift += 1; console.error(`stale: ${f}`); }
}
if (check && drift > 0) process.exit(1);
console.log(`${check ? "checked" : "wrote"} ${want.size} mocks`);
