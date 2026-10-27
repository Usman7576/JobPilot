"use client";

import { AlertTriangle, Check, EyeOff, Loader2, RefreshCw, Sparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { MatchDetail, MatchSummary, Recommendation } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

export const RECOMMENDATION: Record<Recommendation, { label: string; tone: string }> = {
  strong_apply: {
    label: "Strong match",
    tone: "text-emerald-700 dark:text-emerald-400 border-emerald-600/40 bg-emerald-500/10",
  },
  apply: {
    label: "Good match",
    tone: "text-sky-700 dark:text-sky-400 border-sky-600/40 bg-sky-500/10",
  },
  stretch: {
    label: "Stretch",
    tone: "text-amber-700 dark:text-amber-400 border-amber-600/40 bg-amber-500/10",
  },
  skip: { label: "Weak match", tone: "text-muted-foreground border-border bg-muted" },
};

export const FILTER_LABELS: Record<string, string> = {
  excluded_company: "A company you excluded",
  excluded_keyword: "Contains a keyword you excluded",
  missing_include_keyword: "Missing your must-have keywords",
  remote_mismatch: "A work arrangement you didn't pick",
  location_mismatch: "Outside your locations",
  seniority_gap: "Far more senior than your experience",
  salary_below_floor: "Pays below your minimum",
  stale: "Posted too long ago",
};

const BREAKDOWN: { key: string; label: string }[] = [
  { key: "skills_match", label: "Skills" },
  { key: "experience_match", label: "Experience" },
  { key: "seniority_fit", label: "Seniority" },
  { key: "domain_relevance", label: "Domain" },
  { key: "location_fit", label: "Location" },
];

const percent = (similarity: number | null) =>
  similarity == null ? null : `${Math.round(Math.max(0, similarity) * 100)}%`;

/** Compact score for job cards: the number when scored, else how it ranked without AI. */
export function ScoreBadge({ match }: { match: MatchSummary | null }) {
  if (!match) return null;
  if (!match.hard_filter_passed) {
    return (
      <Badge variant="outline" className="text-muted-foreground gap-1">
        <EyeOff className="size-3" aria-hidden /> Filtered
      </Badge>
    );
  }
  if (match.overall_score == null || !match.recommendation) {
    const sim = percent(match.similarity);
    return (
      <Badge
        variant="outline"
        className="text-muted-foreground"
        title="Ranked by resume similarity; not scored by the AI yet"
      >
        Not scored{sim ? ` · ${sim} similar` : ""}
      </Badge>
    );
  }
  const rec = RECOMMENDATION[match.recommendation];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        rec.tone,
      )}
      title="Match score: how well this job fits your resume"
    >
      <span className="tabular-nums font-semibold">{match.overall_score}</span>
      {rec.label}
    </span>
  );
}

export function MatchPanel({
  match,
  hasResume,
  rescoring,
  onRescore,
}: {
  match: MatchDetail | null;
  hasResume: boolean;
  rescoring: boolean;
  onRescore: () => void;
}) {
  const rescore = (
    <Button variant="outline" size="sm" onClick={onRescore} disabled={rescoring || !hasResume}>
      {rescoring ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
      {rescoring ? "Scoring…" : match?.overall_score != null ? "Rescore" : "Score now"}
    </Button>
  );

  if (!hasResume) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Match</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Upload your resume on the Profile page to see how well this job fits you.
        </CardContent>
      </Card>
    );
  }

  const scored = match?.overall_score != null && match.recommendation;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4" aria-hidden /> Match
        </CardTitle>
        {rescore}
      </CardHeader>
      <CardContent className="grid gap-5">
        {match && !match.hard_filter_passed && (
          <div className="bg-muted rounded-md p-3 text-sm">
            <p className="font-medium">Hidden from your feed</p>
            <ul className="text-muted-foreground mt-1 list-inside list-disc">
              {match.hard_filter_reasons.map((r) => (
                <li key={r}>{FILTER_LABELS[r] ?? r}</li>
              ))}
            </ul>
          </div>
        )}

        {scored ? (
          <>
            <div className="flex items-center gap-4">
              <div
                className={cn(
                  "grid size-16 shrink-0 place-items-center rounded-full border-2 text-2xl font-semibold tabular-nums",
                  RECOMMENDATION[match.recommendation!].tone,
                )}
              >
                {match.overall_score}
              </div>
              <div className="grid gap-1">
                <span className="font-medium">{RECOMMENDATION[match.recommendation!].label}</span>
                {match.why_good_fit && (
                  <p className="text-muted-foreground text-sm">{match.why_good_fit}</p>
                )}
              </div>
            </div>

            {match.breakdown && (
              <div className="grid gap-2.5">
                {BREAKDOWN.map(({ key, label }) => {
                  const value = match.breakdown?.[key] ?? 0;
                  return (
                    <div
                      key={key}
                      className="grid grid-cols-[5.5rem_1fr_2rem] items-center gap-2 text-sm"
                    >
                      <span className="text-muted-foreground">{label}</span>
                      <Progress value={value} aria-label={`${label} ${value} of 100`} />
                      <span className="text-right tabular-nums">{value}</span>
                    </div>
                  );
                })}
              </div>
            )}

            {(match.matched_skills.length > 0 || match.missing_skills.length > 0) && (
              <div className="grid gap-2">
                <div className="flex flex-wrap gap-1.5">
                  {match.matched_skills.map((s) => (
                    <Badge key={s} variant="outline" className="gap-1 border-emerald-600/40">
                      <Check className="size-3 text-emerald-600" aria-hidden /> {s}
                    </Badge>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {match.missing_skills.map((s) => (
                    <Badge key={s} variant="outline" className="text-muted-foreground gap-1">
                      <X className="size-3" aria-hidden /> {s}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {match.red_flags.length > 0 && (
              <ul className="grid gap-1.5 text-sm">
                {match.red_flags.map((f) => (
                  <li key={f.code} className="flex items-start gap-2">
                    <AlertTriangle
                      className={cn(
                        "mt-0.5 size-4 shrink-0",
                        f.severity === "high"
                          ? "text-destructive"
                          : f.severity === "medium"
                            ? "text-amber-600"
                            : "text-muted-foreground",
                      )}
                      aria-label={`${f.severity} concern`}
                    />
                    {f.message}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="text-muted-foreground text-sm">
            {match?.failure_reason ??
              (match
                ? `Not scored by the AI yet${
                    percent(match.similarity)
                      ? ` (${percent(match.similarity)} similar to your resume)`
                      : ""
                  }. Only your best matches are scored automatically.`
                : "Not ranked yet. It will be on your next search.")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
