import { Search } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Jobs" };

export default function JobsPage() {
  return (
    <>
      <PageHeader
        title="Jobs"
        description="Fresh jobs ranked by how well they match your resume."
        actions={
          <Button disabled>
            <Search className="size-4" /> Find jobs
          </Button>
        }
      />
      <EmptyState
        icon={Search}
        title="No jobs yet"
        description="Job discovery (Phase 3) and match scoring (Phase 4) will fill this feed with ranked, explained matches."
      />
    </>
  );
}
