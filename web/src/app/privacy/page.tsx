import type { Metadata } from "next";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Privacy · Safe Cut" };

const SECTIONS: ReadonlyArray<[string, string]> = [
  ["What we collect", "The clip you upload, the access code you enter, and your IP address (only to limit how often a code or address can call the service). No account, no cookies beyond what the page needs to work."],
  ["Who processes it", "Meta's Model API (to decide what to hide), Modal (processing), Cloudflare R2 (upload storage) and Vercel (this website). Baseten, which runs the open-weight model Muse Spark Open, sees sampled frames only for the owner's own consented demo clips, never for clips uploaded with a pilot, judge or public code."],
  ["How long", "Your clip, the result and the receipt are deleted from Safe Cut's servers after 24 hours, or sooner if you press \"Delete everything now\". While the final check runs, a copy of the redacted result (never the original, nor its file name) sits with the GPU that checks it and is removed when the check ends, or within the hour if the check is cut short. Meta keeps content as needed to run its service and to review abuse, with no fixed period for ordinary content; requests flagged for policy violations may be kept up to 2 years. Meta doesn't train its models on Standard-mode content, and zero data retention isn't enabled. Safe Cut sends store: false where Meta's API accepts it and deletes its uploads."],
  ["What we never do", "No ads, no sale of data, no training on your clip, and nothing published unless you press Publish."],
];

export default function Privacy() {
  return (
    <article className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Privacy</h1>
      {SECTIONS.map(([heading, text]) => (
        <section key={heading} className="mt-8">
          <h2 className="text-xl font-semibold">{heading}</h2>
          <p className="mt-2 text-muted">{text}</p>
        </section>
      ))}
      <section className="mt-8">
        <h2 className="text-xl font-semibold">Contact</h2>
        <p className="mt-2 text-muted">
          {SITE.privacyContact ? (
            <a href={`mailto:${SITE.privacyContact}`} className="inline-flex min-h-11 items-center underline underline-offset-2 lg:min-h-8">
              {SITE.privacyContact}
            </a>
          ) : (
            <a href={`${SITE.repoUrl}/issues`} className="inline-flex min-h-11 items-center underline underline-offset-2 lg:min-h-8" rel="noopener noreferrer" target="_blank">
              Open an issue on GitHub
            </a>
          )}
        </p>
      </section>
    </article>
  );
}
