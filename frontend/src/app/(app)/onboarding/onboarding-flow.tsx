"use client";

import { Check, PartyPopper } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { PreferencesForm } from "@/components/preferences/preferences-form";
import { ParseStatus } from "@/components/resume/parse-status";
import { ProfileEditor } from "@/components/resume/profile-editor";
import { ResumeDropzone } from "@/components/resume/resume-dropzone";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { OnboardingStep } from "@/lib/api/generated/model";
import {
  useResumesGetActiveResume,
  useResumesListResumes,
} from "@/lib/api/generated/resumes/resumes";
import { useSearchesStartSearch } from "@/lib/api/generated/searches/searches";
import { useUsersGetMe } from "@/lib/api/generated/users/users";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

const STEPS: { key: OnboardingStep; label: string }[] = [
  { key: "resume", label: "Upload resume" },
  { key: "profile", label: "Review profile" },
  { key: "preferences", label: "Set preferences" },
  { key: "integrations", label: "Connect Gmail & Sheets" },
];
const ORDER: OnboardingStep[] = ["resume", "profile", "preferences", "integrations", "done"];

function Stepper({ current }: { current: OnboardingStep }) {
  const currentIndex = ORDER.indexOf(current);
  return (
    <ol className="mb-6 grid gap-2 sm:grid-cols-4">
      {STEPS.map((step, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <li
            key={step.key}
            aria-current={active ? "step" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
              active && "border-primary",
            )}
          >
            <span
              className={cn(
                "grid size-6 shrink-0 place-items-center rounded-full text-xs",
                done || active
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {done ? <Check className="size-3.5" /> : i + 1}
            </span>
            {step.label}
          </li>
        );
      })}
    </ol>
  );
}

function UploadStep() {
  const resumes = useResumesListResumes();
  const latest = resumes.data?.[0];
  // Show progress for an unfinished upload (e.g. after a page reload) unless the user
  // chose to upload a different file.
  const [tracking, setTracking] = useState<string | null>(null);
  const [replacing, setReplacing] = useState(false);
  const trackedId =
    tracking ?? (!replacing && latest && latest.status !== "parsed" ? latest.id : null);

  if (resumes.isPending) return <Skeleton className="h-48 w-full rounded-xl" />;

  return (
    <div className="grid max-w-2xl gap-4">
      {trackedId ? (
        <ParseStatus
          resumeId={trackedId}
          onParsed={() => setTracking(null)}
          onUploadAnother={() => {
            setTracking(null);
            setReplacing(true);
          }}
        />
      ) : (
        <ResumeDropzone
          onUploaded={(r) => {
            setReplacing(false);
            setTracking(r.id);
          }}
        />
      )}
      <p className="text-muted-foreground text-sm">
        The AI turns your resume into a structured profile. You&apos;ll review and correct it before
        anything is matched or sent.
      </p>
    </div>
  );
}

function ProfileStep() {
  const active = useResumesGetActiveResume();
  if (active.isPending) return <Skeleton className="h-96 w-full rounded-xl" />;
  if (!active.data) return <UploadStep />;
  return (
    <div className="grid gap-4">
      <p className="text-muted-foreground text-sm">
        Here&apos;s what we read from <strong>{active.data.file_name}</strong>. Fix anything
        that&apos;s wrong or missing; matching and applications use exactly this profile.
      </p>
      <ProfileEditor resume={active.data} saveLabel="Looks good, continue" />
    </div>
  );
}

function PreferencesStep() {
  const router = useRouter();
  const start = useSearchesStartSearch();
  return (
    <div className="grid gap-4">
      <p className="text-muted-foreground text-sm">
        We suggested titles from your resume. Adjust them, pick where you want to work, and choose
        your job sources. Saving starts your first search.
      </p>
      <PreferencesForm
        submitLabel="Save and find jobs"
        onSaved={() =>
          // Start the first search, then show it running on the jobs page.
          start.mutate({ data: { kind: "jobs" } }, { onSettled: () => router.push("/jobs") })
        }
      />
    </div>
  );
}

export function OnboardingFlow() {
  const me = useUsersGetMe();
  const hydrated = useHydrated();
  if (!hydrated || !me.data) return <Skeleton className="h-64 w-full rounded-xl" />;
  const step = me.data.onboarding_step;

  return (
    <>
      <Stepper current={step} />
      {step === "resume" && <UploadStep />}
      {step === "profile" && <ProfileStep />}
      {step === "preferences" && <PreferencesStep />}
      {(step === "integrations" || step === "done") && (
        <EmptyState
          icon={PartyPopper}
          title="You're all set"
          description="Your profile and preferences are saved. Gmail and Google Sheets connections arrive in a later phase."
          action={
            <Button asChild>
              <Link href="/jobs">Go to your jobs</Link>
            </Button>
          }
        />
      )}
    </>
  );
}
