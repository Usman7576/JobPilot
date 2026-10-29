"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Inbox,
  Loader2,
  Paperclip,
  PencilLine,
  Send,
  ShieldCheck,
  SkipForward,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CompanyHistoryNote } from "@/components/applications/extras";
import { emailSubject, emailText } from "@/components/applications/send-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  applicationsCancelSend,
  applicationsSendApplication,
  getApplicationsReviewQueueQueryKey,
  getApplicationsSendQuotaQueryKey,
  useApplicationsAcknowledgeFlags,
  useApplicationsReviewQueue,
  useApplicationsSendQuota,
} from "@/lib/api/generated/applications/applications";
import { useIntegrationsListIntegrations } from "@/lib/api/generated/integrations/integrations";
import type { ApplicationOut } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/forms";
import { cn } from "@/lib/utils";

/**
 * Prepared emails, one at a time: Approve queues it to send (same rules as the preview
 * dialog: daily limit, 30–120 s delay, cancellable), Skip leaves it as a draft.
 */
export function ReviewQueue() {
  const queryClient = useQueryClient();
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [sending, setSending] = useState(false);
  // One idempotency key per application, so a double press can't send twice.
  const keys = useRef(new Map<string, string>());

  const queue = useApplicationsReviewQueue({
    query: { refetchInterval: (q) => ((q.state.data?.writing ?? 0) > 0 ? 4000 : false) },
  });
  const quota = useApplicationsSendQuota();
  const integrations = useIntegrationsListIntegrations();
  const acknowledge = useApplicationsAcknowledgeFlags();

  const items = (queue.data?.items ?? []).filter((a) => !skipped.has(a.id));
  const current = items[0];
  const testMode = integrations.data?.send_backend === "smtp";
  const gmail = integrations.data?.gmail;
  const canSend = testMode || gmail?.status === "connected";
  const locked = Boolean(current?.flags_blocked && !current.flags_acknowledged);
  const noneLeft = (quota.data?.remaining ?? 1) <= 0;

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: getApplicationsReviewQueueQueryKey() });
    void queryClient.invalidateQueries({ queryKey: getApplicationsSendQuotaQueryKey() });
  };

  const approve = async (app: ApplicationOut) => {
    if (sending || locked || !canSend || noneLeft) return;
    setSending(true);
    let key = keys.current.get(app.id);
    if (!key) {
      key = crypto.randomUUID();
      keys.current.set(app.id, key);
    }
    try {
      await applicationsSendApplication(
        app.id,
        { preview_confirmed: true },
        { headers: { "Idempotency-Key": key } },
      );
      toast.success(`Sending to ${app.company_name} in about a minute.`, {
        action: {
          label: "Undo",
          onClick: () =>
            applicationsCancelSend(app.id)
              .then(() => {
                keys.current.delete(app.id);
                toast("Cancelled. It's back in the queue.");
                refresh();
              })
              .catch((e) => toast.error(errorMessage(e))),
        },
      });
      refresh();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSending(false);
    }
  };

  const skip = (app: ApplicationOut) => setSkipped((s) => new Set(s).add(app.id));

  // Keyboard: A approve, S skip (not while typing somewhere).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (!current || e.metaKey || e.ctrlKey || e.altKey) return;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) {
        return;
      }
      if (e.key === "a" || e.key === "A") void approve(current);
      if (e.key === "s" || e.key === "S") skip(current);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (queue.isPending) return <Skeleton className="h-96 w-full rounded-xl" />;

  const writing = queue.data?.writing ?? 0;
  return (
    <div className="grid gap-4">
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span>
          {items.length} to review{skipped.size ? ` · ${skipped.size} skipped` : ""}
        </span>
        {writing > 0 && (
          <span className="flex items-center gap-1.5">
            <Loader2 className="size-3.5 animate-spin" /> {writing} still being written
          </span>
        )}
        {quota.data && (
          <span>
            {quota.data.remaining} of {quota.data.cap} sends left today
            {quota.data.queued ? ` · ${quota.data.queued} sending soon` : ""}
          </span>
        )}
        {skipped.size > 0 && (
          <button
            type="button"
            className="hover:text-foreground underline underline-offset-2"
            onClick={() => setSkipped(new Set())}
          >
            Show skipped again
          </button>
        )}
      </div>

      {testMode && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm">
          Test mode: approved emails go to the local test inbox (Mailpit), not to the real address.
        </p>
      )}
      {integrations.data && !canSend && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm">
          <Link href="/settings" className="font-medium underline">
            Connect Gmail
          </Link>{" "}
          to send{gmail?.status === "needs_reauth" ? " (it needs reconnecting)" : ""}. You can still
          review and edit.
        </p>
      )}

      {!current ? (
        <EmptyState
          icon={writing > 0 ? Loader2 : Inbox}
          title={writing > 0 ? "Writing your emails…" : "Nothing to review"}
          description={
            writing > 0
              ? "They appear here as soon as each one is written and fact-checked."
              : "On the Jobs page, tick “Has email”, select jobs and click Prepare."
          }
          action={
            writing > 0 ? undefined : (
              <Button asChild variant="outline">
                <Link href="/jobs">Go to Jobs</Link>
              </Button>
            )
          }
        />
      ) : (
        <ReviewCard
          key={current.id}
          app={current}
          from={testMode ? "Test mode (Mailpit)" : (gmail?.google_email ?? "Gmail not connected")}
          locked={locked}
          busy={sending}
          sendDisabled={!canSend || noneLeft}
          sendHint={noneLeft ? "Today's send limit is reached." : undefined}
          onApprove={() => approve(current)}
          onSkip={() => skip(current)}
          onConfirmFlags={() =>
            acknowledge.mutate(
              { applicationId: current.id },
              { onSuccess: refresh, onError: (e) => toast.error(errorMessage(e)) },
            )
          }
        />
      )}
    </div>
  );
}

function ReviewCard({
  app,
  from,
  locked,
  busy,
  sendDisabled,
  sendHint,
  onApprove,
  onSkip,
  onConfirmFlags,
}: {
  app: ApplicationOut;
  from: string;
  locked: boolean;
  busy: boolean;
  sendDisabled: boolean;
  sendHint?: string;
  onApprove: () => void;
  onSkip: () => void;
  onConfirmFlags: () => void;
}) {
  const flags = app.email?.flags ?? [];
  const clean = flags.length === 0 && app.email?.verified;
  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="grid gap-0.5">
            <CardTitle className="text-lg">{app.job_title}</CardTitle>
            <p className="text-muted-foreground text-sm">{app.company_name}</p>
          </div>
          {clean ? (
            <Badge className="gap-1 bg-emerald-600 text-white hover:bg-emerald-600">
              <ShieldCheck className="size-3.5" /> Every claim checked
            </Badge>
          ) : flags.length ? (
            <Badge
              variant="outline"
              className="gap-1 border-amber-500 text-amber-700 dark:text-amber-400"
            >
              <TriangleAlert className="size-3.5" /> {flags.length} to check
            </Badge>
          ) : (
            <Badge variant="outline">Fact-check pending</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        <dl className="grid grid-cols-[5rem_1fr] gap-x-3 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">From</dt>
          <dd className="break-all">{from}</dd>
          <dt className="text-muted-foreground">To</dt>
          <dd className="font-medium break-all">{app.contact_email}</dd>
          <dt className="text-muted-foreground">Subject</dt>
          <dd className="font-medium">{emailSubject(app)}</dd>
          <dt className="text-muted-foreground">Attached</dt>
          <dd className="flex items-center gap-1">
            {app.resume_file_name ? (
              <>
                <Paperclip className="size-3.5" aria-hidden /> {app.resume_file_name}
              </>
            ) : (
              "Nothing"
            )}
          </dd>
        </dl>

        <CompanyHistoryNote app={app} />

        <div className="bg-muted max-h-[50vh] overflow-y-auto rounded-md p-4 text-sm leading-relaxed whitespace-pre-wrap">
          {emailText(app)}
        </div>

        {flags.length > 0 && (
          <ul className="grid gap-1.5 text-sm">
            {flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2">
                <TriangleAlert
                  className={cn(
                    "mt-0.5 size-4 shrink-0",
                    f.severity === "block" ? "text-destructive" : "text-amber-500",
                  )}
                />
                <span>
                  <strong className="font-medium">{f.text}</strong>
                  <span className="text-muted-foreground"> · {f.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
        {locked && (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm">
            <span className="flex-1">
              Some claims aren&apos;t on your resume. Edit the email, or confirm they&apos;re
              accurate.
            </span>
            <Button size="sm" variant="outline" onClick={onConfirmFlags}>
              <CheckCircle2 className="size-4" /> They&apos;re accurate
            </Button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onApprove} disabled={busy || locked || sendDisabled}>
            <Send className="size-4" /> {busy ? "Scheduling…" : "Approve & send"}
            <kbd className="ml-1 rounded border px-1 text-[10px] opacity-70">A</kbd>
          </Button>
          <Button variant="outline" onClick={onSkip} disabled={busy}>
            <SkipForward className="size-4" /> Skip
            <kbd className="ml-1 rounded border px-1 text-[10px] opacity-70">S</kbd>
          </Button>
          <Button asChild variant="ghost">
            <Link href={`/applications/${app.id}`}>
              <PencilLine className="size-4" /> Edit
            </Link>
          </Button>
          {sendHint && <span className="text-muted-foreground text-sm">{sendHint}</span>}
        </div>
        <p className="text-muted-foreground text-xs">
          Approved emails wait 30–120 seconds before going out; you can undo from the message that
          appears.
        </p>
      </CardContent>
    </Card>
  );
}
