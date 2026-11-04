/**
 * Runtime schemas for every API response the web app reads (ARCHITECTURE §3,
 * UI-SPEC §8 and §10.1). Every external input is parsed here before any
 * component sees it; a response that doesn't match is a typed error, never a
 * half-rendered page.
 */
import { z } from "zod";
import { localApiOrigin } from "./api-base";

const frame = z.number().int().nonnegative();
export const boxSchema = z.tuple([z.number(), z.number(), z.number(), z.number()]);
export type Box = z.infer<typeof boxSchema>;
const isoTime = z.iso.datetime({ offset: true });
/**
 * A URL the API hands the browser (signed media, keyframes, receipts). Only
 * https, or a same-origin path, so a compromised API can't inject `javascript:`.
 */
const LOCAL_API = localApiOrigin();
/** Plain http is accepted only from a loopback API's own origin (a local run or the e2e check). */
const fromLocalApi = (u: string) => LOCAL_API !== null && u.startsWith(`${LOCAL_API}/`);
export const mediaUrl = z
  .string()
  // Browsers read a backslash as "/" and strip tabs and newlines, so "/" + backslash (or a tab) +
  // "/evil.com" would be protocol-relative: no backslashes, whitespace or control characters anywhere.
  .refine((u) => !/[\\\s\u0000-\u001f\u007f]/.test(u) && (u.startsWith("https://") || /^\/(?!\/)/.test(u) || fromLocalApi(u)), { message: "must be an https URL or a same-origin path" });
/** The presigned upload URL; the mock backend's `mock://` scheme is accepted only in its unit tests. */
const uploadUrl = z.string().refine((u) => u.startsWith("https://") || u.startsWith("mock://") || fromLocalApi(u), { message: "must be an https URL" });
/** A keyframe's frame number from its key: `som/000024.jpg` → "24"; a bare frame number ("24") is kept as is. */
export function keyframeKey(key: string): string {
  const m = /(\d+)(?:\.\w+)?$/.exec(key);
  return m ? String(Number(m[1])) : key;
}

export const roleSchema = z.enum(["participant", "bystander", "child", "unsure"]);
export type Role = z.infer<typeof roleSchema>;

export const kindSchema = z.enum(["person", "child", "plate", "screen", "document", "other"]);
export type Kind = z.infer<typeof kindSchema>;

export const decisionSchema = z.enum(["hide", "keep", "needs_you"]);
export type Decision = z.infer<typeof decisionSchema>;

export const styleSchema = z.enum(["solid", "pixelate", "person_solid"]);
export type Style = z.infer<typeof styleSchema>;

export const decidedBySchema = z.enum(["policy", "model", "creator"]);
export type DecidedBy = z.infer<typeof decidedBySchema>;

export const holdSchema = z.enum(["no_roles", "no_scene", "no_speech", "unmatched_child", "no_speech_link"]);
export type Hold = z.infer<typeof holdSchema>;

export const itemSchema = z.object({
  item_id: z.string().min(1),
  track_ids: z.array(z.string()),
  kind: kindSchema,
  decision: decisionSchema,
  reason: z.string(),
  evidence_frames: z.array(frame),
  style: styleSchema.nullable(),
  decided_by: decidedBySchema,
  locked: z.boolean(),
  removed_by_creator: z.boolean().default(false),
  hold: holdSchema.nullable().optional(),
  origin: z.enum(["sam", "static", "audit_patch"]).nullable().optional(),
  audit_label: z.string().nullable().optional(),
  spot_id: z.string().nullable().optional(),
  box: boxSchema.nullable().optional(),
  first: frame.nullable().optional(),
  last: frame.nullable().optional(),
});
export type Item = z.infer<typeof itemSchema>;

export const trackSchema = z.object({
  track_id: z.string().min(1),
  concept: z.string(),
  first: frame,
  last: frame,
  // WP0's Track defaults it to None, so its JSON may leave the key out (wp0-foundation's j_example fixture).
  reentry_of: z.string().nullable().default(null),
  boxes: z.record(z.string(), boxSchema),
  child_phrase: z.boolean().optional(),
});
export type Track = z.infer<typeof trackSchema>;

export const roleTrackSchema = z.object({
  track_id: z.string(),
  role: roleSchema,
  votes: z.array(roleSchema),
  failed_votes: z.number().int().min(0).max(3).default(0),
  escalated: z.boolean(),
  suggested_role: roleSchema.nullable().optional(),
  escalation_evidence: z.string().nullable().optional(),
  escalation_frames: z.array(frame).nullable().optional(),
  matches_participant: z.number().int().nonnegative().nullable().optional(),
  evidence: z.string(),
  frames: z.array(frame),
});
export type RoleTrack = z.infer<typeof roleTrackSchema>;

export const roleObjectSchema = z.object({
  track_id: z.string(),
  sensitive: z.boolean(),
  content: z.string(),
  frames: z.array(frame),
});
export type RoleObject = z.infer<typeof roleObjectSchema>;

export const missedSchema = z.object({
  what: z.string(),
  sam_phrase: z.string().optional(),
  frame: frame.optional(),
  // WP0's Missed: `point` is required but nullable (a box-only miss), `box` optional; one of them is set.
  point: z.object({ x: z.number(), y: z.number() }).nullable().optional(),
  box: boxSchema.nullable().optional(),
  track_ids: z.array(z.string()).optional(),
});

export const rolesSchema = z.object({
  status: z.string(),
  model: z.string().nullable().optional(),
  tracks: z.array(roleTrackSchema),
  objects: z.array(roleObjectSchema),
  missed: z.array(missedSchema).default([]),
  keyframes: z.array(z.string()).default([]),
});
export type Roles = z.infer<typeof rolesSchema>;

/** COCO-style run-length mask (WP0 `Rle`): `size` is [height, width]; the overlay fills it (`rle.ts`). */
export const rleSchema = z.object({ size: z.tuple([z.number().int(), z.number().int()]), counts: z.string() });
export type Rle = z.infer<typeof rleSchema>;

export const regionSchema = z.object({
  item_id: z.string(),
  shape: z.enum(["box", "mask"]),
  box: boxSchema,
  mask: rleSchema.nullable().optional(),
  style: styleSchema,
  grid: z.tuple([z.number(), z.number(), z.number().positive()]).nullable().optional(),
  /** Kept participants' padded faces this region leaves untouched (DESIGN §2.6). */
  keep_clear: z.array(boxSchema).optional(),
});
export type Region = z.infer<typeof regionSchema>;

export const planSchema = z.object({
  frames: z.record(z.string(), z.array(regionSchema)),
  crowd_fills: z.array(z.object({ frames: z.array(frame), box: boxSchema })).default([]),
});
export type Plan = z.infer<typeof planSchema>;

export const transcriptSchema = z.object({
  status: z.string(),
  source: z.string().nullable().optional(),
  source_kind: z.enum(["primary", "fallback"]).nullable().optional(),
  degraded: z.boolean().default(false),
  turns: z.array(
    z.object({ speaker: z.string(), start: z.number(), end: z.number(), text: z.string() }),
  ),
});
export type Transcript = z.infer<typeof transcriptSchema>;

export const sceneSchema = z.object({
  status: z.string(),
  model: z.string().nullable().optional(),
  summary: z.string().optional(),
  participants: z
    .array(
      z.object({
        description: z.string(),
        evidence: z.string().optional(),
        speaker: z.string().nullable().optional(),
        introduced_in_turn: z.number().int().nullable().optional(),
        introduction_quote: z.string().nullable().optional(),
        is_creator: z.boolean().optional(),
      }),
    )
    .default([]),
  children: z.array(z.object({ description: z.string() })).default([]),
  others_present: z.string().optional(),
  candidate_objects: z.array(z.object({ what: z.string(), approx_time: z.string() })).default([]),
});
export type Scene = z.infer<typeof sceneSchema>;

export const keyframeGeometrySchema = z.object({
  bar_h: z.number().int().nonnegative(),
  frame_width: z.number().int().positive(),
  frame_height: z.number().int().positive(),
  image_width: z.number().int().positive(),
  image_height: z.number().int().positive(),
});
export type KeyframeGeometry = z.infer<typeof keyframeGeometrySchema>;

export const blockedReasonSchema = z.enum(["unresolved_leaks", "audit_failed", "over_budget"]);
export const budgetCauseSchema = z.enum(["daily_cap", "job_cap", "code_cap", "pilot_pool_cap"]);
export type BudgetCause = z.infer<typeof budgetCauseSchema>;

export const spotSchema = z.object({
  spot_id: z.string(),
  first: frame,
  last: frame,
  boxes: z.record(z.string(), boxSchema),
  // WP0 defaults it to None, so its JSON may leave the key out.
  covered_by: z.string().nullable().default(null),
});
export type Spot = z.infer<typeof spotSchema>;

export const auditSchema = z.object({
  frames_scanned: z.number().int().nonnegative(),
  egoblur: z.object({
    model: z.string(),
    faces: z.number().int().nonnegative().nullable(),
    plates: z.number().int().nonnegative().nullable(),
  }),
  leaks: z
    .array(
      z.object({
        frame,
        box: boxSchema,
        kind: z.string(),
        detector: z.string().optional(),
        patched_item: z.string().nullable(),
        unresolved: z.boolean().default(false),
      }),
    )
    .default([]),
  unresolved: z.number().int().nonnegative(),
  passes: z.number().int().nonnegative().default(1),
  blocked_reason: blockedReasonSchema.nullable().default(null),
  sample_step: z.number().int().positive().optional(),
  spots: z.array(spotSchema).default([]),
  // WP0's OpenWeightSummary; its default is `{"model": null, "status": "off", "frames": 0, "findings": 0}`
  // (ARCHITECTURE §3.8). The second opinion never blocks a job, so one that doesn't parse reads as absent.
  open_weight: z
    .object({
      model: z.string().nullable().default(null),
      status: z.enum(["ok", "failed", "off"]).default("off"),
      frames: z.number().int().nonnegative().default(0),
      findings: z.number().int().nonnegative().default(0),
    })
    .nullable()
    .optional()
    .catch(null),
  audit_budget_cause: budgetCauseSchema.nullable().optional(),
});
export type Audit = z.infer<typeof auditSchema>;

export const jobStatusSchema = z.enum([
  "created",
  "processing",
  "retry_later",
  "review",
  "rendering",
  "done",
  "needs_you",
  "failed",
]);
export type JobStatus = z.infer<typeof jobStatusSchema>;

export const stageSchema = z.enum([
  "queued",
  "prepare",
  "track",
  "transcribe",
  "scene",
  "roles",
  "miss_loop",
  "decide",
  "guard",
  "review",
  "render",
  "audit",
  "receipt",
  "done",
]);
export type Stage = z.infer<typeof stageSchema>;

export const failureReasonSchema = z.enum([
  "internal",
  "upstream",
  "job_cap",
  "daily_cap",
  "code_cap",
  "pilot_pool_cap",
  "config",
  "bad_request",
  "refusal",
  "incomplete",
  "code_not_active",
  "too_long",
  "too_large",
  "bad_media",
]);
export type FailureReason = z.infer<typeof failureReasonSchema>;

export const modeSchema = z.enum(["live", "replay"]);
export type Mode = z.infer<typeof modeSchema>;

export const jobMetaSchema = z.object({
  fps: z.number(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  frames: z.number().int(),
  audio: z.boolean().default(true),
  times: z.array(z.number().nullable()),
  created_at: isoTime.optional(),
  prepared_url: mediaUrl.optional(),
  source_name: z.string().optional(),
});
export type JobMeta = z.infer<typeof jobMetaSchema>;

export const jobResponseSchema = z.object({
  job_id: z.string().min(1),
  mode: modeSchema,
  /** A replay of synthetic recordings (the drawn test clip), labelled as such (AGENTS rule 9). Missing on a replay
   * means synthetic (`useReportMode`): a replay is never bannered as a real run unless the API says so. */
  synthetic: z.boolean().optional(),
  status: jobStatusSchema,
  stage: stageSchema.nullable().optional(),
  stage_reason: z.literal("audit_patch").nullable().optional(),
  progress: z.number().min(0).max(1).optional(),
  eta_s: z.number().nonnegative().nullable().optional(),
  deletes_at: isoTime,
  retry_at: isoTime.nullable().optional(),
  code_valid_until: isoTime.nullable().optional(),
  has_render: z.boolean().default(false),
  failure: z
    .object({
      stage: stageSchema.nullable().optional(),
      reason: failureReasonSchema.nullable().optional(),
      duration_s: z.number().positive().optional(),
      size_bytes: z.number().int().positive().optional(),
    })
    .nullable()
    .optional(),
  job: jobMetaSchema.optional(),
  items: z.array(itemSchema).default([]),
  tracks: z.array(trackSchema).default([]),
  roles: rolesSchema.optional(),
  plan: planSchema.optional(),
  transcript: transcriptSchema.optional(),
  scene: sceneSchema.optional(),
  keyframe_geometry: keyframeGeometrySchema.optional(),
  // The API keys each keyframe by its file name (`som/000024.jpg`); every screen looks one up by frame number
  // ("24"). Normalize here, once: a key that is already a frame number passes through unchanged.
  keyframe_urls: z
    .record(z.string(), mediaUrl)
    .default({})
    .transform((urls) => Object.fromEntries(Object.entries(urls).map(([key, url]) => [keyframeKey(key), url]))),
  audit: auditSchema.nullable().optional(),
  audit_budget_cause: budgetCauseSchema.nullable().optional(),
  result: z.object({ video_url: mediaUrl }).nullable().optional(),
  models: z.record(z.string(), z.string()).optional(),
});
export type JobResponse = z.infer<typeof jobResponseSchema>;

export const resultResponseSchema = z.object({
  // §8 doesn't give /result its job ID either: the page has it from the route.
  job_id: z.string().optional(),
  mode: modeSchema,
  synthetic: z.boolean().optional(),
  // §8/§5.6 don't give /result these; the page reads the job's own status and frames first.
  status: jobStatusSchema.optional(),
  deletes_at: isoTime,
  frames: z.number().int().nonnegative().optional(),
  video_url: mediaUrl,
  captions_url: mediaUrl.nullable().optional(),
  receipt_html_url: mediaUrl,
  receipt_json_url: mediaUrl,
  audit: auditSchema,
  code_valid_until: isoTime.nullable().optional(),
});
export type ResultResponse = z.infer<typeof resultResponseSchema>;

// Request 19: the result shape plus `job` and `audit`; nothing here reads a hero ID.
export const demoResponseSchema = z.object({
  mode: z.literal("replay"),
  synthetic: z.boolean().optional(),
  job: z.object({
    prepared_url: mediaUrl,
    fps: z.number(),
    frames: z.number().int().positive(),
    times: z.array(z.number().nullable()),
  }),
  video_url: mediaUrl,
  poster_url: mediaUrl.nullable().optional(),
  captions_url: mediaUrl.nullable().optional(),
  audit: auditSchema,
});
export type DemoResponse = z.infer<typeof demoResponseSchema>;

export const codeCheckSchema = z.object({
  kind: z.enum(["judge", "public", "pilot", "recording", "owner"]),
  valid_from: isoTime.nullable(),
  valid_until: isoTime.nullable(),
  open_weight: z.boolean().default(false),
});
export type CodeCheck = z.infer<typeof codeCheckSchema>;

export const createJobResponseSchema = z.object({
  job_id: z.string().min(1),
  mode: modeSchema.default("live"),
  upload_url: uploadUrl,
  upload_expires_at: isoTime.optional(),
});
export type CreateJobResponse = z.infer<typeof createJobResponseSchema>;

// The 202 ack is `status` and `stage` (render-ack.json, audit-ack.json, ACTION_ACK).
export const actionAckSchema = z.object({
  job_id: z.string().optional(),
  status: jobStatusSchema,
  stage: stageSchema.nullable().optional(),
  mode: modeSchema.default("live"),
});
export type ActionAck = z.infer<typeof actionAckSchema>;

// §8 Edits: items, plan, status, has_render and audit.spots. The page knows the edit_id it sent.
export const reviewAckSchema = z.object({
  edit_id: z.string().optional(),
  mode: modeSchema.default("live"),
  status: jobStatusSchema,
  has_render: z.boolean(),
  items: z.array(itemSchema),
  plan: planSchema,
  audit: z.object({ spots: z.array(spotSchema).default([]) }).nullable().optional(),
});
export type ReviewAck = z.infer<typeof reviewAckSchema>;

export const errorBodySchema = z.object({
  error: z
    .object({
      code: z.string(),
      message: z.string().optional(),
      retry_at: isoTime.nullable().optional(),
      valid_from: isoTime.nullable().optional(),
      valid_until: isoTime.nullable().optional(),
      size_bytes: z.number().int().optional(),
    })
    .loose(),
});
export type ErrorBody = z.infer<typeof errorBodySchema>;

/** One review edit (UI-SPEC §8 request 5, §10.5). */
export type ReviewEdit =
  | { type: "keep"; edit_id: string; item_id: string }
  | { type: "hide"; edit_id: string; item_id: string }
  | { type: "merge"; edit_id: string; item_id: string; into: string }
  | { type: "remove_person"; edit_id: string; item_id: string }
  | { type: "cover_spot"; edit_id: string; spot_id: string }
  | { type: "undo"; edit_id: string; reverts: string };

export const resultsTableSchema = z.object({
  run_id: z.string(),
  run_url: z.string().optional(),
  rows: z.array(
    z.object({
      method: z.string(),
      variant: z.enum(["blur_all", "egoblur", "detector", "muse_no_tracking", "full", "suggestions", "no_audit"]),
      recall: z.number().min(0).max(1).nullable(),
      exposure: z.number().min(0).max(1).nullable(),
      leak_bursts: z.number().int().nonnegative().nullable(),
      over_blur: z.number().min(0).max(1).nullable(),
    }),
  ),
  n_clips: z.number().int().nonnegative(),
  n_public: z.number().int().nonnegative(),
  n_staged: z.number().int().nonnegative(),
  runs_per_clip_min: z.number().int().positive(),
  runs_per_clip_max: z.number().int().positive(),
  labellers: z.union([z.literal(1), z.literal(2)]),
  percent_agreement: z.number().min(0).max(1).nullable().optional(),
  n_entities: z.number().int().nonnegative().nullable().optional(),
  a: z.number().int().nonnegative().nullable().optional(),
  b: z.number().int().nonnegative().nullable().optional(),
  c: z.number().int().nonnegative().nullable().optional(),
  d: z.number().int().nonnegative().nullable().optional(),
  kappa: z.number().nullable().optional(),
});
export type ResultsTable = z.infer<typeof resultsTableSchema>;
