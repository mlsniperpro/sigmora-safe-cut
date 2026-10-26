import { SITE } from "@/lib/site";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-border bg-surface text-sm text-muted">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6">
        <p>Built for the Meta Global AI Developer Hackathon with Muse Spark, SAM 3.1 and Muse Voice Transcribe on the Meta Model API.</p>
        <p>
          New work: Safe Cut was built during the hackathon (Oct 26 – Nov 4, 2026); the commit history shows every change. Sigmora is the existing product it plugs into.
        </p>
        <p className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Uploads are deleted from Safe Cut&apos;s servers after 24 hours.</span>
          <span>MIT licence</span>
          <a href={SITE.repoUrl} className="underline underline-offset-2" rel="noopener noreferrer" target="_blank">
            Source on GitHub
          </a>
        </p>
      </div>
    </footer>
  );
}
