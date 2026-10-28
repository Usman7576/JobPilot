"use client";

import { LayoutDashboard, Table2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardGetDashboard } from "@/lib/api/generated/dashboard/dashboard";
import type { WeekPoint } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

// Categorical slots 1-3 of the reference palette, validated together in light and dark.
// Text never uses these: values and labels stay in the normal text colors.
const SERIES = [
  { key: "applied", label: "Applied", fill: "bg-[#2a78d6] dark:bg-[#3987e5]" },
  { key: "replied", label: "Replied", fill: "bg-[#eb6834] dark:bg-[#d95926]" },
  { key: "interviews", label: "Interviews", fill: "bg-[#1baf7a] dark:bg-[#199e70]" },
] as const;
const SINGLE = "bg-[#2a78d6] dark:bg-[#3987e5]"; // one-series bars: slot 1
const RANGES = [
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
  { days: 365, label: "Last year" },
];

const pct = (v: number) => `${Math.round(v * 100)}%`;
const weekLabel = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="gap-1 py-4">
      <CardContent className="grid gap-1 px-4">
        <span className="text-muted-foreground text-xs font-medium">{label}</span>
        <span className="text-2xl font-semibold tabular-nums">{value}</span>
        {note && <span className="text-muted-foreground text-xs">{note}</span>}
      </CardContent>
    </Card>
  );
}

/** Horizontal bars for one series: label, bar, value; the bar's end is rounded, the base square. */
function BarList({
  rows,
}: {
  rows: { label: string; value: number; unit?: string; note?: string }[];
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="grid gap-2">
      {rows.map((r) => (
        <li
          key={r.label}
          className="grid grid-cols-[minmax(6rem,9rem)_1fr_auto] items-center gap-3 text-sm"
          title={`${r.label}: ${r.value}${r.unit ? ` ${r.unit}` : ""}${r.note ? ` (${r.note})` : ""}`}
        >
          <span className="truncate">{r.label}</span>
          <span className="bg-muted/60 h-4 rounded-r-[4px]">
            <span
              className={cn("block h-full rounded-r-[4px]", SINGLE)}
              style={{ width: `${(r.value / max) * 100}%` }}
            />
          </span>
          <span className="text-muted-foreground text-right text-xs tabular-nums">
            {r.value}
            {r.unit ? ` ${r.unit}` : ""}
            {r.note ? ` · ${r.note}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function WeeklyChart({ weeks }: { weeks: WeekPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const max = Math.max(1, ...weeks.flatMap((w) => [w.applied, w.replied, w.interviews]));
  const shown = hover != null ? weeks[hover] : null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="grid gap-1">
          <CardTitle className="text-base">Weekly activity</CardTitle>
          <CardDescription>Applications sent, replies and interviews per week.</CardDescription>
        </div>
        <Button size="sm" variant="ghost" aria-pressed={table} onClick={() => setTable((t) => !t)}>
          <Table2 className="size-4" /> {table ? "Chart" : "Table"}
        </Button>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ul className="flex flex-wrap gap-4 text-xs" aria-label="Legend">
          {SERIES.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className={cn("size-2.5 rounded-sm", s.fill)} aria-hidden />
              {s.label}
            </li>
          ))}
        </ul>

        {table ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted-foreground text-left text-xs">
                <th className="py-1 font-medium">Week of</th>
                {SERIES.map((s) => (
                  <th key={s.key} className="py-1 text-right font-medium">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {weeks.map((w) => (
                <tr key={w.week_start} className="border-t">
                  <td className="py-1">{weekLabel(w.week_start)}</td>
                  {SERIES.map((s) => (
                    <td key={s.key} className="py-1 text-right tabular-nums">
                      {w[s.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="relative">
            {/* The hover readout sits above the plot, so it never covers a bar. */}
            <p className="text-muted-foreground h-5 text-xs" aria-live="polite">
              {shown
                ? `Week of ${weekLabel(shown.week_start)}: ${shown.applied} applied, ${shown.replied} replied, ${shown.interviews} interviews`
                : "Hover a week for its numbers."}
            </p>
            <div
              className="flex h-40 items-end gap-2 border-b"
              role="img"
              aria-label="Weekly activity bar chart; use Table for the numbers"
            >
              {weeks.map((w, i) => (
                <div
                  key={w.week_start}
                  className={cn(
                    "flex h-full flex-1 cursor-default items-end justify-center gap-0.5 rounded-sm",
                    hover === i && "bg-muted/60",
                  )}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  {SERIES.map((s) => {
                    const v = w[s.key];
                    return (
                      <div key={s.key} className="flex h-full w-full max-w-3 flex-col justify-end">
                        {v > 0 && (
                          <span className="text-muted-foreground mb-0.5 text-center text-[10px] tabular-nums">
                            {v}
                          </span>
                        )}
                        <div
                          className={cn("w-full rounded-t-[4px]", s.fill)}
                          style={{ height: `${(v / max) * 85}%` }}
                        />
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
            <div className="text-muted-foreground mt-1 flex gap-2 text-[10px]">
              {weeks.map((w) => (
                <span key={w.week_start} className="flex-1 text-center">
                  {weekLabel(w.week_start)}
                </span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardView() {
  const [days, setDays] = useState(30);
  const dash = useDashboardGetDashboard({ days });

  return (
    <div className="grid gap-6">
      <div className="flex items-center gap-2">
        <label htmlFor="range" className="text-muted-foreground text-sm">
          Period
        </label>
        <select
          id="range"
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          {RANGES.map((r) => (
            <option key={r.days} value={r.days}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      {!dash.data ? (
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : dash.data.stats.jobs_found === 0 && dash.data.stats.applied === 0 ? (
        <EmptyState
          icon={LayoutDashboard}
          title="Nothing to show for this period yet"
          description="Run a search and prepare a few applications; your numbers appear here."
          action={
            <Button asChild>
              <Link href="/jobs">Find jobs</Link>
            </Button>
          }
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="Jobs found" value={String(dash.data.stats.jobs_found)} />
            <Stat
              label="Average match"
              value={
                dash.data.stats.avg_match_score != null
                  ? String(Math.round(dash.data.stats.avg_match_score))
                  : "–"
              }
              note="of scored jobs"
            />
            <Stat label="Applied" value={String(dash.data.stats.applied)} />
            <Stat
              label="Reply rate"
              value={dash.data.stats.reply_rate != null ? pct(dash.data.stats.reply_rate) : "–"}
              note={`${dash.data.stats.replied} replied`}
            />
            <Stat
              label="Interviews"
              value={String(dash.data.stats.interviews)}
              note={dash.data.stats.offers ? `${dash.data.stats.offers} offer(s)` : undefined}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Funnel</CardTitle>
                <CardDescription>How far your applications get.</CardDescription>
              </CardHeader>
              <CardContent>
                <BarList
                  rows={dash.data.funnel.map((step, i, all) => ({
                    label: step.step,
                    value: step.count,
                    note:
                      i > 0 && all[i - 1].count > 0
                        ? pct(step.count / all[i - 1].count)
                        : undefined,
                  }))}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Skills to learn next</CardTitle>
                <CardDescription>
                  What your good matches ask for that your resume doesn&apos;t show.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {dash.data.missing_skills.length ? (
                  <BarList
                    rows={dash.data.missing_skills.map((g) => ({
                      label: g.skill,
                      value: g.jobs,
                      unit: g.jobs === 1 ? "job" : "jobs",
                    }))}
                  />
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No gaps yet. They appear once some jobs are scored.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <WeeklyChart weeks={dash.data.weekly} />
        </>
      )}
    </div>
  );
}
