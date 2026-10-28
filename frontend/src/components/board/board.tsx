"use client";

import {
  closestCorners,
  DndContext,
  type DragEndEvent,
  type DragOverEvent,
  DragOverlay,
  type DragStartEvent,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useQueryClient } from "@tanstack/react-query";
import { BellRing, Building2, Mail, MessageSquareReply, MousePointerClick } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import {
  getApplicationsGetBoardQueryKey,
  useApplicationsMoveApplication,
} from "@/lib/api/generated/applications/applications";
import type { BoardCard, BoardCardColumn as Column } from "@/lib/api/generated/model";
import { timeAgo } from "@/lib/format";
import { errorMessage } from "@/lib/forms";
import { cn } from "@/lib/utils";

export const COLUMNS: { id: Column; label: string; hint: string }[] = [
  { id: "saved", label: "Saved", hint: "Saved or being prepared" },
  { id: "applied", label: "Applied", hint: "Waiting for a reply" },
  { id: "replied", label: "Replied", hint: "They got back to you" },
  { id: "interview", label: "Interview", hint: "Interviews scheduled or done" },
  { id: "offer", label: "Offer", hint: "Offers received" },
  { id: "rejected", label: "Rejected", hint: "Declined or withdrawn" },
];

type Lanes = Record<Column, BoardCard[]>;

function group(cards: BoardCard[]): Lanes {
  const lanes = Object.fromEntries(COLUMNS.map((c) => [c.id, [] as BoardCard[]])) as Lanes;
  for (const card of cards) lanes[card.column].push(card);
  for (const c of COLUMNS) lanes[c.id].sort((a, b) => a.position - b.position);
  return lanes;
}

function laneOf(lanes: Lanes, id: string): Column | undefined {
  if (id.startsWith("lane:")) return id.slice(5) as Column;
  return COLUMNS.find((c) => lanes[c.id].some((card) => card.id === id))?.id;
}

function CardBody({ card }: { card: BoardCard }) {
  return (
    <div className="grid gap-1.5">
      <div className="flex items-start justify-between gap-2">
        <span className="line-clamp-2 text-sm font-medium">{card.job_title}</span>
        {card.match_score != null && (
          <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
            {card.match_score}
          </span>
        )}
      </div>
      <span className="text-muted-foreground flex items-center gap-1 text-xs">
        <Building2 className="size-3" aria-hidden /> {card.company_name}
      </span>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {card.channel === "email" && (
          <Mail className="text-muted-foreground size-3" aria-label="By email" />
        )}
        {card.channel === "site" && (
          <MousePointerClick className="text-muted-foreground size-3" aria-label="On the site" />
        )}
        {card.sent_at && (
          <span className="text-muted-foreground">applied {timeAgo(card.sent_at)}</span>
        )}
        {card.follow_up_due && (
          <Badge className="gap-1 bg-amber-500 text-white hover:bg-amber-500">
            <BellRing className="size-3" aria-hidden /> Follow up
          </Badge>
        )}
        {card.last_reply_at && card.column === "replied" && (
          <Badge variant="secondary" className="gap-1">
            <MessageSquareReply className="size-3" aria-hidden /> Reply
          </Badge>
        )}
        {card.status === "withdrawn" && <Badge variant="outline">Withdrawn</Badge>}
        {card.status === "drafting" && <Badge variant="secondary">Writing…</Badge>}
      </div>
    </div>
  );
}

function SortableCard({ card, onOpen }: { card: BoardCard; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: card.id,
  });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "bg-card hover:border-primary/40 cursor-grab touch-none rounded-lg border p-3 transition-colors active:cursor-grabbing",
        isDragging && "opacity-40",
      )}
      {...attributes}
      {...listeners}
      aria-label={`${card.job_title} at ${card.company_name}. Press space to move, enter to open.`}
      onClick={() => onOpen(card.id)}
      onKeyDown={(e) => {
        listeners?.onKeyDown?.(e);
        if (e.key === "Enter" && !e.defaultPrevented) onOpen(card.id);
      }}
    >
      <CardBody card={card} />
    </li>
  );
}

function Lane({
  column,
  cards,
  onOpen,
}: {
  column: (typeof COLUMNS)[number];
  cards: BoardCard[];
  onOpen: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `lane:${column.id}` });
  return (
    <section
      aria-label={column.label}
      className={cn(
        "bg-muted/40 flex w-64 shrink-0 flex-col gap-2 rounded-xl p-2 md:w-auto md:min-w-0 md:flex-1",
        isOver && "ring-primary/40 ring-2",
      )}
    >
      <header className="flex items-center justify-between px-1 pt-1" title={column.hint}>
        <h2 className="text-sm font-semibold">{column.label}</h2>
        <span className="text-muted-foreground text-xs tabular-nums">{cards.length}</span>
      </header>
      <SortableContext items={cards.map((c) => c.id)} strategy={verticalListSortingStrategy}>
        <ul ref={setNodeRef} className="grid min-h-24 content-start gap-2">
          {cards.map((card) => (
            <SortableCard key={card.id} card={card} onOpen={onOpen} />
          ))}
        </ul>
      </SortableContext>
    </section>
  );
}

export function Board({ cards, onOpen }: { cards: BoardCard[]; onOpen: (id: string) => void }) {
  const queryClient = useQueryClient();
  const move = useApplicationsMoveApplication();
  const server = useMemo(() => group(cards), [cards]);
  // While dragging, cards move between lanes locally; the server confirms on drop.
  const [local, setLocal] = useState<Lanes | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const lanes = local ?? server;
  const active = activeId ? cards.find((c) => c.id === activeId) : undefined;

  // Screen-reader announcements name the job and the column, never internal ids.
  const describe = (id: string) => {
    const card = cards.find((c) => c.id === id);
    return card ? `${card.job_title} at ${card.company_name}` : "the application";
  };
  const placeOf = (id: string) => {
    const column = laneOf(lanes, id);
    const label = COLUMNS.find((c) => c.id === column)?.label ?? "the board";
    return id.startsWith("lane:") ? `the ${label} column` : `${describe(id)}, in ${label}`;
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragStart = (e: DragStartEvent) => {
    setActiveId(String(e.active.id));
    setLocal(server);
  };

  const onDragOver = ({ active: a, over }: DragOverEvent) => {
    if (!over || !local) return;
    const from = laneOf(local, String(a.id));
    const to = laneOf(local, String(over.id));
    if (!from || !to || from === to) return;
    const card = local[from].find((c) => c.id === a.id);
    if (!card) return;
    const target = local[to].filter((c) => c.id !== a.id);
    const overIndex = target.findIndex((c) => c.id === over.id);
    target.splice(overIndex === -1 ? target.length : overIndex, 0, { ...card, column: to });
    setLocal({ ...local, [from]: local[from].filter((c) => c.id !== a.id), [to]: target });
  };

  const onDragEnd = ({ active: a, over }: DragEndEvent) => {
    const lanesNow = local;
    setActiveId(null);
    if (!over || !lanesNow) {
      setLocal(null);
      return;
    }
    const to = laneOf(lanesNow, String(over.id));
    if (!to) {
      setLocal(null);
      return;
    }
    const lane = [...lanesNow[to]];
    const from = lane.findIndex((c) => c.id === a.id);
    const overIndex = lane.findIndex((c) => c.id === over.id);
    if (from !== -1 && overIndex !== -1 && from !== overIndex) {
      const [moved] = lane.splice(from, 1);
      lane.splice(overIndex, 0, moved);
    }
    const index = lane.findIndex((c) => c.id === a.id);
    const original = cards.find((c) => c.id === a.id);
    const unchanged =
      original?.column === to && server[to].findIndex((c) => c.id === a.id) === index;
    setLocal({ ...lanesNow, [to]: lane });
    if (unchanged) {
      setLocal(null);
      return;
    }
    move.mutate(
      {
        applicationId: String(a.id),
        data: {
          column: to,
          before_id: lane[index - 1]?.id ?? null,
          after_id: lane[index + 1]?.id ?? null,
        },
      },
      {
        onSettled: async () => {
          await queryClient.invalidateQueries({ queryKey: getApplicationsGetBoardQueryKey() });
          setLocal(null);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      accessibility={{
        screenReaderInstructions: {
          draggable:
            "Press space to pick up this application. Use the arrow keys to move it, space to drop it, escape to cancel. To move it to another column, press enter to open it and use Move to.",
        },
        announcements: {
          onDragStart: ({ active: a }) => `Picked up ${describe(String(a.id))}.`,
          onDragOver: ({ active: a, over }) =>
            over
              ? `${describe(String(a.id))} is over ${placeOf(String(over.id))}.`
              : `${describe(String(a.id))} is not over a column.`,
          onDragEnd: ({ active: a, over }) =>
            over
              ? `Dropped ${describe(String(a.id))} in ${placeOf(String(over.id))}.`
              : `${describe(String(a.id))} was dropped outside the board and didn't move.`,
          onDragCancel: ({ active: a }) => `Cancelled. ${describe(String(a.id))} didn't move.`,
        },
      }}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      onDragCancel={() => {
        setActiveId(null);
        setLocal(null);
      }}
    >
      <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-2 md:mx-0 md:px-0">
        {COLUMNS.map((column) => (
          <Lane key={column.id} column={column} cards={lanes[column.id]} onOpen={onOpen} />
        ))}
      </div>
      <DragOverlay>
        {active ? (
          <div className="bg-card w-64 rotate-2 rounded-lg border p-3 shadow-lg">
            <CardBody card={active} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
