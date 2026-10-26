"use client";
import Link from "next/link";
import { useEffect } from "react";

/** §7 "Unexpected error": never a stack trace, request ID or raw model output. */
export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    const digest = error instanceof Error && "digest" in error ? String((error as { digest?: unknown }).digest ?? "") : "";
    console.error(`unexpected error${digest ? ` (${digest})` : ""}`);
  }, [error]);
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <p role="alert" className="text-xl font-medium">
        Something went wrong on our side. Nothing has been published.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <button type="button" onClick={() => retry()} className="inline-flex min-h-11 items-center rounded-lg border border-border bg-surface px-3 font-medium">
          Try again
        </button>
        <Link href="/" className="inline-flex min-h-11 items-center rounded-lg border border-border bg-surface px-3 font-medium">
          Go to the home page
        </Link>
      </div>
    </section>
  );
}
