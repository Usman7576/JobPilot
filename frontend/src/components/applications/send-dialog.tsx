"use client";

import { Paperclip, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { CompanyHistoryNote } from "@/components/applications/extras";
import { Button } from "@/components/ui/button";
import {
  applicationsSendApplication,
  useApplicationsSendQuota,
} from "@/lib/api/generated/applications/applications";
import type { ApplicationOut } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/forms";

export function emailSubject(app: ApplicationOut) {
  return String((app.email?.content as { subject?: string } | undefined)?.subject ?? "");
}

export function emailText(app: ApplicationOut) {
  const c = (app.email?.content ?? {}) as { body?: string; signature?: string };
  return [c.body, c.signature]
    .map((s) => s?.trim())
    .filter(Boolean)
    .join("\n\n");
}

/**
 * The final preview before an application email goes out. Sending needs this dialog: it is
 * the only place that sets `preview_confirmed`, and each opening gets a fresh idempotency key
 * so a double click can't send twice.
 */
export function SendDialog({
  app,
  from,
  testMode,
  disabled,
  onQueued,
}: {
  app: ApplicationOut;
  from: string;
  testMode: boolean;
  disabled?: boolean;
  onQueued: (app: ApplicationOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [checked, setChecked] = useState(false);
  const [sending, setSending] = useState(false);
  const quota = useApplicationsSendQuota({ query: { enabled: open } });
  const left = quota.data?.remaining;

  const confirm = async () => {
    setSending(true);
    try {
      const data = await applicationsSendApplication(
        app.id,
        { preview_confirmed: true },
        { headers: { "Idempotency-Key": key } },
      );
      onQueued(data);
      setOpen(false);
      toast.success("Scheduled. It goes in about a minute; you can still cancel.");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setKey(crypto.randomUUID());
          setChecked(false);
        }
      }}
    >
      <AlertDialogTrigger asChild>
        <Button className="justify-start" disabled={disabled}>
          <Send className="size-4" /> Send via Gmail
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <AlertDialogHeader>
          <AlertDialogTitle>Check the email before it goes</AlertDialogTitle>
          <AlertDialogDescription>
            This is exactly what will be sent. It waits 30–120 seconds first, and you can cancel it
            until then.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {testMode && (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm">
            Test mode: this goes to the local test inbox (Mailpit), not to the real address.
          </p>
        )}

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
                <Paperclip className="size-3.5" aria-hidden /> Your resume ({app.resume_file_name})
              </>
            ) : (
              "Nothing"
            )}
          </dd>
        </dl>
        <CompanyHistoryNote app={app} />
        <div className="bg-muted max-h-72 overflow-y-auto rounded-md p-3 text-sm whitespace-pre-wrap">
          {emailText(app)}
        </div>

        {app.flags_acknowledged && (
          <p className="text-muted-foreground text-xs">
            You confirmed the flagged claims are accurate.
          </p>
        )}
        {left !== undefined && (
          <p className="text-muted-foreground text-xs">
            {left > 0
              ? `${left} of your ${quota.data?.cap} emails left today.`
              : `You've reached today's limit of ${quota.data?.cap} emails.`}
          </p>
        )}
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
          />
          I&apos;ve read this email, the address is right, and I want to send it.
        </label>

        <AlertDialogFooter>
          <AlertDialogCancel>Not yet</AlertDialogCancel>
          <Button disabled={!checked || sending || left === 0} onClick={confirm}>
            <Send className="size-4" /> {sending ? "Scheduling…" : "Send"}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
