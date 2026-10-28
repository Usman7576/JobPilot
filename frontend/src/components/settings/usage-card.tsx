"use client";

import { Sparkles } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { UsageFeature } from "@/lib/api/generated/model";
import { useUsageGetUsage } from "@/lib/api/generated/usage/usage";
import { cn } from "@/lib/utils";

const FEATURE: Record<UsageFeature, string> = {
  resume_parse: "Reading resumes",
  normalize: "Cleaning job posts",
  score: "Scoring matches",
  generate: "Writing emails and letters",
  verify: "Fact-checking drafts",
  classify: "Sorting replies",
  embed: "Embeddings",
};
const BAR = "bg-[#2a78d6] dark:bg-[#3987e5]"; // one series: categorical slot 1
const number = new Intl.NumberFormat();

export function UsageCard() {
  const usage = useUsageGetUsage();
  const u = usage.data;
  if (!u) return <Skeleton className="h-56 w-full max-w-2xl rounded-xl" />;
  const max = Math.max(1, ...u.daily.map((d) => d.requests));
  const month = new Date(`${u.month_start}T00:00:00`).toLocaleDateString(undefined, {
    month: "long",
  });

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4" aria-hidden /> AI usage
        </CardTitle>
        <CardDescription>
          AI requests you made in {month}. Free tiers cost nothing; when a daily limit is reached,
          scoring and writing pause until the next day.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5 text-sm">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div className="grid">
            <span className="text-muted-foreground text-xs">Requests this month</span>
            <span className="text-2xl font-semibold tabular-nums">{number.format(u.requests)}</span>
          </div>
          <div className="grid">
            <span className="text-muted-foreground text-xs">Left today (whole app)</span>
            <span className="text-2xl font-semibold tabular-nums">
              {u.requests_left_today == null ? "No limit" : number.format(u.requests_left_today)}
            </span>
            {u.daily_request_limit != null && (
              <span className="text-muted-foreground text-xs">
                of {number.format(u.daily_request_limit)} a day
              </span>
            )}
          </div>
          <div className="grid">
            <span className="text-muted-foreground text-xs">Cost</span>
            <span className="text-2xl font-semibold tabular-nums">${u.cost_usd.toFixed(2)}</span>
          </div>
        </div>

        {u.by_feature.length > 0 ? (
          <table className="w-full">
            <thead>
              <tr className="text-muted-foreground text-left text-xs">
                <th className="py-1 font-medium">What for</th>
                <th className="py-1 text-right font-medium">Requests</th>
                <th className="py-1 text-right font-medium">Tokens in / out</th>
              </tr>
            </thead>
            <tbody>
              {u.by_feature.map((f) => (
                <tr key={f.feature} className="border-t">
                  <td className="py-1.5">{FEATURE[f.feature] ?? f.feature}</td>
                  <td className="py-1.5 text-right tabular-nums">{number.format(f.requests)}</td>
                  <td className="text-muted-foreground py-1.5 text-right tabular-nums">
                    {number.format(f.input_tokens)} / {number.format(f.output_tokens)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-muted-foreground">No AI requests yet this month.</p>
        )}

        <div className="grid gap-1.5">
          <span className="text-muted-foreground text-xs">Requests per day, last 30 days</span>
          <div
            className="flex h-16 items-end gap-0.5 border-b"
            role="img"
            aria-label="Daily AI requests"
          >
            {u.daily.map((d) => (
              <div
                key={d.day}
                title={`${new Date(`${d.day}T00:00:00`).toLocaleDateString()}: ${d.requests}`}
                className="flex h-full flex-1 items-end"
              >
                <div
                  className={cn("w-full rounded-t-[2px]", d.requests ? BAR : "bg-transparent")}
                  style={{ height: `${(d.requests / max) * 100}%` }}
                />
              </div>
            ))}
          </div>
        </div>

        <p className="text-muted-foreground text-xs">
          Models:{" "}
          {u.by_model.length
            ? u.by_model.map((m) => `${m.model} (${m.requests})`).join(", ")
            : "none yet"}
          . Main AI: {u.provider}; writing: {u.writing_provider}.
        </p>
      </CardContent>
    </Card>
  );
}
