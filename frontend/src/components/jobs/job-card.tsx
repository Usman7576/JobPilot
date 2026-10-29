"use client";

import { Building2, CheckCircle2, Clock, EyeOff, Mail, MapPin, Wallet } from "lucide-react";
import Link from "next/link";

import { ScoreBadge } from "@/components/jobs/match";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { JobCard as Job, PayStatus } from "@/lib/api/generated/model";
import { formatSalary, REMOTE_LABEL, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

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

const APPLIED = new Set([
  "queued",
  "applied",
  "replied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
]);
const APP_LABEL: Record<string, string> = {
  saved: "Saved",
  drafting: "Writing…",
  ready: "Draft ready",
  queued: "Sending soon",
  applied: "Applied",
  replied: "Replied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

/** Jobs that can go into "Prepare emails": an address in the posting, not applied yet. */
export function canBatch(job: Job) {
  return job.has_contact_email && !APPLIED.has(job.application?.status ?? "");
}

export function JobCard({
  job,
  onDismiss,
  selected,
  onSelect,
}: {
  job: Job;
  onDismiss: () => void;
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
}) {
  const salary = formatSalary(job);
  const remote = REMOTE_LABEL[job.remote_type];
  const status = job.application?.status;
  return (
    <article
      className={cn(
        "hover:border-primary/40 grid gap-3 rounded-xl border p-4 transition-colors",
        selected && "border-primary bg-primary/5",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        {onSelect && (
          <input
            type="checkbox"
            className="mt-1 size-4 shrink-0"
            aria-label={`Select ${job.title}`}
            checked={Boolean(selected)}
            disabled={!canBatch(job)}
            title={canBatch(job) ? undefined : "Needs an email in the posting, and not applied yet"}
            onChange={(e) => onSelect(e.target.checked)}
          />
        )}
        <div className="grid min-w-0 flex-1 gap-1">
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
        <div className="flex shrink-0 items-center gap-1">
          <ScoreBadge match={job.match} />
          <Button variant="ghost" size="icon" aria-label="Hide this job" onClick={onDismiss}>
            <EyeOff className="size-4" />
          </Button>
        </div>
      </div>
      {job.snippet && <p className="text-muted-foreground line-clamp-2 text-sm">{job.snippet}</p>}
      <div className="flex flex-wrap items-center gap-1.5">
        <PayBadge job={job} />
        {status && (
          <Badge variant={APPLIED.has(status) ? "default" : "secondary"} className="gap-1">
            {APPLIED.has(status) && <CheckCircle2 className="size-3" aria-hidden />}
            {APP_LABEL[status] ?? status}
          </Badge>
        )}
        {job.has_contact_email && (
          <Badge variant="outline" className="gap-1">
            <Mail className="size-3" aria-hidden /> Email
          </Badge>
        )}
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
