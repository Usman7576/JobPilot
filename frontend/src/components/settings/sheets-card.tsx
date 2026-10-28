"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink, RefreshCw, Sheet } from "lucide-react";
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
  useIntegrationsDisconnect,
  useIntegrationsListIntegrations,
  useIntegrationsSyncSheets,
} from "@/lib/api/generated/integrations/integrations";
import { timeAgo } from "@/lib/format";
import { errorMessage } from "@/lib/forms";

const RESULT: Record<string, [ok: boolean, message: string]> = {
  connected: [true, "Google Sheets connected. Your tracker sheet is being created."],
  cancelled: [false, "Sheets wasn't connected (you cancelled)."],
  expired: [false, "That took too long. Try connecting again."],
  missing_permission: [false, "Allow access to files JobPilot creates, to make the tracker."],
  failed: [false, "Couldn't connect Google Sheets. Try again."],
};

export function SheetsCard() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const integrations = useIntegrationsListIntegrations({
    // Right after connecting, the sheet is created in the background: check back shortly.
    query: {
      refetchInterval: (q) =>
        q.state.data?.sheets.status === "connected" && !q.state.data.sheets.spreadsheet_url
          ? 3000
          : false,
    },
  });
  const sync = useIntegrationsSyncSheets();
  const disconnect = useIntegrationsDisconnect();
  const [connecting, setConnecting] = useState(false);
  const result = params.get("sheets");

  useEffect(() => {
    if (!result) return;
    const [ok, message] = RESULT[result] ?? RESULT.failed;
    if (ok) toast.success(message);
    else toast.error(message);
    router.replace(pathname);
  }, [result, router, pathname]);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: getIntegrationsListIntegrationsQueryKey() });
  const data = integrations.data;
  const sheets = data?.sheets;
  const connected = sheets?.status === "connected";

  const connect = async () => {
    setConnecting(true);
    try {
      const { url } = await integrationsConnect("sheets");
      window.location.assign(url);
    } catch (e) {
      toast.error(errorMessage(e));
      setConnecting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sheet className="size-4" aria-hidden /> Google Sheets
          {sheets && (
            <Badge variant={connected ? "default" : "outline"}>
              {connected
                ? "Connected"
                : sheets.status === "needs_reauth"
                  ? "Reconnect needed"
                  : "Not connected"}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          A &ldquo;JobPilot AI Tracker&rdquo; spreadsheet with your jobs and applications, updated a
          few minutes after changes. JobPilot can only open files it created. Edits you make in the
          sheet aren&apos;t copied back.
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
          <div className="grid gap-2">
            {sheets.last_error && (
              <p className="text-amber-700 dark:text-amber-400">{sheets.last_error}</p>
            )}
            <div className="flex flex-wrap items-center gap-2">
              {sheets.spreadsheet_url ? (
                <Button asChild size="sm">
                  <a href={sheets.spreadsheet_url} target="_blank" rel="noopener noreferrer">
                    Open the sheet <ExternalLink className="size-4" />
                  </a>
                </Button>
              ) : (
                <span className="text-muted-foreground">Creating your sheet…</span>
              )}
              <Button
                size="sm"
                variant="outline"
                disabled={sync.isPending}
                onClick={() =>
                  sync.mutate(undefined, {
                    onSuccess: () => {
                      toast("Syncing your sheet");
                      setTimeout(() => void refresh(), 4000);
                    },
                    onError: (e) => toast.error(errorMessage(e)),
                  })
                }
              >
                <RefreshCw className="size-4" /> Sync now
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={disconnect.isPending}
                onClick={() =>
                  disconnect.mutate(
                    { provider: "sheets" },
                    {
                      onSuccess: () => {
                        toast("Google Sheets disconnected. Your sheet stays in your Drive.");
                        void refresh();
                      },
                      onError: (e) => toast.error(errorMessage(e)),
                    },
                  )
                }
              >
                Disconnect
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              {sheets.google_email ? `Using ${sheets.google_email}. ` : ""}
              {sheets.last_sync_at
                ? `Last synced ${timeAgo(sheets.last_sync_at)}.`
                : "Not synced yet."}
            </p>
          </div>
        ) : (
          <div className="grid gap-2">
            {sheets?.last_error && <p className="text-amber-700">{sheets.last_error}</p>}
            <Button className="justify-self-start" onClick={connect} disabled={connecting}>
              {connecting ? "Opening Google…" : "Connect Google Sheets"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
