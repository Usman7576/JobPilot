"use client";

import { FileUp, Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { useResumesUploadResume } from "@/lib/api/generated/resumes/resumes";
import type { ResumeOut } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/forms";
import { cn } from "@/lib/utils";

const MAX_MB = 5;
const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function clientCheck(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!name.endsWith(".pdf") && !name.endsWith(".docx")) {
    return "Only PDF and DOCX files are supported.";
  }
  if (file.size > MAX_MB * 1024 * 1024) return `Files can be at most ${MAX_MB} MB.`;
  if (file.size === 0) return "The file is empty.";
  return null;
}

export function ResumeDropzone({
  onUploaded,
  compact = false,
}: {
  onUploaded: (resume: ResumeOut) => void;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useResumesUploadResume();

  const send = (file: File | undefined) => {
    if (!file || upload.isPending) return;
    const problem = clientCheck(file);
    if (problem) {
      toast.error(problem);
      return;
    }
    upload.mutate(
      { data: { file } },
      {
        onSuccess: onUploaded,
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  };

  return (
    <button
      type="button"
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        send(e.dataTransfer.files[0]);
      }}
      disabled={upload.isPending}
      className={cn(
        "flex w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 text-center transition-colors",
        compact ? "py-6" : "py-14",
        dragging ? "border-primary bg-primary/5" : "hover:border-primary/60 hover:bg-muted/40",
        upload.isPending && "cursor-wait opacity-70",
      )}
    >
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          send(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <div className="bg-muted grid size-12 place-items-center rounded-full">
        {upload.isPending ? (
          <Loader2 className="size-6 animate-spin" aria-hidden />
        ) : (
          <FileUp className="text-muted-foreground size-6" aria-hidden />
        )}
      </div>
      <div className="grid gap-1">
        <p className="font-medium">
          {upload.isPending ? "Uploading…" : "Drop your resume here, or click to choose"}
        </p>
        <p className="text-muted-foreground text-sm">
          PDF or DOCX, up to {MAX_MB} MB. Stored encrypted; only you can see it.
        </p>
      </div>
    </button>
  );
}
