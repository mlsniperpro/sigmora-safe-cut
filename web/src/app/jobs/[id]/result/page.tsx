import type { Metadata } from "next";
import { Suspense } from "react";
import { JobSkeleton } from "@/components/job/JobPage";
import { ResultPage } from "@/components/job/ResultPage";

export const metadata: Metadata = { title: "Your clip is ready · Safe Cut", robots: { index: false } };

export default function Page() {
  return (
    <Suspense fallback={<JobSkeleton />}>
      <ResultPage />
    </Suspense>
  );
}
