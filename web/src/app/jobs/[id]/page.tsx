import type { Metadata } from "next";
import { Suspense } from "react";
import { JobPage, JobSkeleton } from "@/components/job/JobPage";

export const metadata: Metadata = { title: "Review your clip · Safe Cut", robots: { index: false } };

export default function Page() {
  return (
    <Suspense fallback={<JobSkeleton />}>
      <JobPage />
    </Suspense>
  );
}
