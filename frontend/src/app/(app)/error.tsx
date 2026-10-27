"use client";

import { TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";

export default function AppError({ reset }: { error: Error; reset: () => void }) {
  return (
    <EmptyState
      icon={TriangleAlert}
      title="Something went wrong"
      description="This page hit an unexpected error. Try again, and if it keeps happening, reload the app."
      action={<Button onClick={reset}>Try again</Button>}
    />
  );
}
