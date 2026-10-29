"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import { auditStepBody } from "@/lib/copy";
import type { DemoResponse } from "@/lib/contracts";
import { HeroPlayer } from "./HeroPlayer";

const STEPS = [
  {
    n: 1,
    title: "Muse Spark decides who",
    body: "Muse Spark watches the clip, reads who said what (from Muse Voice Transcribe), and rules on each person and object SAM 3.1 has labelled: part of the story, or not.",
  },
  {
    n: 2,
    title: "SAM 3.1 keeps them hidden",
    body: "SAM 3.1 keeps each hidden person and item covered through the clip. Anyone the tracker loses and finds again starts hidden. Anything uncertain stays hidden.",
  },
] as const;

/** The closed loop between the models, for the "How it works" figure. */
const LOOP = [
  "SAM 3.1 finds and numbers every face, person, plate, screen and document",
  "Muse Spark rules on each number three times, with the transcript as evidence",
  "Muse Spark names anything SAM missed; SAM 3.1 tracks it as a new number",
  "The render covers everything not kept clear",
  "The audit checks the render; any leak is covered and checked again",
] as const;

export function HeroAndSteps() {
  const [audit, setAudit] = useState<DemoResponse["audit"] | null>(null);
  const onAuditor = useCallback((a: DemoResponse["audit"]) => setAudit(a), []);
  return (
    <>
      <section className="mx-auto grid max-w-6xl gap-8 px-4 pt-10 pb-12 lg:grid-cols-[1fr_1.1fr] lg:items-center lg:pt-16">
        <div className="order-2 lg:order-1">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
            Publish real-world footage without exposing the people who never agreed to be in it.
          </h1>
          <p className="mt-4 text-lg text-muted">
            Safe Cut works out who&apos;s part of your story and hides everyone and everything else: passers-by, children, number plates, private screens. You approve every decision.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-4">
            <Link href="/try" className="flex min-h-11 items-center rounded-lg bg-accent px-5 font-semibold forced-colors:border-2 forced-colors:border-[ButtonText] text-accent-text hover:bg-accent-hover">
              Try it with an access code
            </Link>
            <a href="#results" className="flex min-h-11 items-center underline underline-offset-4">
              See the results ↓
            </a>
          </div>
        </div>
        <div className="order-1 lg:order-2">
          <HeroPlayer onAuditor={onAuditor} />
        </div>
      </section>

      <section id="how-it-works" aria-labelledby="how-title" className="border-y border-border bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-12">
          <h2 id="how-title" className="text-2xl font-semibold tracking-tight">
            How it works
          </h2>
          <ol className="mt-6 grid gap-4 md:grid-cols-3">
            {[...STEPS, { n: 3, title: "An audit checks the render", body: auditStepBody(audit?.egoblur.model ?? null, audit?.open_weight) }].map((s) => (
              <li key={s.n} className="rounded-xl border border-border bg-bg p-5">
                <p className="flex items-baseline gap-3">
                  <span aria-hidden="true" className="text-2xl font-semibold text-accent">
                    {s.n}
                  </span>
                  <span className="font-semibold">{s.title}</span>
                </p>
                <p className="mt-2 text-sm text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
          <figure className="mt-8 rounded-xl border border-border bg-bg p-5">
            <figcaption className="font-semibold">The loop, on every clip</figcaption>
            <ol className="mt-3 grid gap-2 text-sm sm:grid-cols-5">
              {LOOP.map((step, i) => (
                <li key={step} className="flex gap-2 rounded-lg bg-surface p-3">
                  <span aria-hidden="true" className="font-semibold text-accent">
                    {i + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
            <p className="mt-3 text-sm text-muted">Every decision keeps its evidence: the numbered keyframe, the three rulings and what was said. You see all of it under “Why?” before anything is published.</p>
          </figure>
        </div>
      </section>
    </>
  );
}
