"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, Loader2 } from "lucide-react";
import { useEffect } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { ResumeOut, ResumeStatus } from "@/lib/api/generated/model";
import {
  getResumesListResumesQueryKey,
  useResumesGetResume,
  useResumesReparseResume,
} from "@/lib/api/generated/resumes/resumes";
import { getUsersGetMeQueryKey } from "@/lib/api/generated/users/users";
import { errorMessage } from "@/lib/forms";

const IN_PROGRESS: ResumeStatus[] = ["uploaded", "parsing"];

const STAGES: Record<ResumeStatus, { label: string; progress: number }> = {
  uploaded: { label: "Uploaded. Waiting for the parser…", progress: 25 },
  parsing: { label: "Reading your resume with AI…", progress: 65 },
  parsed: { label: "Done", progress: 100 },
  failed: { label: "Parsing failed", progress: 100 },
};

/** Polls a resume until parsing finishes and calls onParsed once. */
export function ParseStatus({
  resumeId,
  onParsed,
  onUploadAnother,
}: {
  resumeId: string;
  onParsed: (resume: ResumeOut) => void;
  onUploadAnother: () => void;
}) {
  const queryClient = useQueryClient();
  const resume = useResumesGetResume(resumeId, {
    query: {
      refetchInterval: (q) =>
        !q.state.data || IN_PROGRESS.includes(q.state.data.status) ? 2000 : false,
    },
  });
  const reparse = useResumesReparseResume();
  const data = resume.data;

  useEffect(() => {
    if (data?.status === "parsed") {
      queryClient.invalidateQueries({ queryKey: getUsersGetMeQueryKey() });
      queryClient.invalidateQueries({ queryKey: getResumesListResumesQueryKey() });
      onParsed(data);
    }
    // onParsed is intentionally not a dependency: fire once per status change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.status, data?.id]);

  if (!data) {
    return <Progress value={10} aria-label="Loading resume status" />;
  }

  const stage = STAGES[data.status];
  if (data.status === "failed") {
    return (
      <div className="grid gap-4 rounded-xl border p-6">
        <div className="flex items-start gap-3">
          <CircleAlert className="text-destructive mt-0.5 size-5 shrink-0" aria-hidden />
          <div className="grid gap-1">
            <p className="font-medium">We couldn&apos;t parse {data.file_name}</p>
            <p className="text-muted-foreground text-sm">
              {data.error_message ?? "Something went wrong."}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={reparse.isPending}
            onClick={() =>
              reparse.mutate(
                { resumeId: data.id },
                {
                  onSuccess: () => resume.refetch(),
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            Try again
          </Button>
          <Button variant="outline" onClick={onUploadAnother}>
            Upload a different file
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-3 rounded-xl border p-6" aria-live="polite">
      <div className="flex items-center gap-3">
        {data.status === "parsed" ? (
          <CircleCheck className="size-5 text-emerald-600" aria-hidden />
        ) : (
          <Loader2 className="size-5 animate-spin" aria-hidden />
        )}
        <div className="grid">
          <p className="font-medium">{data.file_name}</p>
          <p className="text-muted-foreground text-sm">{stage.label}</p>
        </div>
      </div>
      <Progress value={stage.progress} aria-label="Parsing progress" />
      <p className="text-muted-foreground text-xs">
        This usually takes 10–40 seconds. You can leave this page; we&apos;ll keep working.
      </p>
    </div>
  );
}
