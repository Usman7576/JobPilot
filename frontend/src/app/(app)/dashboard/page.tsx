import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";

import { DashboardView } from "./dashboard-view";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" description="Your job search at a glance." />
      <DashboardView />
    </>
  );
}
