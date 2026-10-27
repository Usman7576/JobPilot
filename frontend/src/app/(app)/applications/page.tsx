import { KanbanSquare } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Saved → Applied → Replied → Interview → Offer / Rejected."
      />
      <EmptyState
        icon={KanbanSquare}
        title="Nothing tracked yet"
        description="Jobs you save or apply to will show up on a drag-and-drop board here (Phase 6)."
      />
    </>
  );
}
