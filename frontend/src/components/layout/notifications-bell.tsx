"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { NotificationKind } from "@/lib/api/generated/model";
import {
  getNotificationsListNotificationsQueryKey,
  useNotificationsListNotifications,
  useNotificationsMarkRead,
} from "@/lib/api/generated/notifications/notifications";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const ICON: Partial<Record<NotificationKind, typeof Bell>> = {
  follow_up_due: BellRing,
  strong_matches: Sparkles,
};

export function NotificationsBell() {
  const router = useRouter();
  const queryClient = useQueryClient();
  // Checking also creates due follow-up reminders, so poll gently.
  const list = useNotificationsListNotifications({ query: { refetchInterval: 120_000 } });
  const markRead = useNotificationsMarkRead();
  const unread = list.data?.unread ?? 0;

  return (
    <DropdownMenu
      onOpenChange={(open) => {
        if (!open && unread > 0) {
          markRead.mutate(
            { data: {} },
            {
              onSuccess: () =>
                queryClient.invalidateQueries({
                  queryKey: getNotificationsListNotificationsQueryKey(),
                }),
            },
          );
        }
      }}
    >
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        >
          <Bell className="size-5" />
          {unread > 0 && (
            <span className="bg-primary text-primary-foreground absolute -top-0.5 -right-0.5 grid min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold tabular-nums">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel>Notifications</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {!list.data?.items.length ? (
          <p className="text-muted-foreground px-2 py-6 text-center text-sm">
            Nothing yet. Reminders and new strong matches show up here.
          </p>
        ) : (
          list.data.items.slice(0, 12).map((n) => {
            const Icon = ICON[n.kind] ?? Bell;
            return (
              <DropdownMenuItem
                key={n.id}
                className="items-start gap-2 py-2"
                onSelect={() => n.link && router.push(n.link)}
              >
                <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
                <span className="grid gap-0.5">
                  <span className={cn("text-sm", !n.read && "font-semibold")}>{n.title}</span>
                  {n.body && <span className="text-muted-foreground text-xs">{n.body}</span>}
                  <span className="text-muted-foreground text-xs">{timeAgo(n.created_at)}</span>
                </span>
              </DropdownMenuItem>
            );
          })
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
