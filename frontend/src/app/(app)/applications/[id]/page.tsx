import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import { ApplicationView } from "./application-view";

export const metadata: Metadata = { title: "Application" };

export default function ApplicationPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
      <ApplicationView />
    </Suspense>
  );
}
