import {
  BellRing,
  CalendarClock,
  FileText,
  KanbanSquare,
  Lock,
  MailCheck,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// Signed-in visitors never see this page: the proxy sends them straight to /jobs.
export const metadata: Metadata = {
  title: { absolute: "JobPilot AI: jobs matched to your resume" },
};

const STEPS = [
  {
    icon: FileText,
    title: "Upload your resume",
    text: "AI turns your PDF or DOCX into a profile you can edit. The file is encrypted at rest.",
  },
  {
    icon: Search,
    title: "Find and rank jobs",
    text: "Searches free job sources for jobs or internships, drops what you excluded, and scores the best matches.",
  },
  {
    icon: Sparkles,
    title: "Prepare an application",
    text: "Writes an email and cover letter only from facts on your resume, and flags anything it can't back up.",
  },
  {
    icon: MailCheck,
    title: "Send and track",
    text: "Send from your own Gmail after a final preview, or apply on the company site. Then track replies on a board.",
  },
];

const FEATURES = [
  {
    icon: Target,
    title: "Scores you can read",
    text: "Each match comes with a breakdown (skills, experience, seniority, location), missing skills and red flags, in plain language.",
  },
  {
    icon: ShieldCheck,
    title: "No invented claims",
    text: "Every number, skill and degree in a draft is checked against your resume. Anything that isn't there is marked before you send.",
  },
  {
    icon: KanbanSquare,
    title: "A board for every application",
    text: "Drag cards from Saved to Applied, Replied, Interview and Offer, with a timeline and notes on each.",
  },
  {
    icon: BellRing,
    title: "Follow-ups and replies",
    text: "Reminders when a follow-up is due, AI follow-up drafts, and optional Gmail reply detection that moves cards for you.",
  },
  {
    icon: CalendarClock,
    title: "Daily searches",
    text: "A search at the hour you choose, with an email digest of new strong matches and a Google Sheets tracker.",
  },
  {
    icon: Lock,
    title: "Your data stays yours",
    text: "Export everything as a zip, or delete your account and all its data at any time.",
  },
];

const PROMISES = [
  "Nothing is sent without your review and click.",
  "Every email waits 30–120 seconds, and you can cancel it.",
  "A daily send limit you set.",
  "No logging in to job boards and no auto-filled forms.",
];

export default function Home() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2 text-lg font-semibold tracking-tight whitespace-nowrap"
        >
          <span className="bg-primary text-primary-foreground grid size-8 place-items-center rounded-lg text-sm">
            JP
          </span>
          JobPilot AI
        </Link>
        <nav className="flex items-center gap-1 sm:gap-2">
          <ThemeToggle />
          <Button asChild variant="ghost">
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild>
            <Link href="/signup">Get started</Link>
          </Button>
        </nav>
      </header>

      <main className="flex-1">
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-14 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:py-24">
          <div className="grid gap-6">
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              Find jobs that fit your resume, and apply without making anything up.
            </h1>
            <p className="text-muted-foreground max-w-xl text-lg text-pretty">
              JobPilot finds openings, explains how well each one matches you, and drafts
              applications from your real experience. You review every word and decide what gets
              sent.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/signup">Create a free account</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="/login">Sign in</Link>
              </Button>
            </div>
          </div>
          <MatchPreview />
        </section>

        <section className="bg-muted/40 border-y">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6">
            <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
            <ol className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map((step, i) => (
                <li key={step.title} className="grid content-start gap-3">
                  <div className="flex items-center gap-3">
                    <span className="bg-primary text-primary-foreground grid size-8 place-items-center rounded-full text-sm font-semibold">
                      {i + 1}
                    </span>
                    <step.icon className="text-muted-foreground size-5" aria-hidden />
                  </div>
                  <h3 className="font-medium">{step.title}</h3>
                  <p className="text-muted-foreground text-sm">{step.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight">What you get</h2>
          <div className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="grid content-start gap-2">
                <f.icon className="text-primary size-5" aria-hidden />
                <h3 className="font-medium">{f.title}</h3>
                <p className="text-muted-foreground text-sm">{f.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
          <div className="grid gap-8 rounded-xl border p-6 sm:p-10 lg:grid-cols-2">
            <div className="grid content-start gap-3">
              <h2 className="text-2xl font-semibold tracking-tight">You stay in control</h2>
              <p className="text-muted-foreground">
                JobPilot helps you apply better, not to more places blindly. Every application is
                yours to read, edit and approve.
              </p>
            </div>
            <ul className="grid gap-3">
              {PROMISES.map((p) => (
                <li key={p} className="flex items-start gap-2">
                  <ShieldCheck className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl justify-items-center gap-4 px-4 pb-20 text-center sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight">Start with your resume</h2>
          <p className="text-muted-foreground max-w-md">
            Upload it, set what you&apos;re looking for, and see your first matches in a few
            minutes.
          </p>
          <Button asChild size="lg">
            <Link href="/signup">Get started</Link>
          </Button>
        </section>
      </main>

      <footer className="text-muted-foreground border-t">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-sm sm:px-6">
          <span>JobPilot AI</span>
          <span>Job listings come from public sources and may change without notice.</span>
        </div>
      </footer>
    </div>
  );
}

/** An illustration of a match card (sample content, not real data). */
function MatchPreview() {
  return (
    <div aria-hidden className="bg-card grid gap-4 rounded-xl border p-5 shadow-sm sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="grid gap-1">
          <p className="font-medium">Backend Engineer (Python)</p>
          <p className="text-muted-foreground text-sm">Example Co · Remote</p>
        </div>
        <div className="border-primary grid size-14 shrink-0 place-items-center rounded-full border-4 text-lg font-semibold">
          86
        </div>
      </div>
      <Badge className="justify-self-start">Strong apply</Badge>
      <p className="text-sm">
        Your FastAPI and PostgreSQL work matches the core of this role, and your experience fits the
        level they ask for.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {["Python", "FastAPI", "PostgreSQL"].map((s) => (
          <Badge key={s} variant="secondary">
            {s}
          </Badge>
        ))}
        <Badge variant="outline">Missing: Kubernetes</Badge>
      </div>
      <div className="grid gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        <p className="font-medium">1 claim to check before sending</p>
        <p className="text-muted-foreground">
          &ldquo;cut costs by 40%&rdquo; isn&apos;t on your resume.
        </p>
      </div>
    </div>
  );
}
