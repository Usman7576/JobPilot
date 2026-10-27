"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, CircleMinus, Loader2, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { getJobsListJobsQueryKey } from "@/lib/api/generated/jobs/jobs";
import type { SearchRunSourceOut } from "@/lib/api/generated/model";
import {
  getSearchesGetActiveSearchQueryKey,
  useSearchesCancelSearch,
  useSearchesGetSearch,
} from "@/lib/api/generated/searches/searches";
import { errorMessage } from "@/lib/forms";

function SourceChip({ s }: { s: SearchRunSourceOut }) {
  const icon =
    s.status === "ok" ? (
      <CircleCheck className="size-3.5 text-emerald-600" />
    ) : s.status === "failed" ? (
      <CircleAlert className="text-destructive size-3.5" />
    ) : s.status === "skipped" ? (
      <CircleMinus className="text-muted-foreground size-3.5" />
    ) : s.status === "running" ? (
      <Loader2 className="size-3.5 animate-spin" />
    ) : null;
  return (
    <Badge variant="outline" className="gap-1.5" title={s.error_message ?? undefined}>
      {icon}
      {s.label}
      {s.status === "ok" && <span className="text-muted-foreground">{s.fetched_count}</span>}
      {s.status === "skipped" && <span className="text-muted-foreground">skipped</span>}
      {s.status === "failed" && <span className="text-muted-foreground">failed</span>}
    </Badge>
  );
}

/** Live progress for one search run; refreshes the job list as it goes. */
export function SearchProgress({ runId, onDone }: { runId: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const cancel = useSearchesCancelSearch();
  const run = useSearchesGetSearch(runId, {
    query: { refetchInterval: (q) => (!q.state.data || q.state.data.is_active ? 2000 : false) },
  });
  const data = run.data;
  const lastNew = useRef(0);

  useEffect(() => {
    const found = data?.counts.new_for_you ?? 0;
    if (found !== lastNew.current || (data && !data.is_active)) {
      lastNew.current = found;
      queryClient.invalidateQueries({ queryKey: getJobsListJobsQueryKey() });
    }
    if (data && !data.is_active) {
      queryClient.invalidateQueries({ queryKey: getSearchesGetActiveSearchQueryKey() });
    }
  }, [data, queryClient]);

  if (!data) return <Progress value={5} aria-label="Starting search" />;

  const finished = !data.is_active;
  const issues = data.sources.filter((s) => s.status === "failed" || s.status === "skipped");
  const title = finished
    ? data.status === "cancelled"
      ? "Search cancelled"
      : data.status === "failed"
        ? "Search failed"
        : `Found ${data.counts.new_for_you ?? 0} new job${data.counts.new_for_you === 1 ? "" : "s"}`
    : (data.stage_detail ?? "Searching…");

  return (
    <div className="grid gap-3 rounded-xl border p-4" aria-live="polite">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {finished ? (
            data.status === "failed" ? (
              <CircleAlert className="text-destructive size-5" />
            ) : (
              <CircleCheck className="size-5 text-emerald-600" />
            )
          ) : (
            <Loader2 className="size-5 animate-spin" />
          )}
          <div className="grid">
            <p className="font-medium">{title}</p>
            <p className="text-muted-foreground text-xs">
              {data.counts.scraped ?? 0} results · {data.counts.new ?? 0} new postings ·{" "}
              {data.counts.duplicates ?? 0} duplicates merged
            </p>
          </div>
        </div>
        {finished ? (
          <Button variant="ghost" size="icon" aria-label="Dismiss" onClick={onDone}>
            <X className="size-4" />
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            disabled={cancel.isPending}
            onClick={() =>
              cancel.mutate(
                { runId },
                { onSuccess: () => run.refetch(), onError: (e) => toast.error(errorMessage(e)) },
              )
            }
          >
            Cancel
          </Button>
        )}
      </div>
      {!finished && <Progress value={data.progress} aria-label="Search progress" />}
      <div className="flex flex-wrap gap-1.5">
        {data.sources.map((s) => (
          <SourceChip key={s.source} s={s} />
        ))}
      </div>
      {finished && issues.length > 0 && (
        <ul className="text-muted-foreground grid gap-0.5 text-xs">
          {issues.map((s) => (
            <li key={s.source}>
              <strong>{s.label}:</strong> {s.error_message ?? s.error_code}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
