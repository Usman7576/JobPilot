import { LayoutDashboard } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" description="Your job search at a glance." />
      <EmptyState
        icon={LayoutDashboard}
        title="Stats appear once you start applying"
        description="Jobs found, average match score, reply rate, interviews and your top missing skills (Phase 6)."
      />
    </>
  );
}
