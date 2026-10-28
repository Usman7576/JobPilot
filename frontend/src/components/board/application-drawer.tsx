"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BellRing, ClipboardCopy, ExternalLink, Loader2, Mail, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { COLUMNS } from "@/components/board/board";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getApplicationsGetApplicationQueryKey,
  getApplicationsGetBoardQueryKey,
  useApplicationsFollowUpDraft,
  useApplicationsFollowUpSent,
  useApplicationsGetApplication,
  useApplicationsMoveApplication,
} from "@/lib/api/generated/applications/applications";
import type { ApplicationOut, BoardCard } from "@/lib/api/generated/model";
import { timeAgo } from "@/lib/format";
import { errorMessage } from "@/lib/forms";

const STATUS_LABEL: Record<string, string> = {
  saved: "Saved",
  drafting: "Writing…",
  ready: "Ready to review",
  queued: "Queued",
  applied: "Applied",
  replied: "Replied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};
const FOLLOW_UP_WAIT_MS = 90_000;

function followUpText(app: ApplicationOut) {
  const c = (app.follow_up?.content ?? {}) as { body?: string; signature?: string };
  return [c.body, c.signature].filter(Boolean).join("\n\n");
}

export function ApplicationDrawer({
  card,
  onClose,
}: {
  card: BoardCard | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const id = card?.id ?? "";
  // While a follow-up is being written, poll until a new draft id shows up.
  const [waitingFor, setWaitingFor] = useState<{ since: number; prev: string | null } | null>(null);
  const app = useApplicationsGetApplication(id, {
    query: {
      enabled: Boolean(card),
      refetchInterval: (q) =>
        waitingFor && (q.state.data?.follow_up?.id ?? null) === waitingFor.prev ? 2500 : false,
    },
  });
  const writing = Boolean(waitingFor && (app.data?.follow_up?.id ?? null) === waitingFor.prev);
  useEffect(() => {
    if (!writing || !waitingFor) return;
    const t = setTimeout(
      () => {
        setWaitingFor(null);
        toast("Still writing. Check back in a minute.");
      },
      Math.max(0, FOLLOW_UP_WAIT_MS - (Date.now() - waitingFor.since)),
    );
    return () => clearTimeout(t);
  }, [writing, waitingFor]);

  const draft = useApplicationsFollowUpDraft();
  const sent = useApplicationsFollowUpSent();
  const move = useApplicationsMoveApplication();
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: getApplicationsGetBoardQueryKey() }),
      queryClient.invalidateQueries({ queryKey: getApplicationsGetApplicationQueryKey(id) }),
    ]);
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const data = app.data;
  const waitingForReply = data?.status === "applied";

  return (
    <Sheet open={Boolean(card)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{card?.job_title}</SheetTitle>
          <SheetDescription>{card?.company_name}</SheetDescription>
        </SheetHeader>

        {!data ? (
          <div className="grid gap-3 px-4">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <div className="grid gap-5 px-4 pb-6 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{STATUS_LABEL[data.status] ?? data.status}</Badge>
              {data.sent_at && (
                <span className="text-muted-foreground">applied {timeAgo(data.sent_at)}</span>
              )}
              {data.contact_email && (
                <span className="text-muted-foreground flex items-center gap-1">
                  <Mail className="size-3" aria-hidden /> {data.contact_email}
                </span>
              )}
            </div>

            <section className="grid gap-1.5" aria-label="Move to">
              <span className="text-muted-foreground text-xs font-medium">Move to</span>
              <div className="flex flex-wrap gap-1.5">
                {COLUMNS.map((c) => {
                  const here = card?.column === c.id;
                  return (
                    <Button
                      key={c.id}
                      size="sm"
                      variant={here ? "secondary" : "outline"}
                      aria-current={here ? "true" : undefined}
                      disabled={here || move.isPending}
                      onClick={() =>
                        move.mutate(
                          { applicationId: id, data: { column: c.id } },
                          {
                            onSuccess: () => {
                              toast(`Moved to ${c.label}`);
                              void refresh();
                            },
                            onError,
                          },
                        )
                      }
                    >
                      {c.label}
                    </Button>
                  );
                })}
              </div>
            </section>

            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <Link href={`/applications/${data.id}`}>Open application</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link href={`/jobs/${data.job_id}`}>
                  Job <ExternalLink className="size-3" />
                </Link>
              </Button>
            </div>

            {waitingForReply && (
              <>
                <Separator />
                <section className="grid gap-2">
                  <h3 className="flex items-center gap-1.5 font-medium">
                    <BellRing className="size-4" aria-hidden /> Follow-up
                  </h3>
                  <p className="text-muted-foreground">
                    {data.follow_up_at
                      ? `Reminder ${timeAgo(data.follow_up_at)}.`
                      : "No more reminders for this one."}{" "}
                    {data.follow_up_count > 0 && `${data.follow_up_count} sent so far.`}
                  </p>
                  {data.follow_up && !writing && (
                    <div className="bg-muted/50 grid gap-2 rounded-md p-3">
                      <p className="text-xs font-medium">
                        {(data.follow_up.content as { subject?: string }).subject}
                      </p>
                      <p className="whitespace-pre-wrap">{followUpText(data)}</p>
                      {data.follow_up.flags.length > 0 && (
                        <p className="text-amber-700 dark:text-amber-400">
                          {data.follow_up.flags.length} thing(s) to check: open the application.
                        </p>
                      )}
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(followUpText(data));
                              toast.success("Follow-up copied");
                            } catch {
                              toast.error("Couldn't copy. Select the text and copy it.");
                            }
                          }}
                        >
                          <ClipboardCopy className="size-4" /> Copy
                        </Button>
                        {data.contact_email && (
                          <Button asChild size="sm" variant="outline">
                            <a
                              href={`mailto:${data.contact_email}?subject=${encodeURIComponent(
                                String(
                                  (data.follow_up.content as { subject?: string }).subject ?? "",
                                ),
                              )}&body=${encodeURIComponent(followUpText(data))}`}
                            >
                              <Mail className="size-4" /> Open in email app
                            </a>
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant={data.follow_up ? "outline" : "default"}
                      disabled={writing || draft.isPending}
                      onClick={() =>
                        draft.mutate(
                          { applicationId: id, data: { tone: data.tone } },
                          {
                            onSuccess: () =>
                              setWaitingFor({
                                since: Date.now(),
                                prev: data.follow_up?.id ?? null,
                              }),
                            onError,
                          },
                        )
                      }
                    >
                      {writing ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Sparkles className="size-4" />
                      )}
                      {writing
                        ? "Writing…"
                        : data.follow_up
                          ? "Write another"
                          : "Write a follow-up"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={sent.isPending}
                      onClick={() =>
                        sent.mutate(
                          { applicationId: id },
                          {
                            onSuccess: () => {
                              toast.success("Follow-up logged");
                              void refresh();
                            },
                            onError,
                          },
                        )
                      }
                    >
                      I sent a follow-up
                    </Button>
                  </div>
                </section>
              </>
            )}

            {data.status !== "withdrawn" && data.status !== "rejected" && (
              <Button
                size="sm"
                variant="ghost"
                className="text-muted-foreground justify-self-start"
                disabled={move.isPending}
                onClick={() =>
                  move.mutate(
                    { applicationId: id, data: { column: "rejected", withdrawn: true } },
                    {
                      onSuccess: () => {
                        toast("Marked as withdrawn");
                        void refresh();
                      },
                      onError,
                    },
                  )
                }
              >
                I withdrew from this one
              </Button>
            )}

            {data.notes && (
              <>
                <Separator />
                <section className="grid gap-1">
                  <h3 className="font-medium">Notes</h3>
                  <p className="text-muted-foreground whitespace-pre-wrap">{data.notes}</p>
                </section>
              </>
            )}

            <Separator />
            <section className="grid gap-2">
              <h3 className="font-medium">Timeline</h3>
              <ol className="border-muted grid gap-2 border-l pl-3">
                {data.events.map((e, i) => (
                  <li key={i} className="grid">
                    <span>
                      {STATUS_LABEL[e.to_status] ?? e.to_status}
                      {e.from_status && e.from_status !== e.to_status && (
                        <span className="text-muted-foreground">
                          {" "}
                          (from {STATUS_LABEL[e.from_status] ?? e.from_status})
                        </span>
                      )}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {timeAgo(e.created_at)}
                      {e.reason ? ` · ${e.reason}` : ""}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
