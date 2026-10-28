import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";

import { ApplicationsList } from "./applications-list";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader title="Applications" description="Track every application from saved to offer." />
      <ApplicationsList />
    </>
  );
}
