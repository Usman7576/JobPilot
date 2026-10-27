import type { JobCard, RemoteType } from "@/lib/api/generated/model";

const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

export function formatSalary(
  job: Pick<JobCard, "salary_min" | "salary_max" | "salary_currency" | "salary_period">,
) {
  if (!job.salary_min && !job.salary_max) return null;
  const symbol = job.salary_currency ? `${job.salary_currency} ` : "";
  const lo = job.salary_min ? compact.format(job.salary_min) : null;
  const hi = job.salary_max ? compact.format(job.salary_max) : null;
  const range = lo && hi && lo !== hi ? `${lo}–${hi}` : (lo ?? hi);
  const per = job.salary_period === "hour" ? "/hr" : job.salary_period === "month" ? "/mo" : "/yr";
  return `${symbol}${range}${per}`;
}

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function timeAgo(iso: string | null) {
  if (!iso) return null;
  const days = Math.round((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (days === 0) return "today";
  if (Math.abs(days) < 30) return rtf.format(days, "day");
  return rtf.format(Math.round(days / 30), "month");
}

export const REMOTE_LABEL: Record<RemoteType, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
  unknown: "",
};
