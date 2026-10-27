"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Download, MoreHorizontal, RefreshCw, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import type { ResumeStatus, ResumeSummary } from "@/lib/api/generated/model";
import {
  getResumesGetActiveResumeQueryKey,
  getResumesListResumesQueryKey,
  useResumesActivateResume,
  useResumesDeleteResume,
  useResumesListResumes,
  useResumesReparseResume,
} from "@/lib/api/generated/resumes/resumes";
import { errorMessage } from "@/lib/forms";

const STATUS_BADGE: Record<
  ResumeStatus,
  { label: string; variant: "secondary" | "destructive" | "outline" }
> = {
  uploaded: { label: "Queued", variant: "outline" },
  parsing: { label: "Parsing…", variant: "outline" },
  parsed: { label: "Parsed", variant: "secondary" },
  failed: { label: "Failed", variant: "destructive" },
};

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

export function ResumeVersions() {
  const queryClient = useQueryClient();
  const list = useResumesListResumes({
    query: {
      refetchInterval: (q) =>
        q.state.data?.some((r) => r.status === "uploaded" || r.status === "parsing") ? 3000 : false,
    },
  });
  const activate = useResumesActivateResume();
  const reparse = useResumesReparseResume();
  const remove = useResumesDeleteResume();
  const [toDelete, setToDelete] = useState<ResumeSummary | null>(null);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: getResumesListResumesQueryKey() });
    queryClient.invalidateQueries({ queryKey: getResumesGetActiveResumeQueryKey() });
  };
  const onError = (e: unknown) => toast.error(errorMessage(e));

  if (list.isPending) return <Skeleton className="h-24 w-full rounded-xl" />;
  if (!list.data?.length) {
    return <p className="text-muted-foreground text-sm">No resumes uploaded yet.</p>;
  }

  return (
    <>
      <ul className="divide-y rounded-xl border">
        {list.data.map((r) => {
          const badge = STATUS_BADGE[r.status];
          return (
            <li key={r.id} className="flex items-center gap-3 px-4 py-3">
              <div className="grid min-w-0 flex-1 gap-0.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-medium">{r.label || r.file_name}</span>
                  <span className="text-muted-foreground text-xs">v{r.version}</span>
                  {r.is_active && <Badge>Active</Badge>}
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                </div>
                <p className="text-muted-foreground text-xs">
                  Uploaded {dateFormat.format(new Date(r.created_at))}
                  {r.status === "parsed" && ` · ${r.skills_count} skills`}
                  {r.status === "failed" && r.error_message && ` · ${r.error_message}`}
                </p>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Actions for version ${r.version}`}
                  >
                    <MoreHorizontal className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {!r.is_active && r.status === "parsed" && (
                    <DropdownMenuItem
                      onSelect={() =>
                        activate.mutate(
                          { resumeId: r.id },
                          {
                            onSuccess: () => {
                              refresh();
                              toast.success(`Version ${r.version} is now active`);
                            },
                            onError,
                          },
                        )
                      }
                    >
                      <Star className="size-4" /> Make active
                    </DropdownMenuItem>
                  )}
                  {(r.status === "failed" || r.status === "parsed") && (
                    <DropdownMenuItem
                      onSelect={() =>
                        reparse.mutate({ resumeId: r.id }, { onSuccess: refresh, onError })
                      }
                    >
                      <RefreshCw className="size-4" /> Parse again
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem asChild>
                    {/* Same-origin GET with the session cookie; the API streams the decrypted file. */}
                    <a href={`/api/v1/resumes/${r.id}/file`} download>
                      <Download className="size-4" /> Download original
                    </a>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onSelect={() => setToDelete(r)}>
                    <Trash2 className="size-4" /> Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          );
        })}
      </ul>

      <AlertDialog open={toDelete !== null} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete version {toDelete?.version}?</AlertDialogTitle>
            <AlertDialogDescription>
              The file and its parsed profile are permanently deleted.
              {toDelete?.is_active && " Your newest other parsed version becomes active."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                toDelete &&
                remove.mutate(
                  { resumeId: toDelete.id },
                  {
                    onSuccess: () => {
                      refresh();
                      toast.success("Resume deleted");
                    },
                    onError,
                  },
                )
              }
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
