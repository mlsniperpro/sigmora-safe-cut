/**
 * In-browser stand-in for WP5's API, built on `web/mocks/` (WP6 step 2).
 *
 * - `/jobs/<fixture-name>` serves that fixture (frozen until you act on it), so
 *   every UI-SPEC §10.1 state has a URL.
 * - Jobs created through `/try` run a simulated pipeline on a timer.
 * - Review edits follow the WP3 `apply_review` contract (UI-SPEC §8 request 5),
 *   including idempotent `edit_id`s and `undo` with `reverts`.
 * - `inject()` makes the next matching request answer with an error fixture,
 *   for failure-path tests.
 */
import { MOCK_LOADERS, type MockName } from "../../mocks";
import type { RawResponse, RequestInit, Transport } from "./api";
import { jobResponseSchema, type Box, type Item, type JobResponse, type Plan, type Region, type ReviewEdit, type Spot, type Stage } from "./contracts";

interface Envelope {
  status: number;
  headers?: Record<string, string>;
  body: unknown;
}

const PIPELINE: readonly Stage[] = ["queued", "prepare", "track", "transcribe", "scene", "roles", "miss_loop", "decide", "guard"];
const RENDER: readonly Stage[] = ["render", "audit", "receipt"];

/** Codes with scripted answers, so every `/try` refusal can be exercised in mock mode. */
export const MOCK_CODES: Readonly<Record<string, { check?: MockName; create?: MockName; start?: MockName }>> = {
  wrong: { check: "error-401" },
  "open-weight": { check: "code-check-ok-open-weight" },
  "not-yet": { check: "error-401-not-yet-active" },
  "rate-limited": { check: "error-429-rate" },
  expired: { create: "error-401-expired" },
  "no-budget": { create: "error-429-code-cap" },
  "pilot-done": { start: "error-429-pilot-pool-cap" },
  "too-big": { start: "error-422-job-cap" },
  revoked: { start: "error-401-revoked-start" },
  "no-auditor": { start: "error-503-auditor-unavailable" },
  "no-credits": { start: "error-503-billing" },
  "upload-lost": { start: "error-409-upload-incomplete" },
};

interface History {
  items: Record<string, Item | null>;
  regions: Record<string, Array<[string, Region]>>;
  spots: Record<string, string | null>;
  status: JobResponse["status"];
}

interface MockJob {
  data: JobResponse;
  code: string | null;
  /** When set, the job advances through `stages` one step per `stepMs`. */
  timeline: { startedAt: number; stages: readonly Stage[]; then: "review" | "done" } | null;
  edits: Map<string, History>;
  deleted: boolean;
}

const headers = (h: Record<string, string> = {}) => ({ get: (name: string) => h[name] ?? h[name.toLowerCase()] ?? null });
const respond = (status: number, body: unknown, h?: Record<string, string>): RawResponse => ({ status, headers: headers(h), body });
const notFound = () => respond(404, { error: { code: "not_found" } });

function padBox([x1, y1, x2, y2]: Box, frac: number, width: number, height: number): Box {
  const dx = (x2 - x1) * frac;
  const dy = (y2 - y1) * frac;
  return [Math.max(0, Math.round(x1 - dx)), Math.max(0, Math.round(y1 - dy)), Math.min(width, Math.round(x2 + dx)), Math.min(height, Math.round(y2 + dy))];
}

export interface MockBackendOptions {
  /** Delay before each answer, so the UI shows its pending states. */
  latencyMs?: number;
  /** Time per simulated pipeline stage. */
  stepMs?: number;
  now?: () => number;
  /** Media the simulated jobs point at (served from `public/`). */
  sample?: { job: MockName; mediaBase: string } | null;
  /**
   * Where jobs made through `/try` are kept, so a reload or the copied review link still finds
   * them, like the real API's 24 hours. Fixture jobs are never stored: they reset on reload.
   */
  storage?: Pick<Storage, "getItem" | "setItem"> | null;
}

const STORAGE_KEY = "safecut.mock-jobs";
const DAY_MS = 24 * 60 * 60 * 1000;
const isCreated = (id: string) => /^j_mock\d+$/.test(id);

interface StoredJob {
  data: JobResponse;
  code: string | null;
  timeline: MockJob["timeline"];
  edits: Array<[string, History]>;
  deleted: boolean;
}

export class MockBackend implements Transport {
  private readonly jobs = new Map<string, MockJob>();
  private readonly codes = new Map<string, string>();
  private readonly injected: Array<{ match: RegExp; fixture: MockName; times: number }> = [];
  private readonly latencyMs: number;
  private readonly stepMs: number;
  private readonly now: () => number;
  private readonly sample: { job: MockName; mediaBase: string } | null;
  private readonly storage: Pick<Storage, "getItem" | "setItem"> | null;
  private nextId = 1;
  /** Every request seen, for tests. */
  readonly log: Array<{ method: string; path: string; body: unknown }> = [];

  constructor(options: MockBackendOptions = {}) {
    this.latencyMs = options.latencyMs ?? 250;
    this.stepMs = options.stepMs ?? 1_200;
    this.now = options.now ?? (() => Date.now());
    this.sample = options.sample ?? null;
    this.storage = options.storage ?? null;
    for (const [id, stored] of Object.entries(this.readStored())) {
      this.jobs.set(id, { ...stored, edits: new Map(stored.edits) });
      this.codes.set(id, stored.code ?? "");
      this.nextId = Math.max(this.nextId, Number(id.slice("j_mock".length)) + 1);
    }
  }

  /** Stored `/try` jobs that haven't passed their `deletes_at`; unreadable storage counts as empty. */
  private readStored(): Record<string, StoredJob> {
    try {
      const raw = this.storage?.getItem(STORAGE_KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (typeof parsed !== "object" || parsed === null) return {};
      return Object.fromEntries(
        Object.entries(parsed as Record<string, StoredJob>).filter(
          ([id, j]) => isCreated(id) && typeof j?.data?.deletes_at === "string" && Date.parse(j.data.deletes_at) > this.now() && Array.isArray(j.edits),
        ),
      );
    } catch {
      return {};
    }
  }

  private save(): void {
    if (!this.storage) return;
    const stored: Record<string, StoredJob> = {};
    for (const [id, j] of this.jobs) {
      // Only a scripted code is kept: a real code typed into the preview never lands in storage.
      const code = j.code !== null && j.code in MOCK_CODES ? j.code : null;
      if (isCreated(id)) stored[id] = { data: j.data, code, timeline: j.timeline, edits: [...j.edits], deleted: j.deleted };
    }
    try {
      this.storage.setItem(STORAGE_KEY, JSON.stringify(stored));
    } catch {
      // Storage full or blocked (a private window): the job still works in this tab.
    }
  }

  /** The real API deletes everything 24 hours after the job was made (§5.4). */
  private deletesAt(): string {
    return new Date(this.now() + DAY_MS).toISOString();
  }

  /** The next `times` requests whose `METHOD path` matches answer with this fixture. */
  inject(match: RegExp, fixture: MockName, times = 1): void {
    this.injected.push({ match, fixture, times });
  }

  async request(init: RequestInit): Promise<RawResponse> {
    this.log.push({ method: init.method, path: init.path, body: init.body });
    if (this.latencyMs > 0) await this.delay(this.latencyMs, init.signal);
    const key = `${init.method} ${init.path}`;
    const hit = this.injected.find((i) => i.match.test(key));
    if (hit) {
      hit.times -= 1;
      if (hit.times <= 0) this.injected.splice(this.injected.indexOf(hit), 1);
      return this.envelope(hit.fixture);
    }
    const response = await this.route(init);
    this.save();
    return response;
  }

  upload(url: string, _file: Blob, _contentType: string, onProgress: (fraction: number) => void, signal: AbortSignal): Promise<void> {
    const jobId = url.split("/").pop() ?? "";
    return new Promise((resolve, reject) => {
      let step = 0;
      const timer = setInterval(() => {
        step += 1;
        onProgress(Math.min(1, step / 5));
        if (step >= 5) {
          clearInterval(timer);
          const job = this.jobs.get(jobId);
          if (job) job.data = { ...job.data, status: "created" };
          this.save();
          resolve();
        }
      }, Math.max(1, this.latencyMs));
      signal.addEventListener("abort", () => {
        clearInterval(timer);
        reject(new Error("upload cancelled"));
      }, { once: true });
    });
  }

  // ------------------------------------------------------------------ routing

  private async route({ method, path, body }: RequestInit): Promise<RawResponse> {
    const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
    if (parts[0] !== "v1") return notFound();
    if (method === "POST" && parts[1] === "codes" && parts[2] === "check") return this.checkCode(body);
    if (parts[1] === "demo" && method === "GET") return this.demo();
    if (parts[1] !== "jobs") return notFound();
    if (method === "POST" && parts.length === 2) return this.createJob(body);
    const id = parts[2];
    if (!id) return notFound();
    const action = parts[3];
    if (method === "DELETE" && !action) return this.deleteJob(id);
    if (method === "GET" && !action) return this.getJob(id);
    if (method === "GET" && action === "result") return this.getResult(id);
    if (method === "POST" && action === "start") return this.start(id);
    if (method === "POST" && action === "render") return this.renderOrAudit(id, "render");
    if (method === "POST" && action === "audit") return this.renderOrAudit(id, "audit");
    if (method === "POST" && action === "review") return this.review(id, body as ReviewEdit);
    return notFound();
  }

  private async envelope(name: MockName): Promise<RawResponse> {
    const data = (await this.fixture(name)) as Envelope;
    return respond(data.status, structuredClone(data.body), data.headers);
  }

  private async fixture(name: MockName): Promise<unknown> {
    const mod = (await MOCK_LOADERS[name]()) as { default: unknown };
    return structuredClone(mod.default);
  }

  private checkCode(body: unknown): Promise<RawResponse> | RawResponse {
    const code = typeof body === "object" && body && "code" in body ? String((body as { code: unknown }).code) : "";
    const scripted = MOCK_CODES[code]?.check;
    if (scripted) return this.envelope(scripted);
    return this.envelope("code-check-ok");
  }

  private async createJob(body: unknown): Promise<RawResponse> {
    const input = (body ?? {}) as { code?: string; size_bytes?: number };
    const scripted = MOCK_CODES[input.code ?? ""]?.create;
    if (scripted) return this.envelope(scripted);
    if ((input.size_bytes ?? 0) > 157_286_400) return this.envelope("error-413");
    const id = `j_mock${this.nextId++}`;
    const base = jobResponseSchema.parse(await this.fixture(this.sample?.job ?? "job-review-hero1"));
    const data: JobResponse = {
      ...base,
      job_id: id,
      mode: "live",
      deletes_at: this.deletesAt(),
      status: "created",
      stage: null,
      has_render: false,
      audit: null,
      result: null,
    };
    this.jobs.set(id, { data, code: input.code ?? null, timeline: null, edits: new Map(), deleted: false });
    this.codes.set(id, input.code ?? "");
    return respond(201, { job_id: id, mode: "live", upload_url: `mock://upload/${id}` });
  }

  private async start(id: string): Promise<RawResponse> {
    const scripted = MOCK_CODES[this.codes.get(id) ?? ""]?.start;
    if (scripted) return this.envelope(scripted);
    const job = await this.load(id);
    if (!job) return notFound();
    job.timeline = { startedAt: this.now(), stages: PIPELINE, then: "review" };
    job.data = { ...job.data, status: "processing", stage: "queued", failure: null };
    return respond(202, { job_id: id, status: "processing", stage: "queued", mode: job.data.mode });
  }

  private async getJob(id: string): Promise<RawResponse> {
    if (id.startsWith("error-")) return this.envelope(id as MockName);
    const job = await this.load(id);
    if (!job) return notFound();
    this.advance(job);
    return respond(200, structuredClone(job.data));
  }

  private async getResult(id: string): Promise<RawResponse> {
    if (id.startsWith("result-") && id in MOCK_LOADERS) {
      const data = (await this.fixture(id as MockName)) as Record<string, unknown>;
      if ("receipt_html_url" in data) {
        // With sample media (the app's mock mode), its URLs and frame count replace the fixture's,
        // so the player, the audit summary and the sample receipt all describe the same clip.
        const sample = this.sample ? jobResponseSchema.parse(await this.fixture(this.sample.job)).job : null;
        const audit = data.audit as Record<string, unknown> | undefined;
        return respond(200, {
          ...data,
          ...(this.sample && this.mediaUrls(id)),
          // Frames the fixture's audit left unchecked stay unchecked.
          ...(sample && { frames: sample.frames, audit: { ...audit, frames_scanned: sample.frames - (Number(data.frames) - Number(audit?.frames_scanned)) } }),
          deletes_at: this.deletesAt(),
        });
      }
    }
    const job = await this.load(id);
    if (!job) return notFound();
    this.advance(job);
    if (job.data.status !== "done") return respond(409, { error: { code: "not_ready" } });
    const urls = this.mediaUrls(id);
    return respond(200, {
      job_id: id,
      mode: job.data.mode,
      status: "done",
      deletes_at: job.data.deletes_at,
      frames: job.data.job?.frames ?? 0,
      ...urls,
      audit: job.data.audit ?? (await this.cleanAudit(job)),
      code_valid_until: job.data.code_valid_until ?? null,
    });
  }

  private async demo(): Promise<RawResponse> {
    const data = (await this.fixture("demo-hero")) as Record<string, unknown> & { job: Record<string, unknown> };
    if (this.sample) {
      const base = this.sample.mediaBase;
      data.video_url = `${base}/redacted.mp4`;
      data.poster_url = `${base}/poster.jpg`;
      data.captions_url = `${base}/captions.vtt`;
      const sample = (await this.fixture(this.sample.job)) as JobResponse;
      if (sample.job) data.job = { prepared_url: `${base}/prepared.mp4`, fps: sample.job.fps, frames: sample.job.frames, times: sample.job.times };
    }
    return respond(200, data);
  }

  private deleteJob(id: string): RawResponse {
    const job = this.jobs.get(id);
    if (job) job.deleted = true;
    else this.jobs.set(id, { data: {} as JobResponse, code: null, timeline: null, edits: new Map(), deleted: true });
    return respond(204, null);
  }

  private async renderOrAudit(id: string, what: "render" | "audit"): Promise<RawResponse> {
    const job = await this.load(id);
    if (!job) return notFound();
    this.advance(job);
    if (job.data.status === "rendering") return respond(409, { error: { code: "rendering" } });
    const stages = what === "render" ? RENDER : (["audit", "receipt"] as const);
    job.timeline = { startedAt: this.now(), stages, then: "done" };
    job.data = { ...job.data, status: "rendering", stage: stages[0] ?? "render", stage_reason: null };
    return respond(202, { job_id: id, status: "rendering", stage: job.data.stage, mode: job.data.mode });
  }

  // ------------------------------------------------------------------ state

  private async load(id: string): Promise<MockJob | null> {
    const existing = this.jobs.get(id);
    if (existing) return existing.deleted ? null : existing;
    if (!(id in MOCK_LOADERS)) return null;
    const data = (await this.fixture(id as MockName)) as JobResponse & { status?: unknown };
    if (typeof data !== "object" || data === null || typeof data.status !== "string" || !("deletes_at" in data)) return null;
    if ("receipt_html_url" in data) return this.adopt(id, await this.doneJobFor(id, data as unknown as { audit: unknown }));
    return this.adopt(id, jobResponseSchema.parse(data));
  }

  private adopt(id: string, data: JobResponse): MockJob {
    const job: MockJob = { data: { ...this.withSampleMedia(data), deletes_at: this.deletesAt() }, code: null, timeline: null, edits: new Map(), deleted: false };
    this.jobs.set(id, job);
    return job;
  }

  /** A `result-*` fixture is a result response; the job behind it is the hero, done, with that audit. */
  private async doneJobFor(id: string, result: { audit: unknown }): Promise<JobResponse> {
    const hero = jobResponseSchema.parse(await this.fixture("job-review-hero1"));
    const audit = jobResponseSchema.shape.audit.parse(result.audit);
    return { ...hero, job_id: id, status: "done", stage: "done", has_render: true, audit, result: { video_url: this.mediaUrls(id).video_url } };
  }

  private mediaUrls(id: string) {
    const base = this.sample?.mediaBase ?? `https://example.invalid/${id}`;
    return {
      video_url: `${base}/redacted.mp4`,
      captions_url: `${base}/captions.vtt`,
      receipt_html_url: `${base}/receipt.html`,
      receipt_json_url: `${base}/receipt.json`,
    };
  }

  private withSampleMedia(data: JobResponse): JobResponse {
    if (!this.sample || !data.job?.prepared_url?.startsWith("https://example.invalid/")) return data;
    const base = this.sample.mediaBase;
    return { ...data, job: { ...data.job, prepared_url: `${base}/prepared.mp4` } };
  }

  private advance(job: MockJob): void {
    const t = job.timeline;
    if (!t) return;
    const step = Math.floor((this.now() - t.startedAt) / this.stepMs);
    const stage = t.stages[step];
    if (stage) {
      const status = t.then === "review" ? "processing" : "rendering";
      job.data = { ...job.data, status, stage, progress: step / t.stages.length, eta_s: Math.round(((t.stages.length - step) * this.stepMs) / 1000) };
      return;
    }
    job.timeline = null;
    if (t.then === "review") {
      job.data = { ...job.data, status: "review", stage: "review", progress: 1, eta_s: null };
    } else {
      const urls = this.mediaUrls(job.data.job_id);
      job.data = { ...job.data, status: "done", stage: "done", progress: 1, eta_s: null, has_render: true, result: { video_url: urls.video_url } };
      void this.cleanAudit(job).then((audit) => {
        job.data = { ...job.data, audit };
        this.save();
      });
    }
  }

  private async cleanAudit(job: MockJob) {
    const fixed = (await this.fixture("result-fixed")) as { audit: NonNullable<JobResponse["audit"]> };
    return { ...fixed.audit, frames_scanned: job.data.job?.frames ?? fixed.audit.frames_scanned };
  }

  // ------------------------------------------------------------------ review edits (WP3 apply_review, mocked)

  private async review(id: string, edit: ReviewEdit): Promise<RawResponse> {
    const job = await this.load(id);
    if (!job) return notFound();
    this.advance(job);
    const d = job.data;
    if (d.status === "needs_you") return respond(409, { error: { code: "read_only" } });
    if (d.status === "rendering") return respond(409, { error: { code: "rendering" } });
    if (!job.edits.has(edit.edit_id)) {
      const history = this.apply(job, edit);
      if (!history) return respond(422, { error: { code: "invalid_edit" } });
      job.edits.set(edit.edit_id, history);
      if (job.data.status === "done") job.data = { ...job.data, status: "review" };
    }
    const data = job.data;
    return respond(200, {
      edit_id: edit.edit_id,
      mode: data.mode,
      status: data.status,
      has_render: data.has_render,
      items: structuredClone(data.items),
      plan: structuredClone(data.plan ?? { frames: {}, crowd_fills: [] }),
      audit: data.audit ? { spots: structuredClone(data.audit.spots) } : null,
    });
  }

  private apply(job: MockJob, edit: ReviewEdit): History | null {
    const d = job.data;
    const plan: Plan = structuredClone(d.plan ?? { frames: {}, crowd_fills: [] });
    const items = d.items.map((i) => ({ ...i }));
    const spots = (d.audit?.spots ?? []).map((s) => ({ ...s }));
    const byId = new Map(items.map((i) => [i.item_id, i]));
    const history: History = { items: {}, regions: {}, spots: {}, status: d.status };
    const remember = (itemId: string) => {
      if (itemId in history.items) return;
      const it = byId.get(itemId);
      history.items[itemId] = it ? { ...it } : null;
      history.regions[itemId] = this.regionsOf(plan, itemId);
    };

    switch (edit.type) {
      case "keep":
      case "hide":
      case "remove_person": {
        const it = byId.get(edit.item_id);
        if (!it || (it.locked && edit.type === "keep")) return null;
        remember(it.item_id);
        if (edit.type === "keep") {
          Object.assign(it, { decision: "keep", decided_by: "creator", style: null, removed_by_creator: false });
          this.dropRegions(plan, it.item_id);
        } else {
          const removing = edit.type === "remove_person";
          const style = removing ? "person_solid" : it.style ?? (it.kind === "person" ? "pixelate" : "solid");
          Object.assign(it, { decision: "hide", decided_by: "creator", style, removed_by_creator: removing ? true : it.removed_by_creator });
          if (removing || this.regionsOf(plan, it.item_id).length === 0) {
            this.dropRegions(plan, it.item_id);
            this.addTrackRegions(plan, it, d, removing);
          }
        }
        break;
      }
      case "merge": {
        const src = byId.get(edit.item_id);
        const dst = byId.get(edit.into);
        if (!src || !dst || src === dst || src.locked || dst.decision !== "keep") return null;
        remember(src.item_id);
        remember(dst.item_id);
        dst.track_ids = [...dst.track_ids, ...src.track_ids];
        dst.decided_by = "creator";
        this.dropRegions(plan, src.item_id);
        items.splice(items.indexOf(src), 1);
        break;
      }
      case "cover_spot": {
        const spot = spots.find((s) => s.spot_id === edit.spot_id);
        if (!spot || spot.covered_by !== null) return null;
        const next = 1 + items.reduce((n, i) => Math.max(n, Number(i.audit_label?.slice(1) ?? 0)), 0);
        const itemId = `p_${next}`;
        remember(itemId);
        history.spots[spot.spot_id] = null;
        const box = this.unionBox(spot);
        const frames = d.job?.frames ?? spot.last + 1;
        const half = Math.ceil((d.audit?.sample_step ?? 1) / 2);
        const first = Math.max(0, spot.first - half - 8);
        const last = Math.min(frames - 1, spot.last + half + 8);
        const kind = d.audit?.leaks.find((l) => l.frame === spot.first)?.kind;
        items.push({
          item_id: itemId, origin: "audit_patch", audit_label: `A${next}`, track_ids: [], spot_id: spot.spot_id,
          kind: kind === "face" || kind === "person" ? "person" : kind === "plate" ? "plate" : "other",
          decision: "hide", locked: true, reason: "Added by the audit: the final check found this after rendering and covered it.",
          evidence_frames: [spot.first], box, first, last, style: "solid", decided_by: "policy", removed_by_creator: false,
        });
        for (let f = first; f <= last; f += 1) (plan.frames[String(f)] ??= []).push({ item_id: itemId, shape: "box", box, mask: null, style: "solid", grid: null });
        spot.covered_by = itemId;
        break;
      }
      case "undo": {
        const target = job.edits.get(edit.reverts);
        if (!target) return null;
        for (const itemId of Object.keys(target.items)) remember(itemId);
        for (const [itemId, before] of Object.entries(target.items)) {
          const index = items.findIndex((i) => i.item_id === itemId);
          if (before === null) {
            if (index >= 0) items.splice(index, 1);
          } else if (index >= 0) {
            items[index] = { ...before };
          } else {
            items.push({ ...before });
          }
          this.dropRegions(plan, itemId);
          for (const [f, r] of target.regions[itemId] ?? []) (plan.frames[f] ??= []).push(r);
        }
        for (const [spotId, coveredBy] of Object.entries(target.spots)) {
          const spot = spots.find((s) => s.spot_id === spotId);
          if (spot) {
            history.spots[spotId] = spot.covered_by;
            spot.covered_by = coveredBy;
          }
        }
        job.edits.delete(edit.reverts);
        break;
      }
    }
    job.data = { ...d, items, plan, audit: d.audit ? { ...d.audit, spots } : d.audit };
    return history;
  }

  private regionsOf(plan: Plan, itemId: string): Array<[string, Region]> {
    const out: Array<[string, Region]> = [];
    for (const [f, regions] of Object.entries(plan.frames)) for (const r of regions) if (r.item_id === itemId) out.push([f, { ...r }]);
    return out;
  }

  private dropRegions(plan: Plan, itemId: string): void {
    for (const [f, regions] of Object.entries(plan.frames)) {
      const kept = regions.filter((r) => r.item_id !== itemId);
      if (kept.length) plan.frames[f] = kept;
      else delete plan.frames[f];
    }
  }

  private addTrackRegions(plan: Plan, item: Item, d: JobResponse, wholePerson: boolean): void {
    const w = d.job?.width ?? 1280;
    const h = d.job?.height ?? 720;
    const ids = wholePerson ? item.track_ids.filter((t) => t.startsWith("person:")) : [];
    const sources = ids.length ? ids : item.track_ids;
    for (const track of d.tracks.filter((t) => sources.includes(t.track_id))) {
      for (const [f, box] of Object.entries(track.boxes)) {
        const style = item.style ?? "solid";
        const padded = padBox(box, track.concept === "face" ? 0.15 : 0.08, w, h);
        (plan.frames[f] ??= []).push({ item_id: item.item_id, shape: "box", box: padded, mask: null, style, grid: style === "pixelate" ? [padded[0], padded[1], 11] : null });
      }
    }
  }

  private unionBox(spot: Spot): Box {
    const boxes = Object.values(spot.boxes);
    return [
      Math.min(...boxes.map((b) => b[0])),
      Math.min(...boxes.map((b) => b[1])),
      Math.max(...boxes.map((b) => b[2])),
      Math.max(...boxes.map((b) => b[3])),
    ];
  }

  private delay(ms: number, signal?: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      const t = setTimeout(resolve, ms);
      signal?.addEventListener("abort", () => {
        clearTimeout(t);
        reject(new Error("aborted"));
      }, { once: true });
    });
  }
}
