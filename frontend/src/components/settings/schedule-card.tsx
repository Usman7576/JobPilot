"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { PreferencesOut, SearchKind } from "@/lib/api/generated/model";
import {
  getPreferencesGetPreferencesQueryKey,
  usePreferencesGetPreferences,
  usePreferencesSavePreferences,
} from "@/lib/api/generated/preferences/preferences";
import { useUsersGetMe } from "@/lib/api/generated/users/users";
import { errorMessage } from "@/lib/forms";
import { useHydrated } from "@/lib/use-hydrated";

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const SCORES = [65, 70, 80, 90];
const selectClass = "border-input bg-background h-9 rounded-md border px-2 text-sm";

function hourLabel(h: number) {
  return new Date(2026, 0, 1, h).toLocaleTimeString(undefined, { hour: "numeric" });
}

type Schedule = {
  daily_search_enabled: boolean;
  daily_search_hour: number;
  daily_search_kinds: SearchKind[];
  digest_enabled: boolean;
  digest_min_score: number;
};

function pick(p: PreferencesOut): Schedule {
  return {
    daily_search_enabled: p.daily_search_enabled ?? false,
    daily_search_hour: p.daily_search_hour ?? 8,
    daily_search_kinds: p.daily_search_kinds ?? ["jobs"],
    digest_enabled: p.digest_enabled ?? true,
    digest_min_score: p.digest_min_score ?? 80,
  };
}

export function ScheduleCard() {
  const queryClient = useQueryClient();
  const prefs = usePreferencesGetPreferences();
  const me = useUsersGetMe();
  // The user is cached by the app shell: show it only after hydration (see useHydrated).
  const user = useHydrated() ? me.data : undefined;
  const save = usePreferencesSavePreferences();
  // Local edits; null means "showing what's saved".
  const [draft, setDraft] = useState<Schedule | null>(null);

  if (!prefs.data) return <Skeleton className="h-48 w-full rounded-xl" />;
  const saved = pick(prefs.data);
  const value = draft ?? saved;
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(saved);
  const set = (patch: Partial<Schedule>) => setDraft({ ...value, ...patch });
  const toggleKind = (kind: SearchKind, on: boolean) => {
    const kinds = on
      ? [...new Set([...value.daily_search_kinds, kind])]
      : value.daily_search_kinds.filter((k) => k !== kind);
    if (kinds.length) set({ daily_search_kinds: kinds });
  };

  const onSave = () => {
    // The saved preferences as input: everything except the read-only is_saved flag.
    const rest = Object.fromEntries(
      Object.entries(prefs.data!).filter(([key]) => key !== "is_saved"),
    ) as Omit<PreferencesOut, "is_saved">;
    save.mutate(
      { data: { ...rest, ...value } },
      {
        onSuccess: (data) => {
          queryClient.setQueryData(getPreferencesGetPreferencesQueryKey(), data);
          setDraft(null);
          toast.success("Schedule saved");
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock className="size-4" aria-hidden /> Daily search and email
        </CardTitle>
        <CardDescription>
          Search your sources automatically once a day, then email you the strong new matches.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {!prefs.data.is_saved && (
          <p className="text-muted-foreground">Save your job preferences below first.</p>
        )}
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            className="size-4"
            checked={value.daily_search_enabled}
            onChange={(e) => set({ daily_search_enabled: e.target.checked })}
          />
          Search every day
        </label>

        <div className="grid gap-3 pl-6 sm:grid-cols-2">
          <label className="grid gap-1">
            <span className="text-muted-foreground text-xs">
              At ({user?.timezone ?? "your time zone"})
            </span>
            <select
              className={selectClass}
              disabled={!value.daily_search_enabled}
              value={value.daily_search_hour}
              onChange={(e) => set({ daily_search_hour: Number(e.target.value) })}
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {hourLabel(h)}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="grid gap-1" disabled={!value.daily_search_enabled}>
            <legend className="text-muted-foreground text-xs">Look for</legend>
            <div className="flex gap-4 pt-1.5">
              {(["jobs", "internships"] as const).map((kind) => (
                <label key={kind} className="flex items-center gap-2 capitalize">
                  <input
                    type="checkbox"
                    className="size-4"
                    checked={value.daily_search_kinds.includes(kind)}
                    onChange={(e) => toggleKind(kind, e.target.checked)}
                  />
                  {kind}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            className="size-4"
            checked={value.digest_enabled}
            onChange={(e) => set({ digest_enabled: e.target.checked })}
          />
          Email me new strong matches after the daily search
        </label>
        <label className="grid max-w-56 gap-1 pl-6">
          <span className="text-muted-foreground text-xs">Only jobs scoring at least</span>
          <select
            className={selectClass}
            disabled={!value.digest_enabled}
            value={value.digest_min_score}
            onChange={(e) => set({ digest_min_score: Number(e.target.value) })}
          >
            {SCORES.map((s) => (
              <option key={s} value={s}>
                {s}
                {s === 80 ? " (strong matches)" : s === 65 ? " (good and up)" : ""}
              </option>
            ))}
          </select>
        </label>
        <p className="text-muted-foreground text-xs">
          The daily search needs the scheduler running (the &ldquo;beat&rdquo; process). Emails go
          to {user?.email ?? "your account email"}; in local testing they land in Mailpit.
        </p>

        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={onSave}
            disabled={!dirty || save.isPending || !prefs.data.is_saved}
          >
            {save.isPending ? "Saving…" : "Save"}
          </Button>
          {dirty && (
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              Discard
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
