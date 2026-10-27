import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";

import { ApplicationsList } from "./applications-list";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Jobs you saved, are preparing, or applied to. A drag-and-drop board arrives in the next phase."
      />
      <ApplicationsList />
    </>
  );
}
