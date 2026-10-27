"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Briefcase, GraduationCap, Search, SlidersHorizontal } from "lucide-react";
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
import type {
  JobsListJobsSort,
  PayStatus,
  Recommendation,
  RemoteType,
  SearchKind,
} from "@/lib/api/generated/model";
import {
  usePreferencesGetPreferences,
  usePreferencesListSources,
} from "@/lib/api/generated/preferences/preferences";
import {
  useSearchesGetActiveSearch,
  useSearchesStartSearch,
} from "@/lib/api/generated/searches/searches";
import { errorMessage } from "@/lib/forms";
import { cn } from "@/lib/utils";

const PAGE = 20;
const selectClass = "border-input bg-background h-9 rounded-md border px-2 text-sm";

const KINDS: { value: SearchKind; label: string; icon: typeof Briefcase }[] = [
  { value: "jobs", label: "Jobs", icon: Briefcase },
  { value: "internships", label: "Internships", icon: GraduationCap },
];

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
  const [kind, setKind] = useState<SearchKind>("jobs");
  const [pay, setPay] = useState<PayStatus | "">("");
  const [sort, setSort] = useState<JobsListJobsSort>("score");
  const [fit, setFit] = useState<Recommendation | "">("");
  const [showFiltered, setShowFiltered] = useState(false);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [remote, setRemote] = useState<RemoteType | "">("");
  const [limit, setLimit] = useState(PAGE);
  const query = useDebounced(q);

  const shownRun = runId ?? active.data?.id ?? null;
  const internships = kind === "internships";
  const noun = internships ? "internships" : "jobs";
  const jobs = useJobsListJobs({
    kind,
    pay: (internships && pay) || undefined,
    sort,
    recommendation: fit || undefined,
    include_filtered: showFiltered || undefined,
    q: query || undefined,
    source: source || undefined,
    remote_type: remote || undefined,
    limit,
  });

  const findJobs = () =>
    start.mutate(
      { data: { kind } },
      {
        onSuccess: (run) => setRunId(run.id),
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409 && typeof e.problem.run_id === "string") {
            setRunId(e.problem.run_id);
            return;
          }
          toast.error(errorMessage(e));
        },
      },
    );

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
  const filtered = Boolean(q || source || remote || fit || (internships && pay));

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Jobs and internships from your sources, ranked by how well they fit your resume."
        actions={
          <Button onClick={findJobs} disabled={start.isPending || searching || Boolean(needsPrefs)}>
            <Search className="size-4" /> {searching ? "Searching…" : `Find ${noun}`}
          </Button>
        }
      />

      <div
        role="tablist"
        aria-label="What to look for"
        className="bg-muted mb-6 inline-flex rounded-lg p-1"
      >
        {KINDS.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={kind === value}
            onClick={() => {
              setKind(value);
              setPay("");
              setLimit(PAGE);
            }}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              kind === value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden /> {label}
          </button>
        ))}
      </div>

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
            {internships && (
              <select
                aria-label="Pay"
                className={selectClass}
                value={pay}
                onChange={(e) => {
                  setPay(e.target.value as PayStatus | "");
                  setLimit(PAGE);
                }}
              >
                <option value="">Paid or unpaid</option>
                <option value="paid">Paid only</option>
                <option value="unpaid">Unpaid only</option>
                <option value="unknown">Pay not stated</option>
              </select>
            )}
            <select
              aria-label="Fit"
              className={selectClass}
              value={fit}
              onChange={(e) => {
                setFit(e.target.value as Recommendation | "");
                setLimit(PAGE);
              }}
            >
              <option value="">Any fit</option>
              <option value="strong_apply">Strong matches</option>
              <option value="apply">Good matches</option>
              <option value="stretch">Stretches</option>
              <option value="skip">Weak matches</option>
            </select>
            <select
              aria-label="Sort"
              className={selectClass}
              value={sort}
              onChange={(e) => setSort(e.target.value as JobsListJobsSort)}
            >
              <option value="score">Best match</option>
              <option value="posted">Newest</option>
              <option value="discovered">Recently found</option>
            </select>
            {jobs.data && (
              <span className="text-muted-foreground self-center text-sm">
                {jobs.data.total} {noun}
                {jobs.data.filtered_out > 0 && (
                  <>
                    {" · "}
                    <button
                      type="button"
                      className="hover:text-foreground underline underline-offset-2"
                      onClick={() => setShowFiltered((v) => !v)}
                    >
                      {showFiltered
                        ? "hide filtered"
                        : `${jobs.data.filtered_out} hidden by your filters`}
                    </button>
                  </>
                )}
              </span>
            )}
          </div>

          {jobs.data && !jobs.data.has_resume && (
            <div className="bg-muted mb-4 rounded-md p-3 text-sm">
              Match scores need your resume.{" "}
              <Link href="/profile" className="font-medium underline underline-offset-2">
                Upload it on your Profile
              </Link>{" "}
              and your jobs will be ranked.
            </div>
          )}
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
              title={filtered ? `No ${noun} match these filters` : `No ${noun} yet`}
              description={
                filtered
                  ? "Try clearing a filter."
                  : `Click “Find ${noun}” to search your sources. It usually takes under a minute.`
              }
            />
          )}
        </>
      )}
    </>
  );
}
