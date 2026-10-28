import {
  ArrowRight,
  BellRing,
  Briefcase,
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

import { FactCheckDemo, ScoreDemo, SendDemo } from "@/components/landing/demos";
import { HeroScene } from "@/components/landing/hero-scene";
import { CountUp, Reveal, Tilt } from "@/components/landing/motion";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";

// Signed-in visitors never see this page: the proxy sends them straight to /jobs.
export const metadata: Metadata = {
  title: { absolute: "JobPilot AI: jobs matched to your resume" },
};

const SOURCES = [
  "Arbeitnow",
  "Remotive",
  "Jooble",
  "Adzuna",
  "SerpAPI",
  "Google Jobs",
  "LinkedIn",
  "Indeed",
  "Glassdoor",
];

const STEPS = [
  {
    icon: FileText,
    title: "Upload your resume",
    text: "AI turns your PDF or DOCX into a profile you can edit. The file is encrypted at rest.",
  },
  {
    icon: Search,
    title: "Find and rank jobs",
    text: "Jobs or internships from free sources, minus what you excluded, ranked by fit.",
  },
  {
    icon: Sparkles,
    title: "Prepare an application",
    text: "An email and cover letter written only from facts on your resume.",
  },
  {
    icon: MailCheck,
    title: "Send and track",
    text: "Send from your Gmail after a final preview, then follow it on your board.",
  },
];

const FEATURES = [
  {
    icon: Target,
    title: "Scores you can read",
    text: "Skills, experience, seniority, domain and location, with missing skills and red flags in plain language.",
    wide: true,
  },
  {
    icon: ShieldCheck,
    title: "No invented claims",
    text: "Numbers, skills and degrees are checked against your resume before anything goes out.",
  },
  {
    icon: KanbanSquare,
    title: "A board for every application",
    text: "Drag cards from Saved to Offer, with a timeline and notes on each.",
  },
  {
    icon: BellRing,
    title: "Follow-ups and replies",
    text: "Reminders, AI follow-up drafts, and optional Gmail reply detection that moves cards for you.",
    wide: true,
  },
  {
    icon: CalendarClock,
    title: "Daily searches",
    text: "A search at your hour, an email digest of strong matches, and a Google Sheets tracker.",
  },
  {
    icon: Lock,
    title: "Your data stays yours",
    text: "Export everything as a zip, or delete your account and its data at any time.",
  },
];

const PROMISES = [
  "Nothing is sent without your review and click.",
  "Every email waits 30–120 seconds, and you can cancel it.",
  "A daily send limit you set.",
  "No logging in to job boards and no auto-filled forms.",
];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-sm font-medium tracking-wide text-[var(--lp-a)] uppercase">{children}</p>
  );
}

export default function Home() {
  return (
    <div className="landing flex min-h-svh flex-col overflow-x-clip">
      <header className="bg-background/70 sticky top-0 z-50 border-b backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-lg font-semibold tracking-tight whitespace-nowrap"
          >
            <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-[var(--lp-a)] to-[var(--lp-b)] text-sm text-white shadow-lg shadow-[color-mix(in_oklch,var(--lp-a)_40%,transparent)]">
              JP
            </span>
            JobPilot AI
          </Link>
          <nav className="flex items-center gap-1 sm:gap-2">
            <ThemeToggle />
            <Button asChild variant="ghost" className="hidden sm:inline-flex">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild className="lp-shine">
              <Link href="/signup">Get started</Link>
            </Button>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        {/* --- Hero --------------------------------------------------------------------------- */}
        <section className="relative isolate">
          <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
            <div className="lp-blob top-[-10%] left-[-10%] size-[480px] bg-[var(--lp-a)]" />
            <div
              className="lp-blob top-[10%] right-[-15%] size-[420px] bg-[var(--lp-b)]"
              style={{ animationDelay: "-6s" }}
            />
            <div
              className="lp-blob bottom-[-20%] left-[30%] size-[380px] bg-[var(--lp-c)]"
              style={{ animationDelay: "-12s" }}
            />
            <div className="lp-floor" />
          </div>

          <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 pt-14 pb-20 sm:px-6 lg:grid-cols-[1fr_1.05fr] lg:pt-20 lg:pb-28">
            <div className="grid gap-7">
              <Reveal>
                <span className="bg-background/60 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium backdrop-blur">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex size-full animate-ping rounded-full bg-[var(--lp-c)] opacity-75" />
                    <span className="relative inline-flex size-2 rounded-full bg-[var(--lp-c)]" />
                  </span>
                  Free to run · you approve every send
                </span>
              </Reveal>
              <Reveal delay={80}>
                <h1 className="text-4xl leading-[1.05] font-semibold tracking-tight text-balance sm:text-6xl">
                  Land the jobs that <span className="lp-gradient-text">actually fit you.</span>
                </h1>
              </Reveal>
              <Reveal delay={160}>
                <p className="text-muted-foreground max-w-xl text-lg text-pretty">
                  JobPilot finds openings, shows exactly why each one matches your resume, and
                  writes applications from your real experience, with every claim checked. You read
                  it, you decide, you send.
                </p>
              </Reveal>
              <Reveal delay={240} className="flex flex-wrap gap-3">
                <Button asChild size="lg" className="lp-shine h-12 px-6 text-base">
                  <Link href="/signup">
                    Create a free account <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button
                  asChild
                  size="lg"
                  variant="outline"
                  className="bg-background/60 h-12 px-6 text-base backdrop-blur"
                >
                  <a href="#demo">See it work</a>
                </Button>
              </Reveal>
              <Reveal delay={320}>
                <ul className="text-muted-foreground flex flex-wrap gap-x-5 gap-y-2 text-sm">
                  {["Resume encrypted", "No auto-filled forms", "Export or delete anytime"].map(
                    (t) => (
                      <li key={t} className="flex items-center gap-1.5">
                        <ShieldCheck className="size-4 text-[var(--lp-c)]" /> {t}
                      </li>
                    ),
                  )}
                </ul>
              </Reveal>
            </div>
            <HeroScene />
          </div>
        </section>

        {/* --- Sources marquee ------------------------------------------------------------------ */}
        <section className="bg-muted/30 border-y py-6">
          <p className="text-muted-foreground mb-4 text-center text-xs font-medium tracking-wider uppercase">
            Searches free job sources for you
          </p>
          <div className="lp-marquee-mask overflow-hidden">
            <div className="lp-marquee gap-12 pr-12">
              {[...SOURCES, ...SOURCES].map((s, i) => (
                <span
                  key={i}
                  aria-hidden={i >= SOURCES.length}
                  className="text-muted-foreground flex items-center gap-2 text-lg font-semibold whitespace-nowrap"
                >
                  <Briefcase className="size-4 opacity-60" /> {s}
                </span>
              ))}
            </div>
          </div>
        </section>

        {/* --- Numbers ------------------------------------------------------------------------- */}
        <section className="mx-auto grid max-w-6xl grid-cols-2 gap-6 px-4 py-16 sm:px-6 lg:grid-cols-4">
          {[
            { to: 9, suffix: "", label: "job sources, most with no key" },
            { to: 15, suffix: "", label: "best matches scored by AI each search" },
            { to: 120, suffix: "s", label: "at most before an email goes, cancellable" },
            { to: 100, suffix: "%", label: "of drafts fact-checked against your resume" },
          ].map((s, i) => (
            <Reveal key={s.label} delay={i * 90} className="grid gap-1">
              <span className="lp-gradient-text text-4xl font-semibold sm:text-5xl">
                <CountUp to={s.to} suffix={s.suffix} />
              </span>
              <span className="text-muted-foreground text-sm">{s.label}</span>
            </Reveal>
          ))}
        </section>

        {/* --- How it works ------------------------------------------------------------------- */}
        <section className="mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6">
          <Reveal className="grid gap-3 text-center">
            <Eyebrow>How it works</Eyebrow>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              From resume to interview in four steps
            </h2>
          </Reveal>
          <ol className="relative grid gap-10 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
            <span
              aria-hidden
              className="absolute top-7 right-[12%] left-[12%] hidden h-px bg-gradient-to-r from-[var(--lp-a)] via-[var(--lp-b)] to-[var(--lp-c)] lg:block"
            />
            {STEPS.map((step, i) => (
              <Reveal
                as="li"
                key={step.title}
                delay={i * 140}
                className="grid justify-items-center gap-3 text-center"
              >
                <span className="bg-background relative grid size-14 place-items-center rounded-2xl border shadow-lg">
                  <step.icon className="size-6 text-[var(--lp-a)]" />
                  <span className="absolute -top-2 -right-2 grid size-6 place-items-center rounded-full bg-gradient-to-br from-[var(--lp-a)] to-[var(--lp-b)] text-xs font-semibold text-white">
                    {i + 1}
                  </span>
                </span>
                <h3 className="font-medium">{step.title}</h3>
                <p className="text-muted-foreground max-w-60 text-sm">{step.text}</p>
              </Reveal>
            ))}
          </ol>
        </section>

        {/* --- Demos -------------------------------------------------------------------------- */}
        <section id="demo" className="relative isolate scroll-mt-20">
          <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
            <div className="lp-blob top-[20%] right-[-10%] size-[420px] bg-[var(--lp-b)]" />
            <div
              className="lp-blob bottom-[10%] left-[-10%] size-[380px] bg-[var(--lp-a)]"
              style={{ animationDelay: "-8s" }}
            />
          </div>
          <div className="mx-auto grid max-w-6xl gap-24 px-4 py-16 sm:px-6">
            <div className="grid items-center gap-10 lg:grid-cols-2">
              <Reveal className="grid gap-4">
                <Eyebrow>Matching</Eyebrow>
                <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                  Know why a job fits, before you apply
                </h2>
                <p className="text-muted-foreground text-lg">
                  Every match gets a score with its reasons: which of your skills it uses, what
                  you&apos;re missing, and anything that should give you pause. Jobs you ruled out
                  never make the list.
                </p>
              </Reveal>
              <Reveal delay={120}>
                <Tilt className="rounded-2xl">
                  <ScoreDemo />
                </Tilt>
              </Reveal>
            </div>

            <div className="grid items-center gap-10 lg:grid-cols-2">
              <Reveal delay={120} className="grid gap-4 lg:order-2">
                <Eyebrow>Writing</Eyebrow>
                <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                  Applications with nothing made up
                </h2>
                <p className="text-muted-foreground text-lg">
                  Drafts are written from a fact sheet of your resume. Any number, skill or degree
                  the resume can&apos;t back up is marked, and stays marked until you fix it or
                  confirm it. Try it on this sample.
                </p>
              </Reveal>
              <Reveal className="lg:order-1">
                <Tilt className="rounded-2xl" max={5}>
                  <FactCheckDemo />
                </Tilt>
              </Reveal>
            </div>
          </div>
        </section>

        {/* --- Features bento ------------------------------------------------------------------ */}
        <section className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6">
          <Reveal className="grid gap-3 text-center">
            <Eyebrow>Everything in one place</Eyebrow>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Your whole job search, organised
            </h2>
          </Reveal>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => (
              <Reveal
                key={f.title}
                delay={(i % 3) * 100}
                className={f.wide ? "lg:col-span-2" : undefined}
              >
                <Tilt className="bg-card/70 h-full rounded-2xl border p-6 backdrop-blur" max={6}>
                  <div className="relative grid gap-3">
                    <span className="grid size-11 place-items-center rounded-xl bg-[color-mix(in_oklch,var(--lp-a)_14%,transparent)]">
                      <f.icon className="size-5 text-[var(--lp-a)]" />
                    </span>
                    <h3 className="text-lg font-medium">{f.title}</h3>
                    <p className="text-muted-foreground text-sm">{f.text}</p>
                  </div>
                </Tilt>
              </Reveal>
            ))}
          </div>
        </section>

        {/* --- Control ------------------------------------------------------------------------ */}
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="grid items-center gap-10 lg:grid-cols-2">
            <Reveal className="grid gap-5">
              <Eyebrow>Sending</Eyebrow>
              <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                You press send. You can still take it back.
              </h2>
              <p className="text-muted-foreground text-lg">
                JobPilot helps you apply better, not to more places blindly.
              </p>
              <ul className="grid gap-3">
                {PROMISES.map((p, i) => (
                  <Reveal as="li" key={p} delay={i * 90} className="flex items-start gap-3">
                    <ShieldCheck className="mt-0.5 size-5 shrink-0 text-[var(--lp-c)]" />
                    <span>{p}</span>
                  </Reveal>
                ))}
              </ul>
            </Reveal>
            <Reveal delay={120}>
              <Tilt className="rounded-2xl" max={5}>
                <SendDemo />
              </Tilt>
            </Reveal>
          </div>
        </section>

        {/* --- Final call to action ------------------------------------------------------------ */}
        <section className="mx-auto max-w-6xl px-4 pt-8 pb-24 sm:px-6">
          <Reveal>
            <div className="lp-gradient-border relative isolate overflow-hidden rounded-3xl px-6 py-16 text-center sm:px-12">
              <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
                <div className="lp-blob top-[-30%] left-[20%] size-[360px] bg-[var(--lp-a)]" />
                <div
                  className="lp-blob right-[10%] bottom-[-40%] size-[320px] bg-[var(--lp-c)]"
                  style={{ animationDelay: "-5s" }}
                />
              </div>
              <Cube />
              <h2 className="mx-auto mt-10 max-w-2xl text-3xl font-semibold tracking-tight text-balance sm:text-5xl">
                Your next job is <span className="lp-gradient-text">already out there.</span>
              </h2>
              <p className="text-muted-foreground mx-auto mt-4 max-w-md text-lg">
                Upload your resume and see your first ranked matches in a few minutes.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-3">
                <Button asChild size="lg" className="lp-shine h-12 px-6 text-base">
                  <Link href="/signup">
                    Get started free <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="h-12 px-6 text-base">
                  <Link href="/login">I have an account</Link>
                </Button>
              </div>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="text-muted-foreground border-t">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-sm sm:px-6">
          <span>© JobPilot AI</span>
          <span>Job listings come from public sources and may change without notice.</span>
        </div>
      </footer>
    </div>
  );
}

/** A slowly spinning 3D cube with an orbit ring (pure CSS). */
function Cube() {
  const faces: [string, React.ReactNode][] = [
    ["rotateY(0deg)", "JP"],
    ["rotateY(90deg)", <Target key="t" className="size-9" />],
    ["rotateY(180deg)", <Sparkles key="s" className="size-9" />],
    ["rotateY(-90deg)", <MailCheck key="m" className="size-9" />],
    ["rotateX(90deg)", <KanbanSquare key="k" className="size-9" />],
    ["rotateX(-90deg)", <ShieldCheck key="sh" className="size-9" />],
  ];
  return (
    <div aria-hidden className="relative mx-auto size-24 [perspective:700px]">
      <div className="lp-preserve absolute inset-[-40px]">
        <div className="lp-orbit absolute inset-0 rounded-full border-2 border-dashed border-[color-mix(in_oklch,var(--lp-a)_50%,transparent)]" />
      </div>
      <div className="lp-preserve lp-cube relative size-full">
        {faces.map(([rotate, content], i) => (
          <div
            key={i}
            className="absolute inset-0 grid place-items-center rounded-xl border border-white/30 bg-gradient-to-br from-[var(--lp-a)] to-[var(--lp-b)] text-2xl font-semibold text-white shadow-inner"
            style={{ transform: `${rotate} translateZ(48px)`, opacity: 0.92 }}
          >
            {content}
          </div>
        ))}
      </div>
    </div>
  );
}
