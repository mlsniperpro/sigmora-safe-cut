import Image from "next/image";
import Link from "next/link";
import { HeroAndSteps } from "@/components/landing/HeroAndSteps";
import { ResultsSection } from "@/components/landing/ResultsSection";
import { RESULTS } from "@/data/results";
import { SITE } from "@/lib/site";

export default function Home() {
  return (
    <>
      <HeroAndSteps />

      <section aria-labelledby="compare-title" className="mx-auto max-w-6xl px-4 py-12">
        <h2 id="compare-title" className="text-2xl font-semibold tracking-tight">
          Blur every face vs Safe Cut
        </h2>
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <figure>
            <Image
              src="/sample/blur-every-face.jpg"
              width={1280}
              height={720}
              className="rounded-xl border border-border"
              alt="Blur every face: every face is pixelated, the guest's included, while the number plate and the chat on the shop screen stay readable."
            />
            <figcaption className="mt-2 text-sm text-muted">Blur every face: your guest is hidden, the number plate isn&apos;t. Illustration with drawn shapes, not a measured result.</figcaption>
          </figure>
          <figure>
            <Image
              src="/sample/safe-cut.jpg"
              width={1280}
              height={720}
              className="rounded-xl border border-border"
              alt="Safe Cut: the guest stays clear; the passer-by, the child, the number plate, the shop screen and the man watching are covered."
            />
            <figcaption className="mt-2 text-sm text-muted">Safe Cut: your guest stays clear, the plate and the passer-by are hidden. Illustration with drawn shapes, not a measured result.</figcaption>
          </figure>
        </div>
      </section>

      <section id="results" aria-labelledby="results-title" className="mx-auto max-w-6xl px-4 py-12">
        <h2 id="results-title" className="text-2xl font-semibold tracking-tight">
          Results on our labelled test set
        </h2>
        <div className="mt-6">
          <ResultsSection results={RESULTS} />
        </div>
      </section>

      <section aria-label="Next steps" className="mx-auto max-w-6xl px-4">
        <p className="flex flex-wrap gap-x-6 gap-y-2 rounded-xl border border-border bg-surface p-5 font-medium">
          <Link href="/try" className="underline underline-offset-4">
            Try it
          </Link>
          <a href={SITE.repoUrl} className="underline underline-offset-4" rel="noopener noreferrer" target="_blank">
            Source on GitHub
          </a>
          <a href={SITE.sigmoraUrl} className="underline underline-offset-4" rel="noopener noreferrer" target="_blank">
            Use it inside Sigmora
          </a>
        </p>
      </section>
    </>
  );
}
