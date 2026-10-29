import { Inbox } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";

import { ApplicationsList } from "./applications-list";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Track every application from saved to offer."
        actions={
          <Button asChild variant="outline">
            <Link href="/applications/review">
              <Inbox className="size-4" /> Review emails
            </Link>
          </Button>
        }
      />
      <ApplicationsList />
    </>
  );
}
