/**
 * Model-based check: random edit sequences go through the reducer and the mock
 * server (WP3 semantics), with acks, rejects and undos interleaved. Once nothing
 * is pending, the client's view must equal the server's. `FUZZ_RUNS` scales it
 * for long soak runs (the default keeps the normal suite fast).
 */
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import heroMock from "../../../mocks/job-review-hero1.json";
import reentryMock from "../../../mocks/job-review-reentry.json";
import unresolvedMock from "../../../mocks/result-unresolved-review.json";
import { SafeCutClient } from "../api";
import { jobResponseSchema, type ReviewEdit } from "../contracts";
import { MockBackend } from "@/test/mock-backend";
import { buildItems, initialState, step, type Action, type ReviewState } from "./reducer";

const RUNS = Number(process.env.FUZZ_RUNS ?? 60);
const FIXTURES = { "job-review-hero1": heroMock, "job-review-reentry": reentryMock, "result-unresolved-review": unresolvedMock } as const;

type Op = { kind: "keep" | "hide" | "remove" | "confirm" | "cancel" | "merge" | "cover" | "undo" | "flush" | "fail"; a: number; b: number };

const opArb = fc.record({
  kind: fc.constantFrom<Op["kind"]>("keep", "hide", "remove", "confirm", "cancel", "merge", "cover", "undo", "flush", "flush", "fail"),
  a: fc.nat(10),
  b: fc.nat(10),
});

function view(state: ReviewState) {
  const out: Record<string, unknown> = {};
  for (const [id, i] of Object.entries(state.items)) {
    if (i.merged_into) continue;
    out[id] = { decision: i.decision, decided_by: i.decided_by, removed: i.removed, tracks: [...i.track_ids].sort() };
  }
  return out;
}

describe("client and server agree after any edit sequence", () => {
  for (const [name, raw] of Object.entries(FIXTURES)) {
    it(`${name} (${RUNS} runs)`, async () => {
      await fc.assert(
        fc.asyncProperty(fc.array(opArb, { maxLength: 30 }), async (ops) => {
          const backend = new MockBackend({ latencyMs: 0 });
          const client = new SafeCutClient({ transport: backend, sleep: () => Promise.resolve() });
          const job = jobResponseSchema.parse(raw);
          const context = { tracks: job.tracks, roles: job.roles };
          let s = initialState({ items: job.items, plan: job.plan!, status: job.status, has_render: job.has_render, spots: job.audit?.spots ?? [] }, context);
          const queue: ReviewEdit[] = [];
          let n = 0;
          const run = (a: Action) => {
            const r = step(s, a);
            s = r.state;
            if (r.send) queue.push(r.send);
          };
          /** Delivers queued edits in order; `fail` rejects the first one instead. */
          const deliver = async (fail: boolean) => {
            const edit = queue.shift();
            if (!edit) return;
            if (fail) {
              run({ type: "SERVER_REJECT", edit_id: edit.edit_id });
              return;
            }
            const ack = await client.review(name, edit).catch(() => null);
            if (!ack) {
              run({ type: "SERVER_REJECT", edit_id: edit.edit_id });
              return;
            }
            run({ type: "SERVER_ACK", edit_id: edit.edit_id, server: { items: ack.items, plan: ack.plan, status: ack.status, has_render: ack.has_render, spots: ack.audit?.spots ?? [] } });
          };
          for (const op of ops) {
            const ids = Object.keys(s.items).filter((id) => !id.startsWith("pending:"));
            const id = ids[op.a % Math.max(1, ids.length)] ?? "";
            const other = ids[op.b % Math.max(1, ids.length)] ?? "";
            const edit_id = `x${(n += 1)}`;
            switch (op.kind) {
              case "keep": run({ type: "KEEP", id, edit_id }); break;
              case "hide": run({ type: "HIDE", id, edit_id }); break;
              case "remove": run({ type: "REMOVE_PERSON", id, edit_id }); break;
              case "confirm": run({ type: "CONFIRM_KEEP", edit_id }); break;
              case "cancel": run({ type: "CANCEL_CONFIRM" }); break;
              case "merge": run({ type: "MERGE", src: id, dst: other, edit_id }); break;
              case "cover": {
                const spot = Object.keys(s.spots)[0];
                if (spot) run({ type: "COVER_SPOT", spot_id: spot, edit_id });
                break;
              }
              case "undo": {
                const top = s.undo.at(-1);
                if (top) run({ type: "UNDO", target: top.edit.edit_id, edit_id });
                break;
              }
              case "flush": await deliver(false); break;
              case "fail": await deliver(true); break;
            }
          }
          while (queue.length) await deliver(false);
          expect(s.pending).toEqual({});
          const server = jobResponseSchema.parse((await client.getJob(name)) as unknown);
          expect(view(s)).toEqual(view({ ...s, items: buildItems(server.items, context) }));
          expect(Object.fromEntries(Object.entries(s.spots).map(([k, v]) => [k, v.covered_by]))).toEqual(Object.fromEntries((server.audit?.spots ?? []).map((sp) => [sp.spot_id, sp.covered_by])));
          // A locked child is never kept.
          for (const item of server.items) if (item.kind === "child") expect(item.decision).toBe("hide");
        }),
        { numRuns: RUNS },
      );
    }, 600_000);
  }
});
