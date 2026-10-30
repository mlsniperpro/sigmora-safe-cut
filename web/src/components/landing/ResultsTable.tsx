import type { ResultsTable as Results } from "@/lib/contracts";
import { SITE } from "@/lib/site";

const ORDER = ["blur_all", "egoblur", "detector", "muse_no_tracking", "full", "suggestions", "no_audit"] as const;
const NAMES: Record<(typeof ORDER)[number], string> = {
  blur_all: "Blur every face",
  egoblur: "EgoBlur Gen 2",
  detector: "Detector only",
  muse_no_tracking: "Muse Spark, no tracking",
  full: "Safe Cut",
  suggestions: "Safe Cut, suggestions accepted",
  no_audit: "Safe Cut, no audit",
};

const COLUMNS = [
  { key: "recall", label: "Recall", help: "Of the people and things that should be hidden, the share that were hidden on at least 95% of the frames they're visible in." },
  { key: "exposure", label: "Exposure", help: "Counting each should-be-hidden person or thing on each frame it's visible in, the share where less than 90% of it was covered." },
  { key: "leak_bursts", label: "Leak bursts", help: "The number of times something that should be hidden was exposed for 3 or more frames in a row." },
  { key: "over_blur", label: "Over-blur", help: "Of the people and things that should stay clear, the share that were hidden on more than 10% of their frames." },
] as const;

/**
 * Percentages to one decimal, always rounded in the unflattering direction
 * (AGENTS.md rule 9: never round up): down for higher-is-better numbers,
 * up for lower-is-better ones.
 */
function pct(v: number | null, better: "higher" | "lower"): string {
  if (v === null) return "—";
  const tenths = better === "higher" ? Math.floor(v * 1000 + 1e-9) : Math.ceil(v * 1000 - 1e-9);
  return `${(tenths / 10).toFixed(1)}%`;
}

/**
 * §1.3: the second opinion never runs on the test split, which the footnote says once it runs on
 * the hero. The spec's "where `audit.open_weight.status` is `ok`" is the condition, not copy.
 */
const OPEN_WEIGHT_NOTE = "Muse Spark Open's second opinion ran only on consented hero and dev footage; the test-split numbers were measured without it.";

function footnote(r: Results): string {
  const head = `${r.n_clips} test clips (${r.n_public} filmed in public, ${r.n_staged} staged with consenting actors), labelled by`;
  const runCount = r.runs_per_clip_min === r.runs_per_clip_max ? `${r.runs_per_clip_min} run${r.runs_per_clip_min === 1 ? "" : "s"}` : `${r.runs_per_clip_min}–${r.runs_per_clip_max} runs`;
  const runs = `${runCount} per clip. Run ${r.run_id}.`;
  if (r.labellers === 1) return `${head} one person. Agreement between two labellers wasn't measured. ${runs}`;
  const agreed = `They agreed on ${pct(r.percent_agreement ?? null, "higher")} of ${r.n_entities ?? 0} decisions (both said hide: ${r.a ?? 0} · only the first said hide: ${r.b ?? 0} · only the second said hide: ${r.c ?? 0} · both said keep: ${r.d ?? 0})`;
  if (r.kappa === null || r.kappa === undefined || !Number.isFinite(r.kappa)) {
    return `${head} two people. ${agreed}. κ can't be computed: both labellers made the same call on every item. ${runs}`;
  }
  // κ is higher-is-better, so it's rounded down too (AGENTS rule 9): 0.816 shows as 0.81.
  const kappa = (Math.floor(r.kappa * 100 + 1e-9) / 100).toFixed(2);
  return `${head} two people. ${agreed}; κ = ${kappa}. ${runs}`;
}

export function ResultsTable({ results, heroOpenWeight = false }: { results: Results | null; heroOpenWeight?: boolean }) {
  if (!results) {
    return <p className="text-muted">Numbers appear here after our frozen test runs. We publish them whether they&apos;re good or not.</p>;
  }
  const rows = ORDER.map((v) => ({ variant: v, row: results.rows.find((r) => r.variant === v) })).filter((x) => x.row || x.variant === "egoblur");
  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-border bg-surface" role="region" aria-label="Results table" tabIndex={0}>
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-surface-2">
            <tr>
              <th scope="col" className="px-3 py-2 font-semibold">
                Method
              </th>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col" className="px-3 py-2 font-semibold">
                  <abbr title={c.help} className="no-underline">
                    {c.label}
                  </abbr>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ variant, row }) =>
              row ? (
                <tr key={variant} className={`border-t border-border ${variant === "full" ? "font-semibold" : ""}`}>
                  <th scope="row" className="px-3 py-2 font-medium">
                    {NAMES[variant]}
                  </th>
                  <td className="px-3 py-2">{pct(row.recall, "higher")}</td>
                  <td className="px-3 py-2">{pct(row.exposure, "lower")}</td>
                  <td className="px-3 py-2">{row.leak_bursts ?? "—"}</td>
                  <td className="px-3 py-2">{pct(row.over_blur, "lower")}</td>
                </tr>
              ) : (
                <tr key={variant} className="border-t border-border text-muted">
                  <th scope="row" colSpan={5} className="px-3 py-2 font-normal">
                    EgoBlur Gen 2: not run (EgoBlur weights unavailable)
                  </th>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-sm text-muted">
        {footnote(results)}
        {heroOpenWeight && ` ${OPEN_WEIGHT_NOTE}`}{" "}
        <a href={results.run_url ?? SITE.evalUrl} className="underline underline-offset-2" rel="noopener noreferrer" target="_blank">
          How we measured ↗
        </a>
      </p>
      <dl className="mt-3 grid gap-1 text-xs text-muted sm:grid-cols-2">
        {COLUMNS.map((c) => (
          <div key={c.key}>
            <dt className="inline font-semibold">{c.label}: </dt>
            <dd className="inline">{c.help}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
