"use client";

import { useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { ParseStatus } from "@/components/resume/parse-status";
import { ProfileEditor } from "@/components/resume/profile-editor";
import { ResumeDropzone } from "@/components/resume/resume-dropzone";
import { ResumeVersions } from "@/components/resume/resume-versions";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getResumesGetActiveResumeQueryKey,
  getResumesListResumesQueryKey,
  useResumesGetActiveResume,
} from "@/lib/api/generated/resumes/resumes";

export function ProfileView() {
  const queryClient = useQueryClient();
  const active = useResumesGetActiveResume();
  const [uploading, setUploading] = useState<string | null>(null);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: getResumesGetActiveResumeQueryKey() });
    queryClient.invalidateQueries({ queryKey: getResumesListResumesQueryKey() });
  };

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
      <section className="order-2 grid content-start gap-4 lg:order-1">
        {active.isPending ? (
          <Skeleton className="h-96 w-full rounded-xl" />
        ) : active.data ? (
          // Re-mount the editor when the active version or its profile changes.
          <ProfileEditor
            key={`${active.data.id}:${active.data.profile_version}`}
            resume={active.data}
          />
        ) : (
          <EmptyState
            icon={FileText}
            title="No parsed resume yet"
            description="Upload a resume to build your profile."
          />
        )}
      </section>

      <aside className="order-1 grid content-start gap-4 lg:order-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Resume versions</CardTitle>
            <CardDescription>
              The active version is used for matching. A newly parsed upload becomes active.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {uploading ? (
              <ParseStatus
                resumeId={uploading}
                onParsed={() => {
                  setUploading(null);
                  refresh();
                }}
                onUploadAnother={() => setUploading(null)}
              />
            ) : (
              <ResumeDropzone
                compact
                onUploaded={(r) => {
                  setUploading(r.id);
                  refresh();
                }}
              />
            )}
            <ResumeVersions />
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
