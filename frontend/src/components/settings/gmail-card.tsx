"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getIntegrationsListIntegrationsQueryKey,
  integrationsConnect,
  useIntegrationsCheckRepliesNow,
  useIntegrationsDisconnect,
  useIntegrationsListIntegrations,
  useIntegrationsSetReplyDetection,
} from "@/lib/api/generated/integrations/integrations";
import type { IntegrationOut } from "@/lib/api/generated/model";
import { timeAgo } from "@/lib/format";
import { errorMessage } from "@/lib/forms";

const RESULT: Record<string, [ok: boolean, message: string]> = {
  connected: [true, "Gmail connected."],
  cancelled: [false, "Gmail wasn't connected (you cancelled)."],
  expired: [false, "That took too long. Try connecting again."],
  missing_permission: [false, "Allow “Send email on your behalf” to connect Gmail."],
  failed: [false, "Couldn't connect Gmail. Try again."],
};

/** Shows the result of Google's redirect back (?gmail=...) once, then cleans the URL. */
function useConnectResult() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const result = params.get("gmail");
  useEffect(() => {
    if (!result) return;
    const [ok, message] = RESULT[result] ?? RESULT.failed;
    if (ok) toast.success(message);
    else toast.error(message);
    router.replace(pathname);
  }, [result, router, pathname]);
}

export function GmailCard() {
  useConnectResult();
  const queryClient = useQueryClient();
  const integrations = useIntegrationsListIntegrations();
  const disconnect = useIntegrationsDisconnect();
  const [connecting, setConnecting] = useState(false);

  const connect = async (read = false) => {
    setConnecting(true);
    try {
      const { url } = await integrationsConnect("gmail", read ? { read: true } : undefined);
      window.location.assign(url);
    } catch (e) {
      toast.error(errorMessage(e));
      setConnecting(false);
    }
  };

  const data = integrations.data;
  const gmail = data?.gmail;
  const connected = gmail?.status === "connected";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Mail className="size-4" aria-hidden /> Gmail
          {gmail && (
            <Badge variant={connected ? "default" : "outline"}>
              {connected
                ? "Connected"
                : gmail.status === "needs_reauth"
                  ? "Reconnect needed"
                  : "Not connected"}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Lets JobPilot send application emails from your own address, only after you check each one
          in the final preview and click Send. Reading mail is a separate, optional permission for
          reply detection.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {!data ? (
          <Skeleton className="h-9 w-40" />
        ) : !data.google_configured ? (
          <p className="text-muted-foreground">
            Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env to enable this.
          </p>
        ) : connected ? (
          <div className="flex flex-wrap items-center gap-3">
            <span>
              Sending as <strong>{gmail.google_email}</strong>
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={disconnect.isPending}
              onClick={() =>
                disconnect.mutate(
                  { provider: "gmail" },
                  {
                    onSuccess: () => {
                      toast("Gmail disconnected");
                      void queryClient.invalidateQueries({
                        queryKey: getIntegrationsListIntegrationsQueryKey(),
                      });
                    },
                    onError: (e) => toast.error(errorMessage(e)),
                  },
                )
              }
            >
              Disconnect
            </Button>
            <ReplyDetection
              gmail={gmail}
              connecting={connecting}
              onAllowRead={() => connect(true)}
            />
          </div>
        ) : (
          <div className="grid gap-2">
            {gmail?.last_error && <p className="text-amber-700">{gmail.last_error}</p>}
            <Button className="justify-self-start" onClick={() => connect()} disabled={connecting}>
              {connecting ? "Opening Google…" : "Connect Gmail"}
            </Button>
            <p className="text-muted-foreground text-xs">
              While the Google app is in Testing mode, Google asks you to reconnect every 7 days.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReplyDetection({
  gmail,
  connecting,
  onAllowRead,
}: {
  gmail: IntegrationOut;
  connecting: boolean;
  onAllowRead: () => void;
}) {
  const queryClient = useQueryClient();
  const toggle = useIntegrationsSetReplyDetection();
  const check = useIntegrationsCheckRepliesNow();
  const queryKey = getIntegrationsListIntegrationsQueryKey();

  return (
    <div className="grid w-full gap-2 border-t pt-3">
      <p className="font-medium">Reply detection</p>
      <p className="text-muted-foreground text-xs">
        Every 15 minutes, looks only for emails from the contacts and companies you applied to,
        reads just the sender, subject and preview, and moves the card (Replied, Interview,
        Rejected). Nothing else in your inbox is opened or stored.
      </p>
      {!gmail.can_read ? (
        <Button
          variant="outline"
          size="sm"
          className="justify-self-start"
          disabled={connecting}
          onClick={onAllowRead}
        >
          {connecting ? "Opening Google…" : "Turn on reply detection"}
        </Button>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={gmail.reply_detection}
              disabled={toggle.isPending}
              onChange={(e) =>
                toggle.mutate(
                  { data: { enabled: e.target.checked } },
                  {
                    onSuccess: (data) => queryClient.setQueryData(queryKey, data),
                    onError: (err) => toast.error(errorMessage(err)),
                  },
                )
              }
            />
            {gmail.reply_detection ? "On" : "Off"}
          </label>
          {gmail.reply_detection && (
            <Button
              variant="outline"
              size="sm"
              disabled={check.isPending}
              onClick={() =>
                check.mutate(undefined, {
                  onSuccess: () => {
                    toast("Checking for replies. Cards move in a minute if any arrived.");
                    setTimeout(() => queryClient.invalidateQueries({ queryKey }), 20_000);
                  },
                  onError: (err) => toast.error(errorMessage(err)),
                })
              }
            >
              Check now
            </Button>
          )}
          {gmail.reply_detection && gmail.replies_checked_at && (
            <span className="text-muted-foreground text-xs">
              Last checked {timeAgo(gmail.replies_checked_at)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
