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
  integrationsConnectGmail,
  useIntegrationsDisconnect,
  useIntegrationsListIntegrations,
} from "@/lib/api/generated/integrations/integrations";
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

  const connect = async () => {
    setConnecting(true);
    try {
      const { url } = await integrationsConnectGmail();
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
          Lets JobPilot send application emails from your own address, only when you click Send. It
          can send, but can&apos;t read your inbox. Sending from the app arrives in a coming update;
          connecting now gets it ready.
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
          </div>
        ) : (
          <div className="grid gap-2">
            {gmail?.last_error && <p className="text-amber-700">{gmail.last_error}</p>}
            <Button className="justify-self-start" onClick={connect} disabled={connecting}>
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
