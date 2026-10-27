import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import { JobDetailView } from "./job-detail-view";

export const metadata: Metadata = { title: "Job" };

export default function JobPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
      <JobDetailView />
    </Suspense>
  );
}
