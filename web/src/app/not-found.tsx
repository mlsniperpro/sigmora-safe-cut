import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Page not found · Safe Cut" };

export default function NotFound() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-xl font-medium">We couldn&apos;t find that page.</h1>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link href="/" className="inline-flex min-h-11 items-center rounded-lg border border-border bg-surface px-3 font-medium">
          Go to the home page
        </Link>
        <Link href="/try" className="inline-flex min-h-11 items-center rounded-lg border border-border bg-surface px-3 font-medium">
          Try Safe Cut
        </Link>
      </div>
    </section>
  );
}
