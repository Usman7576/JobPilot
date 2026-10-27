"use client";

import { Building2, Clock, EyeOff, MapPin, Wallet } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { JobCard as Job, PayStatus } from "@/lib/api/generated/model";
import { formatSalary, REMOTE_LABEL, timeAgo } from "@/lib/format";

const PAY: Record<PayStatus, { label: string; className: string }> = {
  paid: { label: "Paid", className: "bg-emerald-600 text-white hover:bg-emerald-600" },
  unpaid: { label: "Unpaid", className: "bg-amber-500 text-white hover:bg-amber-500" },
  unknown: { label: "Pay not stated", className: "" },
};

/** Paid / unpaid label; shown on internships, where it's the question people ask first. */
export function PayBadge({ job }: { job: Pick<Job, "employment_type" | "pay_status"> }) {
  if (job.employment_type !== "internship") return null;
  const pay = PAY[job.pay_status];
  return (
    <Badge variant={job.pay_status === "unknown" ? "outline" : "default"} className={pay.className}>
      {pay.label}
    </Badge>
  );
}

export function JobCard({ job, onDismiss }: { job: Job; onDismiss: () => void }) {
  const salary = formatSalary(job);
  const remote = REMOTE_LABEL[job.remote_type];
  return (
    <article className="hover:border-primary/40 grid gap-3 rounded-xl border p-4 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1">
          <Link href={`/jobs/${job.id}`} className="truncate font-medium hover:underline">
            {job.title}
          </Link>
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="flex items-center gap-1">
              <Building2 className="size-3.5" aria-hidden /> {job.company_name}
            </span>
            {job.location_raw && (
              <span className="flex items-center gap-1">
                <MapPin className="size-3.5" aria-hidden /> {job.location_raw}
              </span>
            )}
            {salary && (
              <span className="flex items-center gap-1">
                <Wallet className="size-3.5" aria-hidden /> {salary}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Clock className="size-3.5" aria-hidden />{" "}
              {timeAgo(job.posted_at ?? job.discovered_at)}
            </span>
          </div>
        </div>
        <Button variant="ghost" size="icon" aria-label="Hide this job" onClick={onDismiss}>
          <EyeOff className="size-4" />
        </Button>
      </div>
      {job.snippet && <p className="text-muted-foreground line-clamp-2 text-sm">{job.snippet}</p>}
      <div className="flex flex-wrap items-center gap-1.5">
        <PayBadge job={job} />
        {remote && <Badge>{remote}</Badge>}
        {job.seniority && (
          <Badge variant="secondary" className="capitalize">
            {job.seniority}
          </Badge>
        )}
        {job.min_years_experience != null && (
          <Badge variant="secondary">{job.min_years_experience}+ yrs</Badge>
        )}
        {job.required_skills.slice(0, 5).map((s) => (
          <Badge key={s} variant="outline">
            {s}
          </Badge>
        ))}
        <span className="text-muted-foreground ml-auto text-xs">via {job.sources.join(", ")}</span>
      </div>
    </article>
  );
}
