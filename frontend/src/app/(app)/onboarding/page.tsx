import { FileUp } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";

export const metadata: Metadata = { title: "Get started" };

const STEPS = ["Upload resume", "Review profile", "Set preferences", "Connect Gmail & Sheets"];

export default function OnboardingPage() {
  return (
    <>
      <PageHeader
        title="Let's set you up"
        description="Four quick steps and JobPilot starts finding jobs that fit you."
      />
      <ol className="mb-6 grid gap-2 sm:grid-cols-4">
        {STEPS.map((step, i) => (
          <li
            key={step}
            className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"
            aria-current={i === 0 ? "step" : undefined}
          >
            <span
              className={
                i === 0
                  ? "bg-primary text-primary-foreground grid size-6 place-items-center rounded-full text-xs"
                  : "bg-muted text-muted-foreground grid size-6 place-items-center rounded-full text-xs"
              }
            >
              {i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
      <EmptyState
        icon={FileUp}
        title="Resume upload arrives in Phase 2"
        description="You'll drop a PDF or DOCX here, the AI parses it into a profile, and you review and edit it before any matching happens."
      />
    </>
  );
}
