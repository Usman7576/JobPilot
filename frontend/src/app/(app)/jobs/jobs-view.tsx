"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { JobCard } from "@/components/jobs/job-card";
import { SearchProgress } from "@/components/jobs/search-progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/fetcher";
import {
  getJobsListJobsQueryKey,
  useJobsDismissJob,
  useJobsListJobs,
  useJobsUndismissJob,
} from "@/lib/api/generated/jobs/jobs";
import type { RemoteType } from "@/lib/api/generated/model";
import {
  usePreferencesGetPreferences,
  usePreferencesListSources,
} from "@/lib/api/generated/preferences/preferences";
import {
  useSearchesGetActiveSearch,
  useSearchesStartSearch,
} from "@/lib/api/generated/searches/searches";
import { errorMessage } from "@/lib/forms";

const PAGE = 20;
const selectClass = "border-input bg-background h-9 rounded-md border px-2 text-sm";

function useDebounced<T>(value: T, ms = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function JobsView() {
  const queryClient = useQueryClient();
  const prefs = usePreferencesGetPreferences();
  const sources = usePreferencesListSources();
  const active = useSearchesGetActiveSearch();
  const start = useSearchesStartSearch();
  const dismiss = useJobsDismissJob();
  const undismiss = useJobsUndismissJob();

  const [runId, setRunId] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [remote, setRemote] = useState<RemoteType | "">("");
  const [limit, setLimit] = useState(PAGE);
  const query = useDebounced(q);

  const shownRun = runId ?? active.data?.id ?? null;
  const jobs = useJobsListJobs({
    q: query || undefined,
    source: source || undefined,
    remote_type: remote || undefined,
    limit,
  });

  const findJobs = () =>
    start.mutate(undefined, {
      onSuccess: (run) => setRunId(run.id),
      onError: (e) => {
        if (e instanceof ApiError && e.status === 409 && typeof e.problem.run_id === "string") {
          setRunId(e.problem.run_id);
          return;
        }
        toast.error(errorMessage(e));
      },
    });

  const hide = (id: string) =>
    dismiss.mutate(
      { jobId: id },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getJobsListJobsQueryKey() });
          toast("Job hidden", {
            action: {
              label: "Undo",
              onClick: () =>
                undismiss.mutate(
                  { jobId: id },
                  {
                    onSuccess: () =>
                      queryClient.invalidateQueries({ queryKey: getJobsListJobsQueryKey() }),
                  },
                ),
            },
          });
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );

  const needsPrefs = prefs.data && (!prefs.data.is_saved || !prefs.data.target_titles?.length);
  const searching = Boolean(shownRun && active.data?.is_active);

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Fresh jobs from your sources. Match scores arrive in the next phase."
        actions={
          <Button onClick={findJobs} disabled={start.isPending || searching || Boolean(needsPrefs)}>
            <Search className="size-4" /> {searching ? "Searching…" : "Find jobs"}
          </Button>
        }
      />

      {shownRun && (
        <div className="mb-6">
          <SearchProgress runId={shownRun} onDone={() => setRunId(null)} />
        </div>
      )}

      {needsPrefs ? (
        <EmptyState
          icon={SlidersHorizontal}
          title="Tell us what to look for"
          description="Set your target job titles, locations and sources, then run your first search."
          action={
            <Button asChild>
              <Link href="/settings">Set preferences</Link>
            </Button>
          }
        />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <Input
              className="max-w-xs"
              placeholder="Search title or company"
              aria-label="Search jobs"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setLimit(PAGE);
              }}
            />
            <select
              aria-label="Source"
              className={selectClass}
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="">All sources</option>
              {sources.data?.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.label}
                </option>
              ))}
            </select>
            <select
              aria-label="Work arrangement"
              className={selectClass}
              value={remote}
              onChange={(e) => setRemote(e.target.value as RemoteType | "")}
            >
              <option value="">Any arrangement</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
            {jobs.data && (
              <span className="text-muted-foreground self-center text-sm">
                {jobs.data.total} jobs
              </span>
            )}
          </div>

          {jobs.isPending ? (
            <div className="grid gap-3">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-32 w-full rounded-xl" />
              ))}
            </div>
          ) : jobs.data?.items.length ? (
            <div className="grid gap-3">
              {jobs.data.items.map((job) => (
                <JobCard key={job.id} job={job} onDismiss={() => hide(job.id)} />
              ))}
              {jobs.data.has_more && (
                <Button
                  variant="outline"
                  className="justify-self-center"
                  onClick={() => setLimit((l) => l + PAGE)}
                >
                  Load more
                </Button>
              )}
            </div>
          ) : (
            <EmptyState
              icon={Search}
              title={q || source || remote ? "No jobs match these filters" : "No jobs yet"}
              description={
                q || source || remote
                  ? "Try clearing a filter."
                  : "Click “Find jobs” to search your sources. It usually takes under a minute."
              }
            />
          )}
        </>
      )}
    </>
  );
}
