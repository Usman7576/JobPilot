"use client";

import { Building2, KanbanSquare, Mail, MousePointerClick } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useApplicationsListApplications } from "@/lib/api/generated/applications/applications";
import type { ApplicationStatus } from "@/lib/api/generated/model";
import { timeAgo } from "@/lib/format";

const STATUS: Partial<
  Record<ApplicationStatus, { label: string; variant: "default" | "secondary" | "outline" }>
> = {
  saved: { label: "Saved", variant: "outline" },
  drafting: { label: "Writing…", variant: "secondary" },
  ready: { label: "Ready to review", variant: "secondary" },
  applied: { label: "Applied", variant: "default" },
};

export function ApplicationsList() {
  const list = useApplicationsListApplications();

  if (list.isPending) {
    return (
      <div className="grid gap-3">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (!list.data?.length) {
    return (
      <EmptyState
        icon={KanbanSquare}
        title="Nothing here yet"
        description="Open a job and click “Prepare application” or “Save for later”."
        action={
          <Button asChild>
            <Link href="/jobs">Browse jobs</Link>
          </Button>
        }
      />
    );
  }
  return (
    <ul className="grid gap-3">
      {list.data.map((a) => {
        const status = STATUS[a.status] ?? { label: a.status, variant: "outline" as const };
        return (
          <li key={a.id}>
            <Link
              href={a.status === "saved" ? `/jobs/${a.job_id}` : `/applications/${a.id}`}
              className="hover:border-primary/40 flex items-center justify-between gap-3 rounded-xl border p-4 transition-colors"
            >
              <div className="grid min-w-0 gap-1">
                <span className="truncate font-medium">{a.job_title}</span>
                <span className="text-muted-foreground flex flex-wrap items-center gap-x-3 text-sm">
                  <span className="flex items-center gap-1">
                    <Building2 className="size-3.5" aria-hidden /> {a.company_name}
                  </span>
                  {a.channel === "email" && a.contact_email && (
                    <span className="flex items-center gap-1">
                      <Mail className="size-3.5" aria-hidden /> {a.contact_email}
                    </span>
                  )}
                  {a.channel === "site" && (
                    <span className="flex items-center gap-1">
                      <MousePointerClick className="size-3.5" aria-hidden /> Apply on site
                    </span>
                  )}
                </span>
              </div>
              <div className="grid shrink-0 justify-items-end gap-1">
                <Badge variant={status.variant}>{status.label}</Badge>
                <span className="text-muted-foreground text-xs">
                  {a.sent_at ? `applied ${timeAgo(a.sent_at)}` : `updated ${timeAgo(a.updated_at)}`}
                </span>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
