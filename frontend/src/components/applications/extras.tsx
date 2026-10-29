"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ClipboardCopy,
  Lightbulb,
  ListChecks,
  Loader2,
  MessagesSquare,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getApplicationsGetApplicationQueryKey,
  useApplicationsInterviewPrep,
} from "@/lib/api/generated/applications/applications";
import type { ApplicationOut } from "@/lib/api/generated/model";
import { useUsersGetAnswers } from "@/lib/api/generated/users/users";
import { timeAgo } from "@/lib/format";
import { errorMessage } from "@/lib/forms";

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${what} copied`);
  } catch {
    toast.error("Couldn't copy. Select the text and copy it yourself.");
  }
}

/** "You emailed this company N days ago": shown before sending so you don't double up. */
export function CompanyHistoryNote({ app }: { app: ApplicationOut }) {
  const history = app.company_history ?? [];
  if (!history.length) return null;
  const [latest, ...rest] = history;
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-sm">
      <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
      <p>
        You already applied to {app.company_name} {timeAgo(latest.sent_at)} (
        <Link href={`/applications/${latest.id}`} className="underline">
          {latest.job_title}
        </Link>
        ){rest.length ? ` and ${rest.length} more time${rest.length > 1 ? "s" : ""}` : ""} this
        month. A second email to the same team can look like spam; consider waiting or mentioning
        the earlier one.
      </p>
    </div>
  );
}

/** Saved answers to common form questions, with copy buttons (apply-on-site checklist). */
export function SiteAnswers() {
  const answers = useUsersGetAnswers();
  const items = (answers.data?.items ?? []).filter((a) => a.answer.trim());
  if (!answers.data) return null;
  if (!items.length) {
    return (
      <p className="text-muted-foreground text-xs">
        Tip: save answers to common form questions (notice period, salary, work permit) in{" "}
        <Link href="/settings" className="underline">
          Settings → Answer bank
        </Link>{" "}
        to copy them here.
      </p>
    );
  }
  return (
    <div className="grid gap-2">
      <p className="flex items-center gap-1.5 font-medium">
        <ListChecks className="size-4" aria-hidden /> Your answers
      </p>
      <ul className="grid gap-1.5">
        {items.map((a) => (
          <li
            key={a.question}
            className="flex items-start justify-between gap-2 rounded-md border p-2"
          >
            <div className="grid min-w-0 gap-0.5">
              <span className="text-muted-foreground text-xs">{a.question}</span>
              <span className="line-clamp-3 break-words">{a.answer}</span>
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="shrink-0"
              aria-label={`Copy answer: ${a.question}`}
              onClick={() => copy(a.answer, "Answer")}
            >
              <ClipboardCopy className="size-4" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface PrepContent {
  questions?: { question: string; why: string; your_angle: string }[];
  focus_topics?: string[];
  to_ask?: string[];
}

const WAIT_MS = 120_000;

/** Likely interview questions with what to talk about, topics to revise and questions to ask. */
export function InterviewPrepCard({ app }: { app: ApplicationOut }) {
  const queryClient = useQueryClient();
  const request = useApplicationsInterviewPrep();
  const [waiting, setWaiting] = useState<{ prev: string | null; since: number } | null>(null);
  const key = getApplicationsGetApplicationQueryKey(app.id);
  const current = app.interview_prep?.id ?? null;
  const writing = Boolean(waiting && waiting.prev === current && !app.last_error);

  useEffect(() => {
    if (!writing || !waiting) return;
    const poll = setInterval(() => void queryClient.invalidateQueries({ queryKey: key }), 3000);
    const stop = setTimeout(
      () => setWaiting(null),
      Math.max(0, WAIT_MS - (Date.now() - waiting.since)),
    );
    return () => {
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [writing, waiting, queryClient, key]);

  const start = () =>
    request.mutate(
      { applicationId: app.id },
      {
        onSuccess: () => setWaiting({ prev: current, since: Date.now() }),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );

  const prep = (app.interview_prep?.content ?? {}) as PrepContent;
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div className="grid gap-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <MessagesSquare className="size-4" aria-hidden /> Interview prep
          </CardTitle>
          <CardDescription>
            Likely questions from the job post, what you could say from your resume, and questions
            to ask them.
          </CardDescription>
        </div>
        <Button
          size="sm"
          variant={app.interview_prep ? "outline" : "default"}
          disabled={writing || request.isPending}
          onClick={start}
        >
          {writing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : app.interview_prep ? (
            <RefreshCw className="size-4" />
          ) : (
            <Lightbulb className="size-4" />
          )}
          {writing ? "Preparing…" : app.interview_prep ? "Write again" : "Prepare me"}
        </Button>
      </CardHeader>
      {app.interview_prep && !writing && (
        <CardContent className="grid gap-5 text-sm">
          <ol className="grid gap-3">
            {(prep.questions ?? []).map((q, i) => (
              <li key={i} className="grid gap-1 rounded-lg border p-3">
                <p className="font-medium">
                  {i + 1}. {q.question}
                </p>
                {q.why && <p className="text-muted-foreground text-xs">Why they ask: {q.why}</p>}
                {q.your_angle && (
                  <p>
                    <span className="font-medium">Your angle: </span>
                    {q.your_angle}
                  </p>
                )}
              </li>
            ))}
          </ol>
          {!!prep.focus_topics?.length && (
            <div className="grid gap-1.5">
              <p className="font-medium">Revise before the interview</p>
              <ul className="flex flex-wrap gap-1.5">
                {prep.focus_topics.map((t) => (
                  <li key={t} className="bg-muted rounded-md px-2 py-0.5 text-xs">
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {!!prep.to_ask?.length && (
            <div className="grid gap-1.5">
              <p className="font-medium">Questions to ask them</p>
              <ul className="list-inside list-disc space-y-1">
                {prep.to_ask.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-muted-foreground text-xs">
            Written {timeAgo(app.interview_prep.created_at)} from your resume. Check every angle
            before you use it.
          </p>
        </CardContent>
      )}
    </Card>
  );
}
