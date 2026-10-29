import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";

import { ReviewQueue } from "./review-queue";

export const metadata: Metadata = { title: "Review emails" };

export default function ReviewPage() {
  return (
    <>
      <PageHeader
        title="Review emails"
        description="Read each prepared application, then approve it to send or skip it."
      />
      <ReviewQueue />
    </>
  );
}
