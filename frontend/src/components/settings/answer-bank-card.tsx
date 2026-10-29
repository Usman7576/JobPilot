"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ListChecks, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { AnswerItem } from "@/lib/api/generated/model";
import {
  getUsersGetAnswersQueryKey,
  useUsersGetAnswers,
  useUsersSaveAnswers,
} from "@/lib/api/generated/users/users";
import { errorMessage } from "@/lib/forms";

// Offered when the bank is empty: the questions most application forms ask.
const STARTERS = [
  "Notice period / earliest start date",
  "Expected salary",
  "Are you authorized to work in this country? Do you need sponsorship?",
  "Willing to relocate?",
  "LinkedIn profile",
  "Portfolio or GitHub",
];

export function AnswerBankCard() {
  const answers = useUsersGetAnswers();
  if (!answers.data) return <Skeleton className="h-48 w-full max-w-2xl rounded-xl" />;
  // Keyed on the saved list so the editor resets after a save from elsewhere.
  return <AnswerBankEditor key={JSON.stringify(answers.data.items)} saved={answers.data.items} />;
}

function AnswerBankEditor({ saved }: { saved: AnswerItem[] }) {
  const queryClient = useQueryClient();
  const save = useUsersSaveAnswers();
  const [items, setItems] = useState<AnswerItem[]>(
    saved.length ? saved : STARTERS.map((question) => ({ question, answer: "" })),
  );
  const set = (i: number, patch: Partial<AnswerItem>) =>
    setItems((list) => list.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const dirty = JSON.stringify(items) !== JSON.stringify(saved);

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ListChecks className="size-4" aria-hidden /> Answer bank
        </CardTitle>
        <CardDescription>
          Your answers to questions application forms keep asking. They appear with copy buttons
          when you apply on a company site. Stored encrypted; empty answers aren&apos;t shown.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {items.map((item, i) => (
          <div key={i} className="grid gap-1.5 rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Input
                aria-label={`Question ${i + 1}`}
                value={item.question}
                maxLength={200}
                placeholder="Question"
                onChange={(e) => set(i, { question: e.target.value })}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Remove question ${i + 1}`}
                onClick={() => setItems((list) => list.filter((_, j) => j !== i))}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
            <Textarea
              aria-label={`Answer ${i + 1}`}
              value={item.answer}
              maxLength={2000}
              placeholder="Your answer"
              className="min-h-16"
              onChange={(e) => set(i, { answer: e.target.value })}
            />
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={items.length >= 50}
            onClick={() => setItems((list) => [...list, { question: "", answer: "" }])}
          >
            <Plus className="size-4" /> Add a question
          </Button>
          <Button
            disabled={!dirty || save.isPending}
            onClick={() =>
              save.mutate(
                { data: { items: items.filter((it) => it.question.trim()) } },
                {
                  onSuccess: (data) => {
                    queryClient.setQueryData(getUsersGetAnswersQueryKey(), data);
                    toast.success("Answers saved");
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            {save.isPending ? "Saving…" : "Save answers"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
