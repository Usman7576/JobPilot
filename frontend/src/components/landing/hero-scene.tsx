"use client";

import { BellRing, CheckCircle2, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { cn } from "@/lib/utils";

import { useInView, useReducedMotion } from "./motion";

/** A score ring drawn with a gradient stroke; fills up from 0 when `show` turns true. */
export function ScoreRing({
  value,
  size = 64,
  stroke = 6,
  show = true,
  className,
}: {
  value: number;
  size?: number;
  stroke?: number;
  show?: boolean;
  className?: string;
}) {
  const id = useId();
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={cn("shrink-0 -rotate-90", className)}
      aria-hidden
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--lp-a)" />
          <stop offset="100%" stopColor="var(--lp-c)" />
        </linearGradient>
      </defs>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="currentColor"
        strokeOpacity={0.12}
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={show ? c * (1 - value / 100) : c}
        style={{ transition: "stroke-dashoffset 1.6s cubic-bezier(0.2, 0.7, 0.2, 1) 0.3s" }}
      />
    </svg>
  );
}

const EMAIL =
  "Hello Acme team,\n\nAt Analytical Engines I built FastAPI services handling 2M requests a day, and your Python and PostgreSQL stack is what I use daily. I also cut cloud costs by 40%.";
const FLAG = "cut cloud costs by 40%";

/** Types the sample email out, then marks the claim that isn't on the resume. */
function TypingEmail({ start }: { start: boolean }) {
  const reduced = useReducedMotion();
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!start || reduced) return;
    const t = setInterval(() => setN((v) => (v >= EMAIL.length ? v : v + 1)), 28);
    return () => clearInterval(t);
  }, [start, reduced]);
  const shown = reduced ? EMAIL.length : n;
  const done = shown >= EMAIL.length;
  const text = EMAIL.slice(0, shown);
  const at = EMAIL.indexOf(FLAG);
  return (
    <div className="grid gap-3">
      <p className="min-h-36 text-[13px] leading-relaxed whitespace-pre-wrap">
        {done ? (
          <>
            {EMAIL.slice(0, at)}
            <mark className="rounded-sm bg-[color-mix(in_oklch,var(--lp-bad)_22%,transparent)] px-0.5 text-current underline decoration-[var(--lp-bad)] decoration-wavy underline-offset-2">
              {FLAG}
            </mark>
            {EMAIL.slice(at + FLAG.length)}
          </>
        ) : (
          <>
            {text}
            <span className="lp-caret ml-px inline-block h-4 w-0.5 translate-y-0.5 bg-current" />
          </>
        )}
      </p>
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-all duration-500",
          "border-[color-mix(in_oklch,var(--lp-bad)_40%,transparent)] bg-[color-mix(in_oklch,var(--lp-bad)_10%,transparent)]",
          done ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
        )}
      >
        <TriangleAlert className="size-3.5 shrink-0 text-[var(--lp-bad)]" />
        &ldquo;40%&rdquo; isn&apos;t on your resume. Fix it or confirm before sending.
      </div>
    </div>
  );
}

const glass =
  "rounded-2xl border bg-card/80 shadow-2xl shadow-black/10 backdrop-blur-xl dark:shadow-black/40";

/**
 * The hero illustration: sample cards at different depths in one 3D rig. The rig leans
 * towards the cursor; each card also floats on its own. Sample content, not real data.
 */
export function HeroScene() {
  const rig = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [stageRef, inView] = useInView<HTMLDivElement>(0.2);

  useEffect(() => {
    if (reduced || !window.matchMedia("(pointer: fine)").matches) return;
    let frame = 0;
    const onMove = (e: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const x = e.clientX / window.innerWidth - 0.5;
        const y = e.clientY / window.innerHeight - 0.5;
        rig.current?.style.setProperty("--sx", x.toFixed(3));
        rig.current?.style.setProperty("--sy", y.toFixed(3));
      });
    };
    window.addEventListener("pointermove", onMove);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
    };
  }, [reduced]);

  return (
    // Phones: the scene keeps its 460px layout and is scaled down to fit, so cards never
    // collide or run off the screen.
    <div
      ref={stageRef}
      aria-hidden
      className="relative mx-auto h-[360px] w-full max-w-[540px] sm:h-[500px]"
    >
      <div className="absolute top-0 left-1/2 h-[460px] w-[460px] origin-top -translate-x-1/2 scale-[0.74] [--lp-depth:0.35] [perspective:1400px] sm:[--lp-depth:1] min-[420px]:scale-[0.85] sm:h-full sm:w-full sm:scale-100">
        <div
          ref={rig}
          className="lp-preserve absolute inset-0 transition-transform duration-700 ease-out"
          style={{
            transform:
              "rotateX(calc((8deg - var(--sy, 0) * 14deg) * var(--lp-depth))) rotateY(calc((-14deg + var(--sx, 0) * 22deg) * var(--lp-depth)))",
          }}
        >
          {/* Back: the tracking board */}
          <div
            className={cn(glass, "lp-float-slow absolute top-2 right-0 w-64 p-4 sm:w-72")}
            style={{ transform: "translateZ(calc(-140px * var(--lp-depth))) rotateZ(3deg)" }}
          >
            <p className="text-muted-foreground mb-3 text-xs font-medium">Your board</p>
            <div className="grid grid-cols-3 gap-2">
              {[
                ["Saved", 3, "var(--lp-b)"],
                ["Applied", 2, "var(--lp-a)"],
                ["Interview", 1, "var(--lp-c)"],
              ].map(([label, count, color]) => (
                <div key={label as string} className="grid content-start gap-1.5">
                  <span className="text-muted-foreground text-[10px]">{label}</span>
                  {Array.from({ length: count as number }, (_, i) => (
                    <span
                      key={i}
                      className="bg-muted h-6 rounded-md border-l-2"
                      style={{ borderLeftColor: color as string }}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* Middle: the email being written and fact-checked */}
          <div
            className={cn(
              glass,
              "lp-float absolute top-24 right-2 w-[300px] p-4 sm:right-6 sm:w-80",
            )}
            style={{ transform: "translateZ(calc(10px * var(--lp-depth)))", animationDelay: "-2s" }}
          >
            <div className="mb-3 flex items-center gap-2 text-xs font-medium">
              <Sparkles className="size-3.5 text-[var(--lp-a)]" /> Drafting from your resume
            </div>
            <TypingEmail start={inView} />
          </div>

          {/* Front: the match card */}
          <div
            className={cn(glass, "lp-float absolute bottom-6 left-0 w-64 p-4 sm:w-72")}
            style={{
              transform: "translateZ(calc(130px * var(--lp-depth)))",
              animationDelay: "-4s",
            }}
          >
            <div className="flex items-center gap-3">
              <div className="relative">
                <ScoreRing value={86} show={inView} />
                <span className="absolute inset-0 grid place-items-center text-lg font-semibold">
                  86
                </span>
              </div>
              <div className="grid gap-0.5">
                <p className="text-sm font-medium">Backend Engineer</p>
                <p className="text-muted-foreground text-xs">Example Co · Remote</p>
                <span className="mt-1 w-fit rounded-full bg-[color-mix(in_oklch,var(--lp-c)_18%,transparent)] px-2 py-0.5 text-[10px] font-medium text-[var(--lp-c)]">
                  Strong apply
                </span>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {["Python", "FastAPI", "PostgreSQL"].map((s) => (
                <span key={s} className="bg-muted rounded-md px-1.5 py-0.5 text-[10px]">
                  {s}
                </span>
              ))}
            </div>
          </div>

          {/* Closest: notifications */}
          <div
            className={cn(
              glass,
              "lp-float-slow absolute top-6 left-2 flex items-center gap-2 px-3 py-2 text-xs",
            )}
            style={{ transform: "translateZ(calc(200px * var(--lp-depth)))" }}
          >
            <BellRing className="size-3.5 text-[var(--lp-warn)]" /> Reply from Example Co: interview
          </div>
          <div
            className={cn(
              glass,
              "lp-float absolute right-4 bottom-0 flex items-center gap-2 px-3 py-2 text-xs",
            )}
            style={{
              transform: "translateZ(calc(180px * var(--lp-depth)))",
              animationDelay: "-1s",
            }}
          >
            <CheckCircle2 className="size-3.5 text-[var(--lp-c)]" /> Sent · follow-up in 7 days
          </div>
        </div>
      </div>
    </div>
  );
}
