"use client";

import { KanbanSquare } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ApplicationDrawer } from "@/components/board/application-drawer";
import { Board } from "@/components/board/board";
import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useApplicationsGetBoard } from "@/lib/api/generated/applications/applications";

/** The tracker: drag cards between Saved, Applied, Replied, Interview, Offer, Rejected. */
export function ApplicationsList() {
  const board = useApplicationsGetBoard();
  const [openId, setOpenId] = useState<string | null>(null);

  if (board.isPending) {
    return (
      <div className="flex gap-3">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-64 w-64 rounded-xl" />
        ))}
      </div>
    );
  }
  if (!board.data?.length) {
    return (
      <EmptyState
        icon={KanbanSquare}
        title="Nothing here yet"
        description="Open a job and click “Prepare application” or “Save for later”."
        action={
          <Button asChild>
            <Link href="/jobs">Browse jobs</Link>
          </Button>
        }
      />
    );
  }
  const open = board.data.find((c) => c.id === openId) ?? null;
  return (
    <>
      <p className="text-muted-foreground mb-3 text-sm">
        Drag a card to another column to update it, or click it to move it, see its timeline and
        write a follow-up.
      </p>
      <Board cards={board.data} onOpen={setOpenId} />
      <ApplicationDrawer card={open} onClose={() => setOpenId(null)} />
    </>
  );
}
