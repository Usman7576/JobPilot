"use client";

import { AlertTriangle, Ban, CheckCircle2, Info } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { DraftOut, FlagOut } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

export const WORD_RANGE = { email: [60, 150], cover_letter: [250, 350] } as const;

export function countWords(text: string) {
  return (text.match(/\b[\w'’-]+\b/g) ?? []).length;
}

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The body with every flagged snippet marked, so the user sees exactly what to check. */
function Highlighted({ text, flags }: { text: string; flags: FlagOut[] }) {
  const parts = useMemo(() => {
    const needles = flags.map((f) => f.text).filter((t) => t.length > 0 && t.length < 120);
    if (!needles.length) return [{ text, flag: undefined as FlagOut | undefined }];
    const re = new RegExp(`(${needles.map(escape).join("|")})`, "gi");
    return text.split(re).map((part) => ({
      text: part,
      flag: flags.find((f) => f.text && f.text.toLowerCase() === part.toLowerCase()),
    }));
  }, [text, flags]);
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap">
      {parts.map((p, i) =>
        p.flag ? (
          <mark
            key={i}
            title={p.flag.reason}
            className={cn(
              "rounded px-0.5",
              p.flag.severity === "block"
                ? "bg-red-500/20 text-red-900 dark:text-red-200"
                : "bg-amber-400/25 text-amber-900 dark:text-amber-100",
            )}
          >
            {p.text}
          </mark>
        ) : (
          <Fragment key={i}>{p.text}</Fragment>
        ),
      )}
    </p>
  );
}

export function FlagList({ flags, verified }: { flags: FlagOut[]; verified: boolean }) {
  if (!flags.length) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="size-4" aria-hidden />
        {verified
          ? "Every claim traces back to your resume."
          : "No problems found by the quick checks. Run the AI fact-check before using it."}
      </p>
    );
  }
  return (
    <ul className="grid gap-1.5 text-sm">
      {flags.map((f, i) => (
        <li key={i} className="flex items-start gap-2">
          {f.severity === "block" ? (
            <Ban className="text-destructive mt-0.5 size-4 shrink-0" aria-label="Must fix" />
          ) : f.source === "length" ? (
            <Info className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-label="Note" />
          ) : (
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-label="Check" />
          )}
          <span>
            {f.text && f.source !== "verifier" && <strong className="mr-1">{f.text}:</strong>}
            {f.source === "verifier" && <em className="mr-1">&ldquo;{f.text}&rdquo;</em>}
            {f.reason}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DraftEditor({
  draft,
  kind,
  saving,
  readOnly,
  onSave,
}: {
  draft: DraftOut;
  kind: "email" | "cover_letter";
  saving: boolean;
  readOnly: boolean;
  onSave: (body: string, subject?: string) => void;
}) {
  const content = draft.content as { body?: string; subject?: string; signature?: string };
  // Local edits reset whenever a new version arrives (the key on the parent changes).
  const [body, setBody] = useState(content.body ?? "");
  const [subject, setSubject] = useState(content.subject ?? "");
  const dirty = body !== (content.body ?? "") || subject !== (content.subject ?? "");
  const words = countWords(body);
  const [low, high] = WORD_RANGE[kind];
  const flags = dirty ? [] : draft.flags;

  return (
    <div className="grid gap-4">
      {kind === "email" && (
        <div className="grid gap-1.5">
          <Label htmlFor="subject">Subject</Label>
          <Input
            id="subject"
            value={subject}
            readOnly={readOnly}
            onChange={(e) => setSubject(e.target.value)}
          />
        </div>
      )}
      <div className="grid gap-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor={`${kind}-body`}>{kind === "email" ? "Email" : "Cover letter"}</Label>
          <span
            className={cn(
              "text-xs tabular-nums",
              words > high || words < low ? "text-amber-600" : "text-muted-foreground",
            )}
          >
            {words} words · aim for {low}–{high}
          </span>
        </div>
        <Textarea
          id={`${kind}-body`}
          value={body}
          readOnly={readOnly}
          onChange={(e) => setBody(e.target.value)}
          className={cn("leading-relaxed", kind === "email" ? "min-h-64" : "min-h-96")}
        />
        {content.signature && (
          <pre className="text-muted-foreground font-sans text-sm whitespace-pre-wrap">
            {content.signature}
          </pre>
        )}
        <p className="text-muted-foreground text-xs">
          The signature comes from your profile. Edit it on the Profile page.
        </p>
      </div>

      {!readOnly && (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            disabled={!dirty || saving || !body.trim()}
            onClick={() => onSave(body, kind === "email" ? subject : undefined)}
          >
            {saving ? "Saving…" : "Save and re-check"}
          </Button>
          {dirty && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setBody(content.body ?? "");
                setSubject(content.subject ?? "");
              }}
            >
              Discard changes
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-2 rounded-md border p-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Fact check</span>
          {draft.verified ? (
            <Badge variant="outline" className="text-emerald-700 dark:text-emerald-400">
              AI-checked
            </Badge>
          ) : (
            <Badge variant="outline" className="text-muted-foreground">
              Quick checks only
            </Badge>
          )}
        </div>
        {dirty ? (
          <p className="text-muted-foreground text-sm">Save to check your edits.</p>
        ) : (
          <>
            <FlagList flags={flags} verified={draft.verified} />
            {flags.some((f) => f.text && f.source !== "length") && (
              <div className="bg-muted/50 rounded-md p-3">
                <Highlighted text={body} flags={flags} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
