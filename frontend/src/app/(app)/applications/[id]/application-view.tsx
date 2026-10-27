"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  ClipboardCopy,
  Download,
  ExternalLink,
  Loader2,
  Mail,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { DraftEditor } from "@/components/applications/draft-editor";
import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/fetcher";
import {
  getApplicationsGetApplicationQueryKey,
  useApplicationsAcknowledgeFlags,
  useApplicationsDeleteApplication,
  useApplicationsGetApplication,
  useApplicationsMarkApplied,
  useApplicationsRegenerateDraft,
  useApplicationsUpdateApplication,
  useApplicationsUseDraftVersion,
  useApplicationsVerifyApplication,
} from "@/lib/api/generated/applications/applications";
import type {
  ApplicationOut,
  ApplicationPatch,
  DraftOut,
  Tone,
  RegenerateInKind as WritableKind,
} from "@/lib/api/generated/model";
import { timeAgo } from "@/lib/format";
import { errorMessage } from "@/lib/forms";
import { cn } from "@/lib/utils";

const TABS: { value: WritableKind; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "cover_letter", label: "Cover letter" },
  { value: "resume_tweaks", label: "Resume tweaks" },
];
const TONES: Tone[] = ["formal", "friendly", "concise"];
const SOURCE_LABEL: Record<string, string> = {
  job_description: "From the job post",
  hunter_domain: "Found with Hunter.io",
  hunter_finder: "Found with Hunter.io",
  manual: "Added by you",
  none: "",
};
const STATUS_LABEL: Record<string, string> = {
  saved: "Saved",
  drafting: "Writing…",
  ready: "Ready to review",
  applied: "Applied",
};
const selectClass = "border-input bg-background h-8 rounded-md border px-2 text-sm";
const VERIFY_TIMEOUT_MS = 90_000;

function fullEmail(app: ApplicationOut) {
  const c = (app.email?.content ?? {}) as { body?: string; signature?: string };
  return [c.body, c.signature].filter(Boolean).join("\n\n");
}

function coverLetterText(app: ApplicationOut) {
  const c = (app.cover_letter?.content ?? {}) as { body?: string; signature?: string };
  return [c.body, c.signature].filter(Boolean).join("\n\n");
}

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${what} copied`);
  } catch {
    toast.error("Couldn't copy. Select the text and copy it yourself.");
  }
}

export function ApplicationView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<WritableKind>("email");
  const [tone, setTone] = useState<Tone | null>(null);
  const [verifyFrom, setVerifyFrom] = useState<number | null>(null);
  const [siteChecklist, setSiteChecklist] = useState(false);

  const app = useApplicationsGetApplication(id, {
    query: {
      refetchInterval: (q) => (q.state.data?.is_generating || verifyFrom ? 2500 : false),
    },
  });
  const key = getApplicationsGetApplicationQueryKey(id);
  const onData = (data: ApplicationOut) => queryClient.setQueryData(key, data);
  const onError = (e: unknown) => toast.error(errorMessage(e));

  const update = useApplicationsUpdateApplication();
  const regenerate = useApplicationsRegenerateDraft();
  const verify = useApplicationsVerifyApplication();
  const useVersion = useApplicationsUseDraftVersion();
  const acknowledge = useApplicationsAcknowledgeFlags();
  const markApplied = useApplicationsMarkApplied();
  const remove = useApplicationsDeleteApplication();

  const data = app.data;
  const allVerified = (data?.email?.verified ?? true) && (data?.cover_letter?.verified ?? true);
  const verifying = Boolean(verifyFrom && data && !allVerified);
  useEffect(() => {
    if (!verifying || !verifyFrom) return;
    const t = setTimeout(
      () => setVerifyFrom(null),
      Math.max(0, VERIFY_TIMEOUT_MS - (Date.now() - verifyFrom)),
    );
    return () => clearTimeout(t);
  }, [verifying, verifyFrom]);

  if (app.error instanceof ApiError && app.error.status === 404) {
    return (
      <EmptyState
        icon={Building2}
        title="Application not found"
        description="It may have been deleted."
        action={
          <Button asChild variant="outline">
            <Link href="/applications">All applications</Link>
          </Button>
        }
      />
    );
  }
  if (!data) return <Skeleton className="h-96 w-full rounded-xl" />;

  const applied = ["applied", "replied", "interview", "offer", "rejected"].includes(data.status);
  const currentTone = tone ?? data.tone;
  const locked = data.flags_blocked && !data.flags_acknowledged;
  const drafts: Record<WritableKind, DraftOut | null> = {
    email: data.email,
    cover_letter: data.cover_letter,
    resume_tweaks: data.resume_tweaks,
  };
  const current = drafts[tab];
  const versions = data.versions[tab] ?? [];

  const patch = (body: ApplicationPatch) =>
    update.mutate({ applicationId: id, data: body }, { onSuccess: onData, onError });
  const write = (kind: WritableKind) =>
    regenerate.mutate(
      { applicationId: id, data: { kind, tone: currentTone } },
      { onSuccess: onData, onError },
    );
  const apply = (channel: "site" | "email") =>
    markApplied.mutate(
      { applicationId: id, data: { channel } },
      {
        onSuccess: (d) => {
          onData(d);
          setSiteChecklist(false);
          toast.success("Marked as applied. Follow-up reminder set.");
        },
        onError,
      },
    );

  const mailto = data.contact_email
    ? `mailto:${data.contact_email}?subject=${encodeURIComponent(
        String((data.email?.content as { subject?: string } | undefined)?.subject ?? ""),
      )}&body=${encodeURIComponent(fullEmail(data))}`
    : null;

  return (
    <div className="grid gap-6">
      <Link
        href={`/jobs/${data.job_id}`}
        className="text-muted-foreground flex items-center gap-1 text-sm hover:underline"
      >
        <ArrowLeft className="size-4" /> Back to the job
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">{data.job_title}</h1>
          <p className="text-muted-foreground flex items-center gap-1 text-sm">
            <Building2 className="size-4" /> {data.company_name}
          </p>
        </div>
        <Badge variant={applied ? "default" : "secondary"}>
          {STATUS_LABEL[data.status] ?? data.status}
          {applied && data.sent_at ? ` · ${timeAgo(data.sent_at)}` : ""}
        </Badge>
      </header>

      {data.is_generating && (
        <div className="bg-muted flex items-center gap-2 rounded-md p-3 text-sm" aria-live="polite">
          <Loader2 className="size-4 animate-spin" /> Writing from your resume and checking every
          claim. This usually takes under a minute.
        </div>
      )}
      {data.last_error && !data.is_generating && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          {data.last_error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section className="grid content-start gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div role="tablist" className="bg-muted inline-flex rounded-lg p-1">
              {TABS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.value}
                  onClick={() => setTab(t.value)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    tab === t.value
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {!applied && (
              <div className="flex items-center gap-2">
                <select
                  aria-label="Tone"
                  className={selectClass}
                  value={currentTone}
                  onChange={(e) => setTone(e.target.value as Tone)}
                >
                  {TONES.map((t) => (
                    <option key={t} value={t} className="capitalize">
                      {t[0].toUpperCase() + t.slice(1)}
                    </option>
                  ))}
                </select>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={data.is_generating || regenerate.isPending}
                  onClick={() => write(tab)}
                >
                  <RefreshCw className="size-4" /> {current ? "Regenerate" : "Write"}
                </Button>
              </div>
            )}
          </div>

          {versions.length > 1 && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Version</span>
              <select
                aria-label="Version"
                className={selectClass}
                value={current?.id}
                onChange={(e) =>
                  useVersion.mutate(
                    { applicationId: id, data: { draft_id: e.target.value } },
                    { onSuccess: onData, onError },
                  )
                }
              >
                {versions.map((v, i) => (
                  <option key={v.id} value={v.id}>
                    {i === 0 ? "Current" : `${timeAgo(v.created_at)}`} · {v.tone}
                    {v.edited_by_user ? " · edited" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <Card>
            <CardContent className="pt-6">
              {!current ? (
                data.is_generating ? (
                  <Skeleton className="h-64 w-full" />
                ) : (
                  <EmptyState
                    icon={Sparkles}
                    title={tab === "resume_tweaks" ? "No tweaks yet" : "Nothing written yet"}
                    description={
                      tab === "resume_tweaks"
                        ? "Get 3–5 honest rewordings of your resume bullets that speak to this job."
                        : "Write a draft from your resume for this job."
                    }
                    action={
                      !applied ? (
                        <Button onClick={() => write(tab)} disabled={regenerate.isPending}>
                          <Sparkles className="size-4" /> Write it
                        </Button>
                      ) : undefined
                    }
                  />
                )
              ) : tab === "resume_tweaks" ? (
                <TweakList draft={current} />
              ) : (
                <DraftEditor
                  key={current.id + (current.edited_by_user ? "e" : "")}
                  draft={current}
                  kind={tab}
                  readOnly={applied || data.is_generating}
                  saving={update.isPending}
                  onSave={(body, subject) =>
                    patch(
                      tab === "email"
                        ? { email_body: body, subject: subject ?? null }
                        : { cover_letter_body: body },
                    )
                  }
                />
              )}
            </CardContent>
          </Card>

          {current && tab !== "resume_tweaks" && !applied && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={verifying || verify.isPending}
                onClick={() =>
                  verify.mutate(
                    { applicationId: id },
                    {
                      onSuccess: () => {
                        setVerifyFrom(Date.now());
                        // Already-checked drafts don't flip "verified", so refresh a few times.
                        for (const ms of [6000, 15000, 30000]) {
                          setTimeout(() => queryClient.invalidateQueries({ queryKey: key }), ms);
                        }
                      },
                      onError,
                    },
                  )
                }
              >
                {verifying ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ShieldCheck className="size-4" />
                )}
                {verifying ? "Fact-checking…" : "Re-check with AI"}
              </Button>
              {data.flags_blocked && !data.flags_acknowledged && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    acknowledge.mutate({ applicationId: id }, { onSuccess: onData, onError })
                  }
                >
                  I&apos;ve checked: these claims are accurate
                </Button>
              )}
            </div>
          )}
        </section>

        <aside className="grid content-start gap-4">
          <ContactCard
            app={data}
            disabled={applied}
            onSave={(email) => patch({ contact_email: email })}
            onClear={() => patch({ clear_contact: true })}
          />

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Apply</CardTitle>
              {locked && (
                <CardDescription className="text-destructive">
                  Fix the claims marked in red, or confirm they&apos;re accurate, first.
                </CardDescription>
              )}
            </CardHeader>
            <CardContent className="grid gap-2">
              {applied ? (
                <p className="text-muted-foreground text-sm">
                  You applied {timeAgo(data.sent_at)}.
                  {data.follow_up_at ? ` Follow-up reminder ${timeAgo(data.follow_up_at)}.` : ""}
                </p>
              ) : (
                <>
                  <Button
                    variant="outline"
                    className="justify-start"
                    disabled
                    title="Sending from the app is coming in a later update"
                  >
                    <Send className="size-4" /> Send via Gmail (coming soon)
                  </Button>
                  {data.email && (
                    <>
                      <Button
                        variant="outline"
                        className="justify-start"
                        disabled={locked}
                        onClick={() => copy(fullEmail(data), "Email")}
                      >
                        <ClipboardCopy className="size-4" /> Copy email
                      </Button>
                      {mailto && (
                        <Button
                          asChild={!locked}
                          variant="outline"
                          className="justify-start"
                          disabled={locked}
                        >
                          <a href={locked ? undefined : mailto}>
                            <Mail className="size-4" /> Open in my email app
                          </a>
                        </Button>
                      )}
                    </>
                  )}
                  {data.apply_url && (
                    <Button
                      className="justify-start"
                      disabled={locked}
                      onClick={() => {
                        if (data.cover_letter) void copy(coverLetterText(data), "Cover letter");
                        window.open(data.apply_url!, "_blank", "noopener,noreferrer");
                        setSiteChecklist(true);
                      }}
                    >
                      <ExternalLink className="size-4" /> Apply on the company site
                    </Button>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {siteChecklist && !applied && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">On the company site</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm">
                <ol className="list-inside list-decimal space-y-1.5">
                  {data.cover_letter && <li>Paste your cover letter (it&apos;s copied).</li>}
                  <li>
                    Upload your resume
                    {data.resume_id && (
                      <>
                        {": "}
                        <a
                          className="inline-flex items-center gap-1 underline"
                          href={`/api/v1/resumes/${data.resume_id}/file`}
                        >
                          <Download className="size-3" /> {data.resume_file_name ?? "download"}
                        </a>
                      </>
                    )}
                  </li>
                  <li>Submit the form yourself, then come back here.</li>
                </ol>
                <Button onClick={() => apply("site")} disabled={markApplied.isPending}>
                  I applied on the site
                </Button>
              </CardContent>
            </Card>
          )}

          {!applied && data.email && (
            <Button
              variant="ghost"
              className="justify-start"
              disabled={locked || markApplied.isPending}
              onClick={() => apply("email")}
            >
              I sent the email myself
            </Button>
          )}

          <NotesCard app={data} onSave={(notes) => patch({ notes })} />

          {data.events.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Timeline</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="text-muted-foreground grid gap-1 text-xs">
                  {data.events.slice(0, 8).map((e, i) => (
                    <li key={i}>
                      {timeAgo(e.created_at)} · {STATUS_LABEL[e.to_status] ?? e.to_status}
                      {e.reason ? ` · ${e.reason}` : ""}
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          )}

          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground justify-start"
            onClick={() => {
              if (!confirm("Delete this application and all its drafts?")) return;
              remove.mutate(
                { applicationId: id },
                { onSuccess: () => router.push(`/jobs/${data.job_id}`), onError },
              );
            }}
          >
            Delete application
          </Button>
        </aside>
      </div>
    </div>
  );
}

function ContactCard({
  app,
  disabled,
  onSave,
  onClear,
}: {
  app: ApplicationOut;
  disabled: boolean;
  onSave: (email: string) => void;
  onClear: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(app.contact_email ?? "");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Send to</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm">
        {editing ? (
          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              onSave(value.trim());
              setEditing(false);
            }}
          >
            <Input
              type="email"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="recruiter@company.com"
              aria-label="Contact email"
            />
            <div className="flex gap-2">
              <Button size="sm" type="submit">
                Save
              </Button>
              <Button size="sm" variant="ghost" type="button" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : app.contact_email ? (
          <>
            <span className="font-medium break-all">{app.contact_email}</span>
            <span className="text-muted-foreground text-xs">
              {SOURCE_LABEL[app.email_source]}
              {app.email_confidence != null ? ` · ${app.email_confidence}% confident` : ""}
            </span>
            {!disabled && (
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                  Change
                </Button>
                <Button size="sm" variant="ghost" onClick={onClear}>
                  Remove
                </Button>
              </div>
            )}
          </>
        ) : (
          <>
            <p className="text-muted-foreground">
              No email found in this posting. Apply on the site, or add an address you know.
            </p>
            {!disabled && (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                Add an email
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function NotesCard({ app, onSave }: { app: ApplicationOut; onSave: (notes: string) => void }) {
  const [notes, setNotes] = useState(app.notes ?? "");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Notes</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2">
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Anything to remember about this one"
          aria-label="Notes"
          className="min-h-20"
        />
        {notes !== (app.notes ?? "") && (
          <Button size="sm" onClick={() => onSave(notes)}>
            Save notes
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function TweakList({ draft }: { draft: DraftOut }) {
  const tweaks = ((draft.content as { tweaks?: unknown[] }).tweaks ?? []) as {
    bullet_id: string;
    original: string;
    suggested: string;
    rationale: string;
  }[];
  if (!tweaks.length) {
    return <p className="text-muted-foreground text-sm">No safe tweaks were found this time.</p>;
  }
  return (
    <ul className="grid gap-4">
      {tweaks.map((t) => (
        <li key={t.bullet_id} className="grid gap-2 rounded-md border p-3 text-sm">
          <div className="grid gap-1 md:grid-cols-2 md:gap-4">
            <div>
              <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">Now</p>
              <p>{t.original}</p>
            </div>
            <div>
              <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">Suggested</p>
              <p className="font-medium">{t.suggested}</p>
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-muted-foreground text-xs">{t.rationale}</span>
            <Button size="sm" variant="ghost" onClick={() => copy(t.suggested, "Bullet")}>
              <ClipboardCopy className="size-4" /> Copy
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
