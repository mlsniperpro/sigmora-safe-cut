import Link from "next/link";

export default function NotFound() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <p className="text-xl font-medium">We couldn&apos;t find that page.</p>
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
