"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { TagInput } from "@/components/common/tag-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  PreferencesIn,
  PreferencesOut,
  PreferredLocation,
  RemoteType,
  Seniority,
  SourceOut,
} from "@/lib/api/generated/model";
import {
  getPreferencesGetPreferencesQueryKey,
  usePreferencesGetPreferences,
  usePreferencesListSources,
  usePreferencesSavePreferences,
} from "@/lib/api/generated/preferences/preferences";
import { getUsersGetMeQueryKey } from "@/lib/api/generated/users/users";
import { COUNTRIES } from "@/lib/countries";
import { errorMessage } from "@/lib/forms";
import { cn } from "@/lib/utils";

const REMOTE_OPTIONS: { value: RemoteType; label: string }[] = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
];
const LEVELS: Seniority[] = [
  "intern",
  "junior",
  "mid",
  "senior",
  "staff",
  "principal",
  "manager",
  "director",
];
const selectClass = "border-input bg-background h-9 rounded-md border px-2 text-sm";

function toggle<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

/** The API rejects unknown fields, so drop the read-only `is_saved` flag. */
function fromOut(p: PreferencesOut): PreferencesIn {
  const rest: Partial<PreferencesOut> = { ...p };
  delete rest.is_saved;
  return rest;
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
    </div>
  );
}

function SourceToggle({
  source,
  checked,
  onToggle,
}: {
  source: SourceOut;
  checked: boolean;
  onToggle: () => void;
}) {
  const unavailable = source.requires_key && !source.configured;
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-lg border p-3",
        checked && "border-primary",
        unavailable && "opacity-70",
      )}
    >
      <input type="checkbox" className="mt-1 size-4" checked={checked} onChange={onToggle} />
      <div className="grid gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{source.label}</span>
          <Badge variant={source.kind === "scraper" ? "outline" : "secondary"}>
            {source.kind === "scraper" ? "Scraper" : "Free API"}
          </Badge>
          {unavailable && <Badge variant="outline">Needs API key</Badge>}
          {source.paused_seconds > 0 && (
            <Badge variant="destructive">Paused {Math.ceil(source.paused_seconds / 60)} min</Badge>
          )}
        </div>
        <p className="text-muted-foreground text-xs">{source.note}</p>
      </div>
    </label>
  );
}

function Editor({
  initial,
  sources,
  submitLabel,
  onSaved,
}: {
  initial: PreferencesIn;
  sources: SourceOut[];
  submitLabel: string;
  onSaved?: (prefs: PreferencesOut) => void;
}) {
  const queryClient = useQueryClient();
  const [prefs, setPrefs] = useState<PreferencesIn>(initial);
  const save = usePreferencesSavePreferences();
  const set = <K extends keyof PreferencesIn>(key: K, value: PreferencesIn[K]) =>
    setPrefs((p) => ({ ...p, [key]: value }));

  const locations = prefs.locations ?? [];
  const setLocation = (i: number, patch: Partial<PreferredLocation>) =>
    set(
      "locations",
      locations.map((loc, j) => (j === i ? { ...loc, ...patch } : loc)),
    );
  const scrapersOn = sources.filter((s) => s.kind === "scraper" && prefs.sources?.includes(s.name));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prefs.target_titles?.length) {
      toast.error("Add at least one job title to search for.");
      return;
    }
    if (!prefs.sources?.length) {
      toast.error("Turn on at least one job source.");
      return;
    }
    save.mutate(
      { data: { ...prefs, locations: locations.filter((l) => l.country) } },
      {
        onSuccess: (saved) => {
          queryClient.setQueryData(getPreferencesGetPreferencesQueryKey(), saved);
          queryClient.invalidateQueries({ queryKey: getUsersGetMeQueryKey() });
          toast.success("Preferences saved");
          onSaved?.(saved);
        },
        onError: (err) => toast.error(errorMessage(err)),
      },
    );
  };

  return (
    <form onSubmit={submit} className="grid gap-6" noValidate>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">What are you looking for?</CardTitle>
          <CardDescription>Each title is searched separately on every source.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <Field label="Job titles" htmlFor="titles" hint="Press Enter after each title. Up to 10.">
            <TagInput
              id="titles"
              value={prefs.target_titles ?? []}
              onChange={(v) => set("target_titles", v)}
              placeholder="e.g. Backend Engineer"
              max={10}
            />
          </Field>

          <Field label="Work arrangement">
            <div className="flex flex-wrap gap-4">
              {REMOTE_OPTIONS.map((o) => (
                <label key={o.value} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4"
                    checked={prefs.remote_types?.includes(o.value) ?? false}
                    onChange={() => set("remote_types", toggle(prefs.remote_types ?? [], o.value))}
                  />
                  {o.label}
                </label>
              ))}
            </div>
          </Field>

          <Field
            label="Locations"
            hint="Used for on-site and hybrid roles. Leave empty to search anywhere."
          >
            <div className="grid gap-2">
              {locations.map((loc, i) => (
                <div key={i} className="flex gap-2">
                  <Input
                    aria-label="City"
                    placeholder="City (optional)"
                    value={loc.city ?? ""}
                    onChange={(e) => setLocation(i, { city: e.target.value || null })}
                  />
                  <select
                    aria-label="Country"
                    className={selectClass}
                    value={loc.country}
                    onChange={(e) => setLocation(i, { country: e.target.value })}
                  >
                    {COUNTRIES.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Remove location"
                    onClick={() =>
                      set(
                        "locations",
                        locations.filter((_, j) => j !== i),
                      )
                    }
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              ))}
              {locations.length < 5 && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="justify-self-start"
                  onClick={() => set("locations", [...locations, { city: null, country: "us" }])}
                >
                  <Plus className="size-4" /> Add location
                </Button>
              )}
            </div>
          </Field>

          <Field label="Experience level" hint="Used for matching in the next phase.">
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {LEVELS.map((level) => (
                <label key={level} className="flex items-center gap-2 text-sm capitalize">
                  <input
                    type="checkbox"
                    className="size-4"
                    checked={prefs.experience_levels?.includes(level) ?? false}
                    onChange={() =>
                      set("experience_levels", toggle(prefs.experience_levels ?? [], level))
                    }
                  />
                  {level}
                </label>
              ))}
            </div>
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Minimum salary (optional)" htmlFor="salary">
              <div className="flex gap-2">
                <Input
                  id="salary"
                  type="number"
                  min={0}
                  placeholder="e.g. 60000"
                  value={prefs.salary_min ?? ""}
                  onChange={(e) =>
                    set("salary_min", e.target.value ? Number(e.target.value) : null)
                  }
                />
                <Input
                  aria-label="Currency"
                  className="w-20 uppercase"
                  maxLength={3}
                  value={prefs.salary_currency ?? "USD"}
                  onChange={(e) => set("salary_currency", e.target.value.toUpperCase())}
                />
              </div>
            </Field>
            <Field label="Posted within" htmlFor="posted">
              <select
                id="posted"
                className={selectClass}
                value={prefs.posted_within_days ?? 7}
                onChange={(e) => set("posted_within_days", Number(e.target.value))}
              >
                {[1, 3, 7, 14, 30].map((d) => (
                  <option key={d} value={d}>
                    {d === 1 ? "Last 24 hours" : `Last ${d} days`}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
          <CardDescription>Applied when ranking jobs (next phase).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <Field label="Must mention (any of)" htmlFor="include">
            <TagInput
              id="include"
              value={prefs.include_keywords ?? []}
              onChange={(v) => set("include_keywords", v)}
              placeholder="e.g. Python"
            />
          </Field>
          <Field label="Hide jobs mentioning" htmlFor="exclude">
            <TagInput
              id="exclude"
              value={prefs.exclude_keywords ?? []}
              onChange={(v) => set("exclude_keywords", v)}
              placeholder="e.g. clearance"
            />
          </Field>
          <Field label="Hide these companies" htmlFor="companies">
            <TagInput
              id="companies"
              value={prefs.exclude_companies ?? []}
              onChange={(v) => set("exclude_companies", v)}
              placeholder="e.g. Current employer"
              max={100}
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Job sources</CardTitle>
          <CardDescription>
            All free. API sources are reliable; scrapers cover more boards but can break. Free keys
            for Adzuna and Jooble go in <code>.env</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="grid gap-2 md:grid-cols-2">
            {sources.map((s) => (
              <SourceToggle
                key={s.name}
                source={s}
                checked={prefs.sources?.includes(s.name) ?? false}
                onToggle={() => set("sources", toggle(prefs.sources ?? [], s.name))}
              />
            ))}
          </div>
          {scrapersOn.length > 0 && (
            <div className="flex gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
              <p>
                Scraping ({scrapersOn.map((s) => s.label).join(", ")}) reads public listings without
                logging in. It may break without notice, and most job boards&apos; terms forbid it;
                you&apos;re responsible for complying with them.
              </p>
            </div>
          )}
          <Field label="Results per source" htmlFor="per-source">
            <select
              id="per-source"
              className={`${selectClass} w-32`}
              value={prefs.results_per_source ?? 30}
              onChange={(e) => set("results_per_source", Number(e.target.value))}
            >
              {[10, 20, 30, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </Field>
        </CardContent>
      </Card>

      <div className="bg-background/90 sticky bottom-0 -mx-4 flex justify-end border-t px-4 py-3 backdrop-blur md:-mx-8 md:px-8">
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}

export function PreferencesForm({
  submitLabel = "Save preferences",
  onSaved,
}: {
  submitLabel?: string;
  onSaved?: (prefs: PreferencesOut) => void;
}) {
  const prefs = usePreferencesGetPreferences();
  const sources = usePreferencesListSources();
  if (!prefs.data || !sources.data) return <Skeleton className="h-96 w-full rounded-xl" />;
  return (
    <Editor
      initial={fromOut(prefs.data)}
      sources={sources.data}
      submitLabel={submitLabel}
      onSaved={onSaved}
    />
  );
}
