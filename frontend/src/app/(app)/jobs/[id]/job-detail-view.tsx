"use client";

import { ArrowLeft, Building2, Clock, ExternalLink, Mail, MapPin, Wallet } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/fetcher";
import { useJobsGetJob } from "@/lib/api/generated/jobs/jobs";
import { formatSalary, REMOTE_LABEL, timeAgo } from "@/lib/format";

export function JobDetailView() {
  const { id } = useParams<{ id: string }>();
  const job = useJobsGetJob(id);

  if (job.error instanceof ApiError && job.error.status === 404) {
    return (
      <EmptyState
        icon={Building2}
        title="Job not found"
        description="It may have been removed, or it belongs to another account."
        action={
          <Button asChild variant="outline">
            <Link href="/jobs">Back to jobs</Link>
          </Button>
        }
      />
    );
  }
  if (!job.data) return <Skeleton className="h-96 w-full rounded-xl" />;

  const j = job.data;
  const salary = formatSalary(j);
  const remote = REMOTE_LABEL[j.remote_type];
  const applyUrl = j.apply_url ?? j.url;

  return (
    <div className="grid gap-6">
      <Link
        href="/jobs"
        className="text-muted-foreground flex items-center gap-1 text-sm hover:underline"
      >
        <ArrowLeft className="size-4" /> All jobs
      </Link>

      <header className="grid gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{j.title}</h1>
        <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span className="flex items-center gap-1">
            <Building2 className="size-4" /> {j.company_name}
          </span>
          {j.location_raw && (
            <span className="flex items-center gap-1">
              <MapPin className="size-4" /> {j.location_raw}
            </span>
          )}
          {salary && (
            <span className="flex items-center gap-1">
              <Wallet className="size-4" /> {salary}
            </span>
          )}
          <span className="flex items-center gap-1">
            <Clock className="size-4" /> Posted {timeAgo(j.posted_at ?? j.discovered_at)}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {remote && <Badge>{remote}</Badge>}
          {j.employment_type !== "unknown" && (
            <Badge variant="secondary">{j.employment_type.replace("_", " ")}</Badge>
          )}
          {j.seniority && (
            <Badge variant="secondary" className="capitalize">
              {j.seniority}
            </Badge>
          )}
          {j.min_years_experience != null && (
            <Badge variant="secondary">{j.min_years_experience}+ years</Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            {/* Third-party link: no referrer, no access to this window. */}
            <a href={applyUrl} target="_blank" rel="noopener noreferrer">
              View posting <ExternalLink className="size-4" />
            </a>
          </Button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Description</CardTitle>
          </CardHeader>
          <CardContent>
            {j.description_text ? (
              <div className="text-sm leading-relaxed whitespace-pre-line">
                {j.description_text}
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">
                This source only provided a title. Open the posting for details.
              </p>
            )}
          </CardContent>
        </Card>

        <aside className="grid content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Skills mentioned</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-1.5">
              {j.required_skills.length ? (
                j.required_skills.map((s) => (
                  <Badge key={s} variant="outline">
                    {s}
                  </Badge>
                ))
              ) : (
                <p className="text-muted-foreground text-sm">None detected.</p>
              )}
            </CardContent>
          </Card>
          {j.contact_emails.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Contact</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-1 text-sm">
                {j.contact_emails.map((e) => (
                  <span key={e} className="flex items-center gap-2">
                    <Mail className="size-4" /> {e}
                  </span>
                ))}
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Found on</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-1 text-sm">
              {j.source_links.map((s) => (
                <a
                  key={s.source + s.url}
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 hover:underline"
                >
                  {s.label} <ExternalLink className="size-3" />
                </a>
              ))}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
