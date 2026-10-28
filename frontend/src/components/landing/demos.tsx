"use client";

import { CheckCircle2, Mail, Paperclip, RotateCcw, ScanSearch, Send, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { ScoreRing } from "./hero-scene";
import { CountUp, useInView } from "./motion";

const card = "rounded-2xl border bg-card/80 p-5 shadow-xl shadow-black/5 backdrop-blur sm:p-6";

// --- Why a job fits ----------------------------------------------------------------------------

const BREAKDOWN: [string, number][] = [
  ["Skills", 92],
  ["Experience", 85],
  ["Seniority", 80],
  ["Location", 100],
  ["Domain", 70],
];

export function ScoreDemo() {
  const [ref, inView] = useInView<HTMLDivElement>(0.35);
  return (
    <div ref={ref} className={cn(card, "grid gap-6 sm:grid-cols-[auto_1fr] sm:items-center")}>
      <div className="relative justify-self-center">
        <ScoreRing value={86} size={160} stroke={12} show={inView} />
        <div className="absolute inset-0 grid place-content-center text-center">
          <span className="text-4xl font-semibold">
            <CountUp to={86} />
          </span>
          <span className="text-muted-foreground text-xs">match</span>
        </div>
      </div>
      <div className="grid gap-3">
        {BREAKDOWN.map(([label, value], i) => (
          <div key={label} className="grid gap-1">
            <div className="flex justify-between text-sm">
              <span>{label}</span>
              <span className="text-muted-foreground tabular-nums">{value}</span>
            </div>
            <div className="bg-muted h-2 overflow-hidden rounded-full">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[var(--lp-a)] to-[var(--lp-c)] transition-[width] duration-1000 ease-out"
                style={{
                  width: inView ? `${value}%` : "0%",
                  transitionDelay: `${200 + i * 120}ms`,
                }}
              />
            </div>
          </div>
        ))}
        <div className="flex flex-wrap gap-1.5 pt-1 text-xs">
          <span className="rounded-full bg-[color-mix(in_oklch,var(--lp-warn)_18%,transparent)] px-2 py-0.5">
            Missing: Kubernetes
          </span>
          <span className="rounded-full bg-[color-mix(in_oklch,var(--lp-bad)_15%,transparent)] px-2 py-0.5">
            Red flag: weekend on-call
          </span>
        </div>
      </div>
    </div>
  );
}

// --- Fact-check --------------------------------------------------------------------------------

type Part = string | { text: string; ok: boolean; note: string };

const DRAFT: Part[] = [
  "I built FastAPI services handling ",
  { text: "2M requests a day", ok: true, note: "On your resume: Analytical Engines, first bullet" },
  " on AWS, and I work in ",
  { text: "Python and PostgreSQL", ok: true, note: "In your skills" },
  " every day. I ",
  { text: "led a team of 12", ok: false, note: "No team size on your resume" },
  " and ",
  { text: "cut costs by 40%", ok: false, note: "This number isn't on your resume" },
  ".",
];

export function FactCheckDemo() {
  const [state, setState] = useState<"idle" | "scanning" | "done">("idle");
  useEffect(() => {
    if (state !== "scanning") return;
    const t = setTimeout(() => setState("done"), 1400);
    return () => clearTimeout(t);
  }, [state]);
  const claims = DRAFT.filter((p): p is Exclude<Part, string> => typeof p !== "string");

  return (
    <div className={cn(card, "grid gap-4")}>
      <div className="relative overflow-hidden rounded-xl border p-4 text-sm leading-relaxed">
        {state === "scanning" && (
          <span className="lp-scan absolute inset-x-0 h-10 bg-gradient-to-b from-transparent via-[color-mix(in_oklch,var(--lp-a)_30%,transparent)] to-transparent" />
        )}
        {DRAFT.map((p, i) =>
          typeof p === "string" ? (
            <span key={i}>{p}</span>
          ) : (
            <mark
              key={i}
              title={state === "done" ? p.note : undefined}
              className={cn(
                "rounded-sm bg-transparent text-current transition-colors duration-500",
                state === "done" &&
                  (p.ok
                    ? "bg-[color-mix(in_oklch,var(--lp-c)_20%,transparent)]"
                    : "bg-[color-mix(in_oklch,var(--lp-bad)_20%,transparent)] underline decoration-[var(--lp-bad)] decoration-wavy underline-offset-2"),
              )}
            >
              {p.text}
            </mark>
          ),
        )}
      </div>

      {state === "done" ? (
        <ul className="grid gap-2 text-sm">
          {claims.map((c, i) => (
            <li
              key={c.text}
              className="lp-pop flex items-start gap-2"
              style={{ animationDelay: `${i * 90}ms` }}
            >
              {c.ok ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--lp-c)]" />
              ) : (
                <XCircle className="mt-0.5 size-4 shrink-0 text-[var(--lp-bad)]" />
              )}
              <span>
                <strong className="font-medium">{c.text}</strong>
                <span className="text-muted-foreground"> · {c.note}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">
          A sample draft. Run the check to see which claims your resume backs up.
        </p>
      )}

      <Button
        variant={state === "done" ? "outline" : "default"}
        className="justify-self-start"
        disabled={state === "scanning"}
        onClick={() => setState(state === "done" ? "idle" : "scanning")}
      >
        {state === "done" ? (
          <>
            <RotateCcw className="size-4" /> Reset
          </>
        ) : (
          <>
            <ScanSearch className="size-4" />{" "}
            {state === "scanning" ? "Checking…" : "Run the fact-check"}
          </>
        )}
      </Button>
    </div>
  );
}

// --- Send with a delay you can cancel ----------------------------------------------------------

const DEMO_SECONDS = 10;

export function SendDemo() {
  const [left, setLeft] = useState<number | null>(null);
  const [result, setResult] = useState<"sent" | "cancelled" | null>(null);

  useEffect(() => {
    if (left === null) return;
    const t = setTimeout(() => {
      if (left > 1) return setLeft(left - 1);
      setLeft(null);
      setResult("sent");
    }, 1000);
    return () => clearTimeout(t);
  }, [left]);

  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <div className={cn(card, "grid gap-4")}>
      <dl className="grid grid-cols-[4.5rem_1fr] gap-y-1 text-sm">
        <dt className="text-muted-foreground">To</dt>
        <dd>jobs@example.com</dd>
        <dt className="text-muted-foreground">Subject</dt>
        <dd>Backend Engineer application</dd>
        <dt className="text-muted-foreground">Attached</dt>
        <dd className="flex items-center gap-1">
          <Paperclip className="size-3.5" /> Your_Resume.pdf
        </dd>
      </dl>

      <div className="flex min-h-16 items-center gap-4">
        {left !== null ? (
          <>
            <div className="relative">
              <svg width="64" height="64" className="-rotate-90" aria-hidden>
                <circle
                  cx="32"
                  cy="32"
                  r={r}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={0.12}
                  strokeWidth="5"
                />
                <circle
                  cx="32"
                  cy="32"
                  r={r}
                  fill="none"
                  stroke="var(--lp-a)"
                  strokeWidth="5"
                  strokeLinecap="round"
                  strokeDasharray={c}
                  strokeDashoffset={c * (1 - left / DEMO_SECONDS)}
                  style={{ transition: "stroke-dashoffset 1s linear" }}
                />
              </svg>
              <span className="absolute inset-0 grid place-items-center font-semibold tabular-nums">
                {left}
              </span>
            </div>
            <p className="text-sm" aria-live="polite">
              Sending in {left}s. Changed your mind?
            </p>
          </>
        ) : result === "sent" ? (
          <p className="lp-pop flex items-center gap-2 text-sm" aria-live="polite">
            <CheckCircle2 className="size-5 text-[var(--lp-c)]" /> Sent from your Gmail. Moved to
            Applied, follow-up reminder set.
          </p>
        ) : result === "cancelled" ? (
          <p className="lp-pop flex items-center gap-2 text-sm" aria-live="polite">
            <XCircle className="size-5 text-[var(--lp-bad)]" /> Cancelled. Nothing was sent.
          </p>
        ) : (
          <p className="text-muted-foreground flex items-center gap-2 text-sm">
            <Mail className="size-4" /> Reviewed and ready.
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {left !== null ? (
          <Button
            variant="outline"
            onClick={() => {
              setLeft(null);
              setResult("cancelled");
            }}
          >
            Cancel sending
          </Button>
        ) : (
          <Button
            className="lp-shine"
            onClick={() => {
              setResult(null);
              setLeft(DEMO_SECONDS);
            }}
          >
            <Send className="size-4" /> {result ? "Try again" : "Send"}
          </Button>
        )}
      </div>
      <p className="text-muted-foreground text-xs">
        Demo: {DEMO_SECONDS} seconds. In the app every email waits 30–120 seconds.
      </p>
    </div>
  );
}
