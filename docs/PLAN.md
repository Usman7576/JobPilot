# JobPilot AI: Master Plan

> Status: **DRAFT, awaiting approval.** No application code is written until the folder structure (§6) and database schema (§7) are approved.
> Date: 2026-10-27

---

## Table of contents

1. [Product summary](#1-product-summary)
2. [Goals, non-goals, guiding principles](#2-goals-non-goals-guiding-principles)
3. [System architecture](#3-system-architecture)
4. [Tech stack and justified deviations](#4-tech-stack-and-justified-deviations)
5. [Key flows (sequence diagrams)](#5-key-flows-sequence-diagrams)
6. [Folder structure](#6-folder-structure)
7. [Database schema](#7-database-schema)
8. [AI pipeline design](#8-ai-pipeline-design)
9. [Job discovery and scraping](#9-job-discovery-and-scraping)
10. [Background jobs (Celery)](#10-background-jobs-celery)
11. [REST API (`/api/v1`)](#11-rest-api-apiv1)
12. [Authentication, authorization, sessions](#12-authentication-authorization-sessions)
13. [Integrations: Gmail, Sheets, Hunter](#13-integrations-gmail-sheets-hunter)
14. [Frontend design](#14-frontend-design)
15. [Safety, compliance, privacy](#15-safety-compliance-privacy)
16. [AI cost controls](#16-ai-cost-controls)
17. [Observability, reliability, error handling](#17-observability-reliability-error-handling)
18. [Configuration and environment variables](#18-configuration-and-environment-variables)
19. [Testing strategy and eval set](#19-testing-strategy-and-eval-set)
20. [DevOps: Docker, CI, deployment](#20-devops-docker-ci-deployment)
21. [Phase-by-phase build plan](#21-phase-by-phase-build-plan)
22. [Stretch features](#22-stretch-features)
23. [Risks and mitigations](#23-risks-and-mitigations)
24. [Open decisions for you](#24-open-decisions-for-you)
25. [Zero-cost stack (build and run for free)](#25-zero-cost-stack-build-and-run-for-free)

---

## 1. Product summary

JobPilot AI turns a resume into a ranked, explained feed of fresh jobs. It helps the user apply to the ones they choose, and it never sends anything without an explicit click.

| Step | What happens | Where |
|---|---|---|
| 1 | Sign up / log in (email+password or Google) | `/login`, `/signup` |
| 2 | Upload a resume (PDF/DOCX), AI parses it, user reviews and edits it | `/onboarding` step 1–2 |
| 3 | Set preferences (titles, locations, remote type, level, salary, include/exclude, sources) | `/onboarding` step 3 |
| 4 | Discover jobs, manually ("Find jobs") or on a daily schedule | `/jobs` |
| 5 | Two-stage matching: embeddings + filters, then LLM scoring with an explained breakdown | `/jobs` |
| 6 | Job detail: description, breakdown chart, matched/missing skills, red flags, company | `/jobs/[id]` |
| 7 | Prepare application: email / cover letter / resume tweaks, guardrail-checked, editable | `/jobs/[id]` panel |
| 8 | Send via Gmail (with preview), apply on the site (clipboard + checklist), or save | `/jobs/[id]` |
| 9 | Kanban tracking, reply detection, follow-up reminders | `/applications` |
| 10 | Dashboard stats + skill-gap chart | `/dashboard` |
| 11 | Optional Google Sheets mirror and daily email digest | `/settings` |

---

## 2. Goals, non-goals, guiding principles

### Goals
- A high-signal ranked feed where every score is explainable and reproducible from stored data.
- Fast time to first value: from upload to a ranked feed in under 3 minutes for a typical search.
- The human stays in the loop for every outbound action.
- Predictable AI cost per user, metered and capped.
- Swappable providers (LLM, embeddings, job sources, storage) behind interfaces.

### Non-goals (explicitly out of scope)
- Logging into job boards, using user job-board credentials, or bypassing anti-bot measures.
- Auto-filling or auto-submitting ATS forms (Workday, Greenhouse, Lever, etc.).
- Bulk or automated outreach. No email goes out without a per-message click.
- Generating claims that are not in the resume.

### Guiding principles
1. **Deterministic where possible, LLM where necessary.** Final scores, recommendations, filters, dedupe and caps are computed in code.
2. **Idempotent background work.** Every task can be retried safely.
3. **Fail soft per source.** One broken scraper never fails a whole search run.
4. **Privacy by default.** Encrypt sensitive data, keep PII out of logs, support full deletion.
5. **Typed end to end.** Pydantic → OpenAPI → generated TS client → strict TS.

---

## 3. System architecture

### 3.1 Container / component diagram

```mermaid
flowchart LR
  subgraph Client
    B[Browser<br/>Next.js App Router UI]
  end

  subgraph Vercel
    W[web: Next.js 14<br/>RSC + client components<br/>/api/v1/* rewrite proxy]
  end

  subgraph Backend["Backend (Railway / Render / Fly)"]
    A[api: FastAPI<br/>uvicorn workers]
    WK[worker: Celery<br/>queues: default, scrape, llm, email, sync]
    BT[beat: Celery Beat<br/>scheduler]
  end

  subgraph Data
    PG[(PostgreSQL 16<br/>+ pgvector)]
    R[(Redis 7<br/>broker, results, rate limits, locks)]
    S3[(S3-compatible storage<br/>resumes, encrypted)]
  end

  subgraph External
    LLM[LLM provider<br/>Anthropic Claude / OpenAI]
    EMB[Embedding provider<br/>fastembed local / OpenAI]
    JS[Job boards via python-jobspy<br/>LinkedIn, Indeed, Glassdoor, Google]
    SERP[SerpAPI Google Jobs]
    GM[Gmail API]
    GS[Google Sheets API]
    HU[Hunter.io]
    GO[Google OAuth]
    MAIL[Transactional email<br/>Resend / SMTP: digests, verification]
  end

  B --> W
  W -->|same-origin /api/v1 proxy| A
  A --> PG
  A --> R
  A --> S3
  A -->|enqueue| R
  BT -->|schedule| R
  R --> WK
  WK --> PG
  WK --> S3
  WK --> LLM
  WK --> EMB
  WK --> JS
  WK --> SERP
  WK --> GM
  WK --> GS
  WK --> HU
  WK --> MAIL
  A --> GO
  A --> LLM
```

### 3.2 Backend layering (clean architecture, pragmatic)

```
api (routers)  ->  services (use cases)  ->  repositories (SQLAlchemy)  ->  models
                          |
                          +-> domain (pure logic: scoring, dedupe, filters, guardrails)
                          +-> providers (interfaces + adapters: llm, embeddings, sources, storage, email)
                          +-> integrations (gmail, sheets, hunter)
tasks (celery) -> services   (tasks are thin wrappers; logic lives in services/domain)
```

- **Routers** do HTTP concerns only: validation, auth dependency, status codes.
- **Services** orchestrate. They are the only layer that touches repositories and providers together.
- **Domain** holds pure, unit-testable functions with no I/O (scoring math, hard filters, dedupe hash, guardrail checks, recommendation banding).
- **Providers** are `Protocol` interfaces with concrete adapters picked at startup from config (a DI container built in `app/core/deps.py`).

### 3.3 Data flow summary

1. Upload → file encrypted → S3/disk → `parse_resume` task → LLM structured output → `resumes.parsed` → `embed_resume` task.
2. "Find jobs" → `search_runs` row → `run_search` chord: one `scrape_source` per enabled source (parallel) → `normalize_and_store` → `match_stage1` → `match_stage2` (LLM, top N) → run complete.
3. "Prepare application" → `generate_application` (sync API call with a streaming option, or task + poll) → guardrail validation → draft stored.
4. "Send" → preview → confirm → `applications.status=queued` → `send_application_email` task with a 30–120 s countdown → Gmail → `applied`.
5. Beat → `check_replies` (15 min), `follow_up_reminders` (hourly), `scheduled_searches` (15 min tick), `sheets_sync` (debounced), `daily_digest`.

---

## 4. Tech stack and justified deviations

| Area | Choice | Notes |
|---|---|---|
| Frontend | Next.js 14+ (App Router), TS strict, Tailwind, shadcn/ui, TanStack Query v5, dnd-kit, Recharts, react-hook-form + zod, next-themes, sonner (toasts) | as specified |
| API client | **orval**, generating TanStack Query hooks + types from OpenAPI | one command `pnpm gen:api` |
| Backend | FastAPI, Python 3.12, Pydantic v2, pydantic-settings | 3.12 satisfies "3.11+" |
| ORM | SQLAlchemy 2.0 (typed `Mapped[]`), Alembic, **psycopg 3** driver | psycopg3 supports async (API) and sync (Celery) with one driver |
| DB | PostgreSQL 16 + pgvector 0.7+ (HNSW indexes) | |
| Queue | Celery 5 + Redis 7 | Flower in dev for inspection |
| LLM | `LLMProvider` protocol → `AnthropicProvider` (default), `OpenAIProvider` | structured output via tool-use / JSON schema |
| Embeddings | `EmbeddingProvider` → `FastEmbedProvider` (default, local ONNX, `BAAI/bge-base-en-v1.5`, 768-d), `OpenAIEmbeddingProvider` (`text-embedding-3-small`, `dimensions=768`) | **Deviation:** Anthropic has no embedding API. A local default is free, private (resume text never leaves the server for embedding), and small enough without torch. Fixing 768 dims lets both providers share one column. |
| Scraping | `python-jobspy` + SerpAPI fallback, behind `JobSource` | |
| HTML cleaning | selectolax + bleach → markdown via `markdownify` | |
| Fuzzy match | rapidfuzz | dedupe and guardrail traceability |
| Retries | tenacity | exponential backoff + jitter |
| HTTP | httpx | respx for mocks |
| Auth | **FastAPI-owned JWT** (access + rotating refresh) in httpOnly cookies; Google login via Authlib | **Deviation from NextAuth:** a single source of truth for users and tokens in the backend; Celery and API share it; there's no dual session model. See §12. |
| Passwords | argon2-cffi | |
| Encryption | `cryptography`: MultiFernet for tokens/fields, AES-256-GCM envelope for files | key rotation supported |
| Storage | `StorageProvider` → `LocalDiskStorage` (dev), `S3Storage` (boto3; works with AWS S3, Cloudflare R2, MinIO) | |
| Transactional email | `Mailer` → Resend (or SMTP) | app-originated email (verification, digest) never uses the user's Gmail |
| Rate limiting | slowapi (Redis backend) for HTTP; Redis token buckets for sources/sends | |
| Logging | structlog (JSON in prod) + PII redaction processor; optional Sentry | |
| Python tooling | uv, ruff (lint+format), mypy --strict (incrementally), pytest, pytest-asyncio, respx, factory-boy, freezegun, testcontainers | |
| JS tooling | pnpm, eslint, prettier, vitest + Testing Library, Playwright | |

### LLM model routing (configurable)

| Task | Default model | Why |
|---|---|---|
| Resume parse | `claude-sonnet-5-5` | accuracy matters; once per upload |
| Job normalization (when rules are insufficient) | `claude-haiku-5-5` | high volume, cheap |
| Stage-2 scoring | `claude-sonnet-5-5` (switchable to haiku via config) | quality of explanations |
| Application generation | `claude-sonnet-5-5` | user-facing writing |
| Guardrail claim verification | `claude-haiku-5-5` | extraction-style |
| Reply classification | `claude-haiku-5-5` | short text |

OpenAI equivalents are mapped in `config/models.yaml`. Prompt caching is used for long static system prompts.

---

## 5. Key flows (sequence diagrams)

### 5.1 Resume upload and parse

```mermaid
sequenceDiagram
  participant U as User
  participant W as Web
  participant A as API
  participant S as Storage
  participant Q as Redis/Celery
  participant K as Worker
  participant L as LLM
  participant E as Embeddings
  U->>W: drop resume.pdf
  W->>A: POST /resumes (multipart)
  A->>A: validate type/size (≤5 MB), magic bytes, page count
  A->>S: put(encrypted file)
  A->>A: insert resumes(version=n+1, status=uploaded)
  A->>Q: parse_resume(resume_id)
  A-->>W: 202 {resume_id, status}
  K->>S: get + decrypt
  K->>K: extract text (pdfplumber / python-docx), normalize
  K->>L: parse prompt + JSON schema
  L-->>K: structured profile
  K->>K: validate (Pydantic), compute derived fields
  K->>E: embed(profile summary + skills + recent bullets)
  K->>A: update resumes(status=parsed)
  W->>A: poll GET /resumes/{id} (TanStack refetchInterval)
  U->>W: review + edit profile
  W->>A: PATCH /resumes/{id}/profile
  A->>Q: re-embed, invalidate matches for this version
```

### 5.2 Search run

```mermaid
sequenceDiagram
  participant W as Web
  participant A as API
  participant K as Worker
  participant J as JobSources
  participant L as LLM
  W->>A: POST /searches
  A->>A: lock (1 active run/user), budget check
  A-->>W: 202 {run_id}
  par per enabled source
    K->>J: fetch(query) with rate limit + backoff
    J-->>K: raw jobs (or error recorded, run continues)
  end
  K->>K: clean HTML, rules extraction, dedupe (hash + URL)
  K->>L: cheap normalization for fields rules missed (batched)
  K->>K: embed new jobs
  K->>K: Stage 1: cosine + hard filters → top N
  K->>L: Stage 2 scoring for uncached (resume_version, job) pairs
  K->>K: weighted score + recommendation in code
  K->>A: search_runs.status=completed, counts
  loop every 2s
    W->>A: GET /searches/{run_id}
  end
```

### 5.3 Prepare and send application

```mermaid
sequenceDiagram
  participant U as User
  participant W as Web
  participant A as API
  participant K as Worker
  participant G as Gmail
  U->>W: Prepare application (tone)
  W->>A: POST /jobs/{id}/prepare-application
  A->>A: contact discovery (regex → Hunter)
  A->>K: generate drafts (email, cover letter, tweaks)
  K->>K: guardrail validation → flags
  A-->>W: application(draft) + flags
  U->>W: edit, then Send via Gmail
  W->>U: Final preview modal (to, subject, body, attachment, flags acknowledged)
  U->>W: Confirm send
  W->>A: POST /applications/{id}/send (Idempotency-Key)
  A->>A: cap check (daily), Gmail connected, contact present, flags acked
  A->>K: send_email countdown=rand(30..120)s, status=queued
  Note over W,A: user can Cancel while queued
  K->>G: users.messages.send (MIME + resume attachment)
  G-->>K: message_id, thread_id
  K->>A: status=applied, sent_at, follow_up_at
```

---

## 6. Folder structure

```
jobpilot-ai/
├── README.md
├── LICENSE
├── Makefile                         # make up, make migrate, make test, make gen-api, make eval
├── docker-compose.yml               # api, worker, beat, web, postgres, redis (+ flower, minio, mailpit in dev profile)
├── docker-compose.override.yml      # dev mounts, hot reload
├── .env.example
├── .editorconfig
├── .gitignore
├── .pre-commit-config.yaml          # ruff, mypy (fast), prettier, eslint, detect-secrets
├── .github/
│   └── workflows/
│       ├── ci.yml                   # backend lint/type/test, frontend lint/type/test/build, openapi drift check
│       └── eval.yml                 # manual / nightly LLM eval run
├── docs/
│   ├── PLAN.md                      # this file
│   ├── architecture.md
│   ├── adr/                         # architecture decision records (0001-auth-in-backend.md, ...)
│   ├── screenshots/
│   └── runbooks/                    # rotating keys, restoring backups, source breakage
│
├── backend/
│   ├── pyproject.toml               # uv-managed; ruff, mypy, pytest config
│   ├── uv.lock
│   ├── Dockerfile                   # multi-stage; one image runs api / worker / beat by CMD
│   ├── alembic.ini
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   ├── config/
│   │   ├── models.yaml              # LLM model routing + per-token prices
│   │   └── scoring.yaml             # weights, thresholds, stage-1 N, banding
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory, routers, middleware
│   │   ├── core/
│   │   │   ├── config.py            # pydantic-settings Settings
│   │   │   ├── deps.py              # DI: db session, current_user, providers
│   │   │   ├── security.py          # JWT, password hashing, CSRF
│   │   │   ├── crypto.py            # MultiFernet, AES-GCM envelope, EncryptedType
│   │   │   ├── logging.py           # structlog + PII redaction
│   │   │   ├── errors.py            # error types → problem+json handlers
│   │   │   ├── ratelimit.py         # slowapi + redis token buckets
│   │   │   ├── idempotency.py
│   │   │   └── retry.py             # tenacity presets
│   │   ├── db/
│   │   │   ├── base.py              # DeclarativeBase, naming conventions, mixins (timestamps, uuid pk)
│   │   │   ├── session.py           # async engine (api), sync engine (celery)
│   │   │   └── types.py             # EncryptedText, EncryptedJSON, Vector
│   │   ├── models/                  # one module per aggregate
│   │   │   ├── user.py              # User, RefreshToken, OAuthAccount, EmailVerification
│   │   │   ├── resume.py
│   │   │   ├── preference.py
│   │   │   ├── company.py
│   │   │   ├── job.py               # Job, JobSourceRecord
│   │   │   ├── match.py             # UserJob, JobMatch
│   │   │   ├── application.py       # Application, ApplicationDraft, ApplicationEvent
│   │   │   ├── integration.py
│   │   │   ├── search.py            # SearchRun, SearchRunSource
│   │   │   ├── usage.py             # UsageEvent, UsageMonthly (view)
│   │   │   ├── notification.py
│   │   │   └── audit.py
│   │   ├── schemas/                 # Pydantic I/O models (API contracts)
│   │   │   ├── auth.py  resume.py  profile.py  preference.py  job.py  match.py
│   │   │   ├── application.py  search.py  integration.py  dashboard.py  usage.py  common.py
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       ├── auth.py  users.py  resumes.py  preferences.py  searches.py
│   │   │       ├── jobs.py  applications.py  integrations.py  sheets.py
│   │   │       ├── dashboard.py  usage.py  notifications.py  health.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── resume_service.py
│   │   │   ├── preference_service.py
│   │   │   ├── search_service.py
│   │   │   ├── normalization_service.py
│   │   │   ├── matching_service.py
│   │   │   ├── application_service.py
│   │   │   ├── contact_service.py
│   │   │   ├── send_service.py
│   │   │   ├── tracking_service.py
│   │   │   ├── sheets_service.py
│   │   │   ├── notification_service.py
│   │   │   ├── usage_service.py
│   │   │   ├── dashboard_service.py
│   │   │   └── account_service.py   # export + deletion
│   │   ├── repositories/            # thin query helpers per aggregate
│   │   ├── domain/                  # pure logic, no I/O
│   │   │   ├── scoring.py           # weighted sum, banding, location_fit
│   │   │   ├── filters.py           # hard filters
│   │   │   ├── dedupe.py            # normalize title/company/location, hash
│   │   │   ├── seniority.py         # level inference + gap
│   │   │   ├── extraction_rules.py  # salary, years, remote, emails (regex)
│   │   │   ├── guardrails.py        # claim traceability checks
│   │   │   ├── skills.py            # canonicalization + synonyms
│   │   │   └── text.py              # html → clean text, truncation
│   │   ├── providers/
│   │   │   ├── llm/
│   │   │   │   ├── base.py          # LLMProvider protocol, LLMResult (usage, cost)
│   │   │   │   ├── anthropic.py
│   │   │   │   ├── openai.py
│   │   │   │   └── fake.py          # deterministic, for tests
│   │   │   ├── embeddings/  base.py  fastembed.py  openai.py  fake.py
│   │   │   ├── sources/
│   │   │   │   ├── base.py          # JobSource protocol, RawJob, SourceQuery
│   │   │   │   ├── jobspy_source.py # LinkedIn / Indeed / Glassdoor / Google sub-sources
│   │   │   │   ├── serpapi_source.py
│   │   │   │   ├── registry.py
│   │   │   │   └── fake.py
│   │   │   ├── storage/  base.py  local.py  s3.py
│   │   │   └── mailer/   base.py  resend.py  smtp.py  console.py
│   │   ├── integrations/
│   │   │   ├── google_oauth.py      # shared OAuth client, token refresh, revoke
│   │   │   ├── gmail.py             # send MIME, history, threads
│   │   │   ├── sheets.py            # gspread wrapper, upsert by id
│   │   │   └── hunter.py
│   │   ├── prompts/                 # versioned prompt files (see §8.7)
│   │   │   ├── registry.py
│   │   │   ├── resume_parse/v1.md   resume_parse/v1.schema.json
│   │   │   ├── job_normalize/v1.md  job_normalize/v1.schema.json
│   │   │   ├── match_score/v1.md    match_score/v1.schema.json
│   │   │   ├── email_draft/v1.md
│   │   │   ├── cover_letter/v1.md
│   │   │   ├── resume_tweaks/v1.md  resume_tweaks/v1.schema.json
│   │   │   ├── claim_verify/v1.md   claim_verify/v1.schema.json
│   │   │   ├── reply_classify/v1.md reply_classify/v1.schema.json
│   │   │   ├── follow_up_draft/v1.md
│   │   │   └── _shared/guard.md     # anti-fabrication rules included by generation prompts
│   │   ├── tasks/
│   │   │   ├── celery_app.py        # app, queues, routes, beat schedule
│   │   │   ├── resume_tasks.py
│   │   │   ├── search_tasks.py
│   │   │   ├── matching_tasks.py
│   │   │   ├── application_tasks.py
│   │   │   ├── email_tasks.py
│   │   │   ├── tracking_tasks.py
│   │   │   ├── sheets_tasks.py
│   │   │   ├── digest_tasks.py
│   │   │   └── maintenance_tasks.py # purge deleted accounts, expire jobs, cleanup
│   │   └── utils/
│   ├── evals/
│   │   ├── README.md
│   │   ├── cases/                   # 10 resume/job pairs (yaml) + expected score ranges
│   │   ├── fixtures/                # anonymized resumes + job descriptions
│   │   └── run_eval.py              # prints table, exits non-zero on regression
│   ├── scripts/
│   │   ├── seed.py                  # demo user, sample resume, fake jobs
│   │   ├── rotate_keys.py
│   │   └── export_openapi.py
│   └── tests/
│       ├── conftest.py              # testcontainers pg, fake providers, factories
│       ├── factories.py
│       ├── unit/
│       │   ├── test_scoring.py  test_filters.py  test_dedupe.py  test_extraction_rules.py
│       │   ├── test_guardrails.py  test_seniority.py  test_crypto.py  test_skills.py
│       ├── integration/
│       │   ├── test_resume_pipeline.py  test_search_pipeline.py  test_matching_pipeline.py
│       │   ├── test_send_flow.py  test_reply_detection.py  test_sheets_sync.py
│       └── api/
│           ├── test_auth.py  test_resumes.py  test_preferences.py  test_searches.py
│           ├── test_jobs.py  test_applications.py  test_integrations.py  test_account_deletion.py
│
└── frontend/
    ├── package.json
    ├── pnpm-lock.yaml
    ├── next.config.mjs              # rewrites /api/v1/* → API_URL, security headers
    ├── tsconfig.json                # strict, noUncheckedIndexedAccess
    ├── tailwind.config.ts
    ├── postcss.config.mjs
    ├── components.json              # shadcn/ui
    ├── orval.config.ts
    ├── playwright.config.ts
    ├── vitest.config.ts
    ├── middleware.ts                # redirect unauthenticated users, onboarding gate
    ├── public/
    └── src/
        ├── app/
        │   ├── layout.tsx           # ThemeProvider, QueryProvider, Toaster
        │   ├── page.tsx             # landing → redirect
        │   ├── (auth)/login/page.tsx   (auth)/signup/page.tsx   (auth)/verify/page.tsx
        │   ├── (app)/layout.tsx     # sidebar + topbar shell
        │   ├── (app)/onboarding/page.tsx
        │   ├── (app)/jobs/page.tsx
        │   ├── (app)/jobs/[id]/page.tsx
        │   ├── (app)/applications/page.tsx
        │   ├── (app)/dashboard/page.tsx
        │   ├── (app)/settings/page.tsx       (tabs: profile, preferences, resumes, integrations, limits, usage, account)
        │   ├── oauth/callback/[provider]/page.tsx
        │   └── not-found.tsx  error.tsx  loading.tsx
        ├── api/
        │   ├── generated/           # orval output (committed; CI checks drift)
        │   └── fetcher.ts           # credentials: 'include', CSRF header, 401 → refresh → retry
        ├── components/
        │   ├── ui/                  # shadcn primitives
        │   ├── layout/              # Sidebar, Topbar, ThemeToggle, UserMenu
        │   ├── onboarding/          # ResumeDropzone, ProfileEditor, PreferencesForm, ConnectIntegrations, Stepper
        │   ├── resume/              # SkillEditor, ExperienceEditor, EducationEditor
        │   ├── jobs/                # JobCard, JobFilters, FindJobsButton, SearchProgress, ScoreBadge, RecommendationBadge
        │   ├── job-detail/          # ScoreBreakdownChart, SkillChips, RedFlags, CompanyCard, JobDescription
        │   ├── apply/               # PreparePanel, DraftEditor, ToneSelector, GuardrailFlags, SendPreviewDialog, ApplyOnSiteChecklist
        │   ├── applications/        # KanbanBoard, KanbanColumn, ApplicationCard, ApplicationDrawer, Timeline
        │   ├── dashboard/           # StatCard, MissingSkillsChart, ApplicationsOverTimeChart
        │   ├── settings/            # IntegrationCard, UsageMeter, ResumeVersions, DangerZone, ScrapingNotice
        │   └── common/              # EmptyState, Skeletons, ConfirmDialog, ErrorBoundary
        ├── hooks/                   # useSearchRun, useClipboard, useDebounce, useAuth
        ├── lib/                     # utils, formatters, constants, zod schemas
        ├── providers/               # QueryProvider, ThemeProvider
        └── tests/                   # vitest unit + e2e/ (Playwright)
```

---

## 7. Database schema

Conventions:
- Every PK is a `uuid` (generated with `uuid7` in the app, which gives time-ordered, index-friendly values).
- Every table gets `created_at` and `updated_at` (`timestamptz`, default `now()`).
- FKs from user-owned rows use `ON DELETE CASCADE` from `users`, so account deletion is one statement plus storage cleanup.
- 🔒 = encrypted at the application level (MultiFernet; stored as `bytea`).
- Enums are Postgres `ENUM` types, managed in Alembic.
- Embedding dims = **768** (`vector(768)`), with `embedding_model` recorded per row.

### 7.1 ER diagram

```mermaid
erDiagram
  users ||--o{ refresh_tokens : has
  users ||--o{ oauth_accounts : has
  users ||--o{ resumes : uploads
  users ||--|| preferences : has
  users ||--o{ search_runs : starts
  users ||--o{ user_jobs : discovers
  users ||--o{ job_matches : scored
  users ||--o{ applications : creates
  users ||--o{ integrations : connects
  users ||--o{ usage_events : incurs
  users ||--o{ notifications : receives
  companies ||--o{ jobs : posts
  companies ||--o{ company_contacts : has
  jobs ||--o{ job_source_records : "seen on"
  jobs ||--o{ user_jobs : ""
  jobs ||--o{ job_matches : ""
  jobs ||--o{ applications : ""
  resumes ||--o{ job_matches : "scored with"
  search_runs ||--o{ search_run_sources : "per source"
  search_runs ||--o{ user_jobs : "found"
  applications ||--o{ application_drafts : versions
  applications ||--o{ application_events : history
```

### 7.2 Tables

#### `users`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| email | citext UNIQUE NOT NULL | |
| password_hash | text NULL | null for Google-only accounts |
| full_name | text | |
| email_verified_at | timestamptz NULL | |
| timezone | text default 'UTC' | used for daily schedules |
| is_active | bool default true | |
| daily_send_cap | int default 25 | user-adjustable up to `MAX_DAILY_SEND_CAP` |
| follow_up_days | int default 7 | |
| monthly_ai_budget_usd | numeric(10,4) default from config | |
| onboarding_step | enum(resume, profile, preferences, integrations, done) | |
| deletion_requested_at | timestamptz NULL | triggers the purge job |
| last_login_at | timestamptz | |

#### `oauth_accounts` (login identities)
| id | user_id FK | provider enum(google) | provider_subject text | email | UNIQUE(provider, provider_subject) |

Login-only (`openid email profile`). This is separate from the Gmail/Sheets `integrations`.

#### `refresh_tokens`
| id | user_id FK | token_hash text UNIQUE (sha256) | family_id uuid | expires_at | revoked_at | user_agent | ip_hash |

Rotation with reuse detection: if a revoked token is presented, the whole family is revoked.

#### `email_verifications` / `password_resets`
| id | user_id | token_hash | expires_at | used_at |

#### `resumes`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | FK | |
| version | int | UNIQUE(user_id, version) |
| label | text | e.g. "Backend focus" (multi-resume stretch) |
| is_active | bool | partial unique index: one active per user |
| status | enum(uploaded, parsing, parsed, failed) | |
| error | text NULL | non-PII error code/message |
| file_key | text | storage key (file stored AES-GCM encrypted) |
| file_name 🔒 | bytea | |
| mime_type | text | |
| file_sha256 | text | detects duplicate uploads |
| raw_text 🔒 | bytea | |
| parsed 🔒 | bytea (JSON) | LLM output as originally parsed |
| profile 🔒 | bytea (JSON) | user-edited profile, used for matching (starts as a copy of `parsed`) |
| profile_version | int default 1 | bumps on each edit, part of the match cache key |
| skills_index | text[] | canonical skill names (not encrypted; needed for filtering/aggregation; low sensitivity) |
| total_years_experience | numeric(4,1) | |
| seniority | enum(intern, junior, mid, senior, staff, principal, manager, director) | |
| embedding | vector(768) | |
| embedding_model | text | |
| prompt_version | text | e.g. `resume_parse/v1` |

> Cache key for matches: `(resume_id, profile_version)`, referred to as **resume_version** in the spec.

#### `preferences` (1:1 with users)
| column | type |
|---|---|
| user_id | uuid PK/FK |
| target_titles | text[] |
| locations | jsonb `[{city, region, country, radius_km}]` |
| remote_types | enum[] (remote, hybrid, onsite) |
| experience_levels | enum[] |
| salary_min | int NULL |
| salary_currency | char(3) default 'USD' |
| include_keywords | text[] |
| exclude_keywords | text[] |
| exclude_companies | text[] (normalized) |
| sources | text[] e.g. {linkedin, indeed, glassdoor, google, serpapi} |
| posted_within_days | int default 7 |
| results_per_source | int default 50 |
| daily_search_enabled | bool default false |
| daily_search_hour | smallint default 8 (user tz) |
| digest_enabled | bool default true |
| digest_min_score | smallint default 80 |
| stage1_top_n | smallint NULL (override config) |

#### `companies`
| id | name | normalized_name UNIQUE | domain NULL | logo_url | linkedin_url | size_range | industry | description | updated_at |

#### `company_contacts` (Hunter / regex cache, shared across users)
| id | company_id FK | email | source enum(job_description, hunter_domain, hunter_finder, manual) | confidence smallint | role text | verified_status | fetched_at | UNIQUE(company_id, email) |

#### `jobs` (global, deduplicated, shared across users)
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| company_id | FK NULL | |
| company_name | text | as scraped |
| title | text | |
| normalized_title | text | lowercase, seniority tokens stripped |
| location_raw | text | |
| location | jsonb `{city, region, country, lat, lon}` | |
| remote_type | enum(remote, hybrid, onsite, unknown) | |
| employment_type | enum(full_time, part_time, contract, internship, temporary, unknown) | |
| seniority | enum (same as resumes) NULL | |
| min_years_experience | numeric(4,1) NULL | |
| salary_min / salary_max | int NULL | |
| salary_currency | char(3) NULL | |
| salary_period | enum(year, month, hour) NULL | |
| required_skills | text[] | canonical |
| nice_to_have_skills | text[] | canonical |
| description_html | text | sanitized |
| description_text | text | clean text, used for LLM |
| contact_emails | text[] | regex-extracted |
| primary_url | text | canonical posting URL |
| apply_url | text NULL | direct apply URL if provided |
| url_hash | text UNIQUE | sha256(canonical url) |
| dedupe_hash | text UNIQUE | sha256(normalized company + normalized title + normalized location) |
| posted_at | timestamptz NULL | |
| first_seen_at / last_seen_at | timestamptz | |
| is_active | bool | false after `JOB_TTL_DAYS` unseen |
| normalization_status | enum(pending, rules_only, llm, failed) | |
| embedding | vector(768) NULL | |
| embedding_model | text | |

Indexes: HNSW on `embedding vector_cosine_ops`; btree on `(posted_at desc)`, `(company_id)`; GIN on `required_skills`; trigram GIN on `normalized_title` (optional search).

#### `job_source_records` (one job can be seen on several boards)
| id | job_id FK | source text | source_job_id text | url | raw jsonb (trimmed; no PII) | scraped_at | UNIQUE(source, source_job_id) |

#### `search_runs`
| column | type |
|---|---|
| id | uuid PK |
| user_id | FK |
| trigger | enum(manual, scheduled) |
| status | enum(queued, scraping, normalizing, matching_stage1, scoring, completed, partial, failed, cancelled) |
| progress | smallint 0–100 |
| stage_detail | text (e.g. "Scoring 12/30") |
| query_snapshot | jsonb (preferences at run time) |
| counts | jsonb `{scraped, new, duplicates, filtered_out, stage1_kept, scored, strong}` |
| error | text NULL |
| started_at / finished_at | timestamptz |
| celery_root_id | text |

#### `search_run_sources`
| id | run_id FK | source | status enum(pending, running, ok, failed, skipped) | fetched_count | error_code | error_message | duration_ms | attempts |

#### `user_jobs` (user's relation to a job, independent of resume version)
| id | user_id | job_id | first_run_id FK NULL | discovered_at | dismissed_at NULL | bookmarked bool | viewed_at NULL | UNIQUE(user_id, job_id) |

#### `job_matches`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | FK | |
| job_id | FK | |
| resume_id | FK | |
| profile_version | int | UNIQUE(job_id, resume_id, profile_version) is the cache key |
| similarity | real | stage 1 cosine |
| hard_filter_passed | bool | |
| hard_filter_reasons | text[] | e.g. `{excluded_company, location_mismatch}` |
| stage | enum(stage1, scored, score_failed) | |
| breakdown | jsonb `{skills_match, experience_match, seniority_fit, domain_relevance, location_fit}` | |
| overall_score | smallint NULL | **computed in code** |
| weights_version | text | e.g. `w1` |
| matched_skills / missing_skills | text[] | |
| red_flags | jsonb `[{code, message, severity}]` | |
| why_good_fit | text | |
| llm_recommendation | enum(strong_apply, apply, stretch, skip) | advisory |
| recommendation | enum(...) | **final, computed in code** |
| prompt_version / model | text | |
| scored_at | timestamptz | |

Indexes: `(user_id, resume_id, profile_version, overall_score desc)`.

#### `applications`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | FK | |
| job_id | FK | UNIQUE(user_id, job_id) — one application per job |
| resume_id | FK | resume attached / used |
| channel | enum(email, site, none) | |
| status | enum(saved, drafting, ready, queued, applied, replied, interview, offer, rejected, withdrawn) | kanban columns: Saved, Applied, Replied, Interview, Offer, Rejected |
| contact_email | citext NULL | |
| email_source | enum(job_description, hunter_domain, hunter_finder, manual, none) | |
| email_confidence | smallint NULL | 0–100 |
| current_draft_id | FK → application_drafts NULL | |
| subject / body 🔒 | bytea | final text actually sent (snapshot) |
| cover_letter 🔒 | bytea NULL | |
| tone | enum(formal, friendly, concise) | |
| guardrail_flags_acknowledged_at | timestamptz NULL | required if flags exist |
| idempotency_key | text NULL UNIQUE | |
| queued_at / scheduled_send_at | timestamptz NULL | |
| send_task_id | text NULL | to revoke on cancel |
| sent_at | timestamptz NULL | |
| gmail_message_id / gmail_thread_id | text NULL | |
| last_reply_at | timestamptz NULL | |
| reply_classification | enum(positive, interview, rejection, auto_reply, other) NULL | |
| follow_up_at | timestamptz NULL | |
| follow_up_count | smallint default 0 | |
| notes 🔒 | bytea NULL | user notes |
| kanban_position | double precision | for ordering within a column |
| sheet_row_synced_at | timestamptz NULL | |

#### `application_drafts` (every generation / regeneration)
| id | application_id FK | kind enum(email, cover_letter, resume_tweaks, follow_up) | tone | content 🔒 bytea (json for tweaks) | guardrail_report jsonb `{claims:[{text, traced, source_snippet_hash, reason}], blocked: bool}` | prompt_version | model | edited_by_user bool | created_at |

#### `application_events` (status history + audit for the kanban timeline)
| id | application_id FK | from_status | to_status | actor enum(user, system, gmail) | reason text | metadata jsonb | created_at |

#### `email_send_log` (for caps; never deleted on application changes)
| id | user_id | application_id | status enum(sent, failed) | sent_on date (user tz) | created_at | INDEX(user_id, sent_on) |

#### `integrations`
| column | type |
|---|---|
| id | uuid PK |
| user_id | FK |
| provider | enum(gmail, sheets) | UNIQUE(user_id, provider) |
| status | enum(connected, needs_reauth, disconnected, error) |
| google_email | text |
| scopes | text[] |
| access_token 🔒 / refresh_token 🔒 | bytea |
| token_expires_at | timestamptz |
| config | jsonb (gmail: `{history_id}`; sheets: `{spreadsheet_id, spreadsheet_url}`) |
| last_sync_at / last_error | |

#### `usage_events` (ledger)
| id | user_id | feature enum(resume_parse, normalize, score, generate, verify, classify, embed) | provider | model | input_tokens | output_tokens | cache_read_tokens | cost_usd numeric(12,6) | ref_type/ref_id | created_at |

`usage_monthly` is a materialized/aggregated view, or simply `SUM` with an index on `(user_id, created_at)`.

> Normalization calls for **global** jobs are attributed to the user whose run triggered them (first discoverer pays), so users are charged only once per new job.

#### `notifications`
| id | user_id | kind enum(search_done, strong_matches, reply_detected, follow_up_due, send_failed, integration_error, budget_warning) | title | body | link | read_at | created_at |

#### `audit_log` (security-relevant actions)
| id | user_id NULL | action (login, logout, token_reuse, integration_connect, send, account_delete_requested ...) | ip_hash | metadata jsonb | created_at |

#### `idempotency_keys`
| key | user_id | endpoint | response_hash | response_body jsonb | created_at | PK(user_id, key) |

---

## 8. AI pipeline design

### 8.1 Provider interfaces

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self, *, prompt: PromptSpec, variables: Mapping[str, Any],
        schema: type[BaseModel], model_tier: ModelTier, user_id: UUID | None,
        max_tokens: int, temperature: float = 0.2,
    ) -> LLMResult[BaseModel]: ...

    async def generate_text(...) -> LLMResult[str]: ...

class EmbeddingProvider(Protocol):
    dim: int
    model_name: str
    def embed(self, texts: Sequence[str], kind: Literal["query", "document"]) -> list[list[float]]: ...
```

- `LLMResult` carries `output`, `usage` (in/out/cache tokens), `cost_usd`, `model` and `prompt_version`.
- Every call goes through `UsageService.guarded_call()`, which checks the budget, records usage, and retries with tenacity on 429/5xx/timeouts (3 attempts, exponential 2–30 s + jitter).
- Structured output uses Anthropic **tool use with a JSON schema** (or OpenAI `response_format=json_schema`). The response is validated with Pydantic; on failure it retries once with the validation error fed back, then fails cleanly.

### 8.2 Resume parsing

1. **Extract**: `pdfplumber` (per page, layout-aware; `x_tolerance` tuned) or `python-docx` (paragraphs + tables). If there's <200 chars of text → status `failed`, code `scanned_pdf_unsupported` (OCR is a later option).
2. **Normalize text**: fix hyphenation, collapse whitespace, strip headers/footers repeated on each page, cap at ~25k chars.
3. **LLM** (`resume_parse/v1`), output schema:

```json
{
  "name": "string",
  "contact": {"email": "string|null", "phone": "string|null", "location": "string|null", "links": [{"label": "string", "url": "string"}]},
  "summary": "string",
  "total_years_experience": 0.0,
  "skills": [{"name": "string", "category": "language|framework|tool|cloud|database|soft|domain|other", "proficiency": "beginner|intermediate|advanced|expert", "evidence": "short quote"}],
  "work_history": [{"title": "", "company": "", "location": "", "start": "YYYY-MM|null", "end": "YYYY-MM|present|null", "bullets": [""]}],
  "education": [{"institution": "", "degree": "", "field": "", "start": "", "end": "", "gpa": "string|null"}],
  "projects": [{"name": "", "description": "", "technologies": [""], "url": "string|null", "bullets": [""]}],
  "certifications": [{"name": "", "issuer": "", "date": ""}],
  "preferred_roles": ["inferred titles"],
  "seniority": "intern|junior|mid|senior|staff|principal|manager|director"
}
```

4. **Post-process in code**:
   - Recompute `total_years_experience` from `work_history` dates (merge overlapping intervals; exclude internships from the "professional years" total but keep them as a separate field). Use the code value when it disagrees with the LLM by more than 1 year.
   - Canonicalize skills through `domain/skills.py` (a synonyms map: `js→JavaScript`, `k8s→Kubernetes`, `postgres→PostgreSQL`...).
5. **Embed**: text = `preferred_roles + summary + top 30 skills + last 3 roles' titles and bullets`, as a `document` embedding.
6. **Review UI** lets the user edit everything. Saving bumps `profile_version`, re-embeds, and marks existing matches stale. Re-scoring runs lazily on the next search, or immediately via "Re-score my feed" (with a budget estimate shown first).

### 8.3 Job normalization

Order: **rules first, LLM only for gaps**.

1. Clean HTML → sanitized HTML (for display) + plain text (for LLM/embedding). Strip tracking params from URLs and canonicalize them.
2. Rules (`domain/extraction_rules.py`):
   - Salary: regex for `$120k–$150k`, `USD 50/hr`, `£40,000 - £50,000 per annum` (also uses JobSpy's structured salary fields when present).
   - Years: `(\d+)\+?\s*(?:-|to)?\s*(\d+)?\s*years?` near "experience".
   - Remote type: JobSpy `is_remote` + keywords (remote, hybrid, on-site, in office N days).
   - Seniority: title tokens (Sr, Senior, Lead, Staff, Principal, Jr, Junior, Intern, Associate, Head of, Director).
   - Employment type: JobSpy field + keywords.
   - Emails: RFC-ish regex, excluding `noreply`, `privacy@`, `accommodations@`, and EEO addresses.
   - Skills: dictionary match against the canonical skill list (~2–3k terms) with word boundaries.
3. LLM (`job_normalize/v1`, haiku tier), **only if** required skills <3, or seniority/years are unknown, or there are requirement-vs-nice-to-have ambiguities. Output: `required_skills`, `nice_to_have_skills`, `min_years_experience`, `seniority`, `employment_type`, `remote_type`, `salary` (nullable). Batched 5 jobs per call to cut overhead. Rule-derived values win when both exist, except for the skills split.
4. Embed text = `title + company + required_skills + first 1500 chars of the description` (`document`).
5. **Dedupe**:
   - `url_hash` on the canonical URL (lowercase host, strip query except an allowlist like `jk`, `currentJobId`).
   - `dedupe_hash` = sha256(`normalize_company(company)` | `normalize_title(title)` | `normalize_location(location)`), where:
     - company: lowercase, strip `inc, llc, ltd, gmbh, corp, co, the`, punctuation;
     - title: lowercase, strip parenthetical codes and req IDs, collapse seniority synonyms (`sr`→`senior`), and strip location suffixes;
     - location: `city|region|country`, or `remote|country`.
   - On a hit: add a `job_source_records` row, update `last_seen_at`, and keep the richer description (the longest one).
   - Optional near-duplicate pass: same company + title similarity ≥ 92 (rapidfuzz) + same city → merge.

### 8.4 Stage 1: fast filter (no LLM)

For each job discovered for the user in this run (plus non-dismissed active jobs from the last `posted_within_days` that have no match for the current profile_version):

Hard filters (`domain/filters.py`). Each returns a reason code:
| filter | rule |
|---|---|
| excluded_company | normalized company ∈ `exclude_companies` |
| excluded_keyword | any `exclude_keywords` in title or description (word-boundary, case-insensitive) |
| missing_include_keyword | if `include_keywords` is set, at least one must appear |
| remote_mismatch | job remote_type known and ∉ user remote_types |
| location_mismatch | onsite/hybrid job whose location isn't within any preferred location (country match + city/region match or haversine ≤ radius) |
| seniority_gap | job seniority more than 2 levels above the resume seniority, or `min_years - resume_years > 3` |
| salary_below_floor | job salary_max known and < salary_min (unknown salary never filters) |
| stale | posted_at older than `posted_within_days` |

Then compute `similarity = 1 - cosine_distance(resume.embedding, job.embedding)` (in SQL via pgvector `<=>` for efficiency), and keep the top **N** (default 30, `scoring.yaml`) among those that passed. Store stage-1 rows for all (including filtered ones, so the UI can show "12 hidden by filters" with reasons).

### 8.5 Stage 2: LLM scoring

- Input: the trimmed resume profile (no contact info: name, email and phone are removed before any scoring/generation call where they're not needed), job fields + description (≤6k chars), and user preferences relevant to fit.
- Prompt `match_score/v1` asks for sub-scores **with rubric anchors** (e.g. skills_match: 90+ = has ≥90% of required skills; 50 = about half...), plus matched/missing skills (must be drawn from the job's skills list), red flags, `why_good_fit` (2 sentences), and `apply_recommendation`.
- Schema = the spec's JSON **minus** trust in `overall_score`: if the LLM returns it, it's ignored.
- **In code** (`domain/scoring.py`):

```python
WEIGHTS_V1 = {"skills_match": .35, "experience_match": .25, "seniority_fit": .15,
              "domain_relevance": .15, "location_fit": .10}

overall = round(sum(breakdown[k] * w for k, w in WEIGHTS.items()))
# deterministic adjustments
breakdown["location_fit"] = compute_location_fit(job, prefs)   # overrides LLM
overall -= penalty_for_red_flags(red_flags)                       # e.g. -5 per high-severity, capped -15
overall = clamp(overall, 0, 100)

recommendation = band(overall, red_flags)  # ≥80 strong_apply, 65–79 apply, 50–64 stretch, <50 skip
# a hard blocker red flag (e.g. requires security clearance / citizenship the user lacks) caps at "stretch"
```

- Deterministic red flags are added in code (years gap, seniority gap, salary below floor, visa/clearance keywords), merged with LLM flags and deduplicated by code.
- **Validation**: sub-scores clamped 0–100; `matched_skills ∩ missing_skills = ∅`; matched skills must exist in the resume skill index (fuzzy ≥ 90) or they are moved to missing.
- **Caching**: `UNIQUE(job_id, resume_id, profile_version)`. Before calling the LLM, look up existing rows and skip them. A weights change (`weights_version`) recomputes `overall_score` from the stored breakdown **without** LLM calls.
- **Concurrency**: a Celery `group` of scoring tasks, chunked 5 per task; per-user concurrency 3; global LLM rate limiter (Redis token bucket).
- A failure on one job → `stage=score_failed`. The job is shown with the stage-1 similarity as "Not scored yet, retry".

### 8.6 Application generation

Endpoint: `POST /jobs/{id}/prepare-application {kinds: [email, cover_letter, resume_tweaks], tone}`.

1. Contact discovery (§13.3), done first so the UI knows whether "Send via Gmail" is available.
2. Build a **fact sheet** from the profile: an allowlisted set of facts (skills, titles, companies, dates, project names, every bullet verbatim, numbers present in the resume). This sheet is the *only* resume content passed to generation prompts.
3. Generation prompts include `_shared/guard.md`:
   - "Use only facts in FACT_SHEET. Do not add skills, employers, titles, metrics, numbers, certifications or degrees not present. If the job requires something the candidate lacks, do not claim it; you may express eagerness to learn."
4. Constraints:
   - **Email**: ≤150 words (enforced in code; if over, one automatic "shorten" retry, then truncate at a sentence boundary with a warning). Subject = exactly `Application: {Job Title}, {Name}`, set **in code**, not by the LLM. It must reference 2–3 matched skills, one concrete project/achievement, and one job-specific detail. The output includes `references: {skills:[], achievement_ref:"bullet id", job_detail:"quoted phrase"}` so these can be validated.
   - **Cover letter**: 250–350 words, same structure, validated in code with one retry.
   - **Resume tweaks**: 3–5 items `{original_bullet_id, original, suggested, rationale, emphasized_skills}`. `original` must match a resume bullet exactly.
5. **Guardrail validation** (`domain/guardrails.py` + `claim_verify/v1`):
   - Deterministic checks:
     - every number/percentage/currency in the output must appear in the fact sheet (normalized: `40%`, `40 percent`);
     - every skill/technology token (dictionary-matched) must be in the resume skills index **or** be quoted as a job requirement without a claim of possession ("your use of Kafka" is OK; "my Kafka experience" is not; the LLM verifier handles that nuance);
     - company names / job titles mentioned must be in work history or be the target company;
     - degrees and certifications must exist.
   - LLM verifier: extracts claims about the candidate as `[{claim, supporting_quote}]`; each `supporting_quote` must fuzzy-match (rapidfuzz partial_ratio ≥ 85) a fact-sheet line. Unsupported claims → flags.
   - Output: `guardrail_report.claims[]`, with each flag highlighted inline in the editor. Severity `block` (fabricated number/skill/employer) or `warn` (vague/unverifiable phrasing).
   - **Send/Copy requires** that all `block` flags are resolved (edited away; re-validation runs on save, deterministically, in <100 ms) or explicitly acknowledged with a checkbox "I confirm this is accurate".
6. **Tone regenerate**: formal / friendly / concise. Each regeneration creates a new `application_drafts` row; the user can switch between versions.
7. User edits re-run the deterministic guardrails (cheap) on save; the LLM verifier runs again only on explicit "Re-check".

### 8.7 Prompt management

- Files: `app/prompts/<name>/v<N>.md`, with YAML front-matter:
  ```yaml
  ---
  id: match_score
  version: 1
  model_tier: smart          # smart | fast
  temperature: 0.1
  max_tokens: 1200
  schema: v1.schema.json
  includes: [_shared/guard.md]
  ---
  ```
- Jinja2 rendering with `StrictUndefined`. Variables are wrapped in XML-style tags (`<resume>…</resume>`, `<job>…</job>`) and the system prompt states that tag contents are **data, not instructions** (prompt-injection defence for scraped descriptions).
- `prompts/registry.py` loads all prompts at startup and validates the front-matter and schemas. Active versions are pinned in config (`PROMPT_VERSIONS__MATCH_SCORE=1`).
- Every stored AI output records `prompt_version` + `model`.
- A prompt change = a new file + an eval run (§19.4); old versions remain for reproducibility.

---

## 9. Job discovery and scraping

### 9.1 `JobSource` interface

```python
@dataclass(frozen=True)
class SourceQuery:
    search_term: str               # one per target title
    location: str | None
    is_remote: bool | None
    posted_within_hours: int
    results_wanted: int
    country: str                   # for Indeed/Glassdoor country param

@dataclass
class RawJob:
    source: str; source_job_id: str; url: str; apply_url: str | None
    title: str; company: str; company_url: str | None
    location: str | None; is_remote: bool | None
    description: str | None; description_format: Literal["html", "markdown", "text"]
    posted_at: datetime | None
    salary_min: float | None; salary_max: float | None; salary_currency: str | None; salary_period: str | None
    job_type: str | None; emails: list[str]

class JobSource(Protocol):
    name: str                      # "linkedin", "indeed", "glassdoor", "google", "serpapi"
    rate_limit: RateLimit          # e.g. 1 request / 10 s, burst 1
    def is_configured(self) -> bool: ...
    def fetch(self, query: SourceQuery) -> Iterable[RawJob]: ...
```

### 9.2 JobSpy adapter

- One `JobSpySource` instance per site (`linkedin`, `indeed`, `glassdoor`, `google`) so each one is independently toggleable, rate-limited and reported.
- Calls `jobspy.scrape_jobs(site_name=[site], search_term=..., location=..., results_wanted=..., hours_old=..., is_remote=..., country_indeed=..., linkedin_fetch_description=True, description_format="markdown")`. For Google, it builds `google_search_term` ("{title} jobs near {location} since last week").
- Query fan-out: `target_titles × locations` (capped, default max 6 queries per source per run), with remote-only searches for remote preferences.
- Known behaviour to design around:
  - LinkedIn rate-limits aggressively (page ~10 often triggers 429): keep `results_wanted` ≤ 50 and add delays. Optional proxies via `JOBSPY_PROXIES`.
  - Glassdoor/Google are the flakiest; treat failures as normal (`partial` run status).
  - The library is sync/blocking, which is fine inside Celery (`scrape` queue, concurrency 2).
- Per-source **circuit breaker** in Redis: after 3 consecutive failed runs, the source is auto-paused for 1 hour and Settings shows "LinkedIn temporarily unavailable".
- No credentials, no logins, public listings only.

### 9.3 SerpAPI adapter

- `engine=google_jobs`, paginated via `next_page_token`; used when `SERPAPI_KEY` is set and (a) the user enabled it, or (b) automatically as a fallback when the JobSpy `google` source fails.
- Results map to `RawJob`; `apply_options` give apply URLs.

### 9.4 Run orchestration

```
run_search(run_id)
  └─ chord(
       group(scrape_source.s(run_id, src) for src in enabled_sources),   # each: fetch → store raw → normalize_and_store
       finalize_scrape.s(run_id)                                          # counts, embed missing jobs
     )
     → match_stage1.s(run_id)
     → group(score_chunk.s(run_id, ids) for ids in chunks(stage1_kept, 5))
     → finalize_run.s(run_id)                                             # status, notifications, sheets sync, digest flags
```

- Progress is written to `search_runs.progress/stage_detail` (scraping 0–40%, normalize 40–55%, stage 1 55–60%, scoring 60–100%).
- One active run per user (Redis lock + DB check). `POST /searches` returns `409` with the existing run_id if one is running.
- Cancel: `POST /searches/{id}/cancel` revokes pending tasks; completed parts are kept.
- Each run has a time limit of 15 min (soft) / 20 min (hard).

---

## 10. Background jobs (Celery)

### 10.1 Queues and workers

| queue | tasks | concurrency (default) |
|---|---|---|
| `default` | resume parse/embed, notifications, maintenance | 4 |
| `scrape` | scrape_source | 2 (polite) |
| `llm` | normalize, score_chunk, generate, verify, classify | 6 |
| `email` | send_application_email, digest | 2 |
| `sync` | sheets_sync, check_replies | 2 |

In dev, one worker consumes all queues; prod can split them.

Settings: `task_acks_late=True`, `task_reject_on_worker_lost=True`, `worker_prefetch_multiplier=1`, JSON serializer only, `result_expires=1d`, visibility timeout > the longest countdown.

### 10.2 Task catalogue

| task | trigger | idempotency |
|---|---|---|
| `parse_resume(resume_id)` | upload | no-op if status ≠ uploaded/failed |
| `embed_resume(resume_id, profile_version)` | parse / edit | skip if the embedding is for the same version |
| `run_search(run_id)` | API / scheduler | status gate |
| `scrape_source(run_id, source)` | run | `search_run_sources` status gate |
| `normalize_jobs(job_ids)` | scrape | `normalization_status` gate |
| `embed_jobs(job_ids)` | normalize | null-embedding filter |
| `match_stage1(run_id)` | chain | upsert |
| `score_chunk(run_id, match_ids)` | chain | skip already scored |
| `generate_application(app_id, kinds, tone)` | API | creates new drafts (by design) |
| `send_application_email(app_id)` | send | status must be `queued`; Redis lock per app; checks `gmail_message_id` is null |
| `check_replies()` → `check_user_replies(user_id)` | beat 15 min | Gmail historyId cursor |
| `follow_up_reminders()` | beat hourly | `follow_up_at` + notification uniqueness |
| `scheduled_searches()` | beat every 15 min | per user per day key `sched:{user}:{date}` |
| `sheets_sync(user_id)` | debounced (5 min) after changes + manual | full upsert by id |
| `daily_digest()` | beat hourly (sends at user-local 18:00) | per user per day key |
| `expire_jobs()` | beat daily | |
| `purge_deleted_accounts()` | beat hourly | |
| `refresh_usage_aggregates()` | beat hourly | |

---

## 11. REST API (`/api/v1`)

All responses are JSON. Errors use RFC 9457 `application/problem+json` with `code`, `title`, `detail` and `errors[]`. Lists use cursor pagination (`?cursor=&limit=`, returning `{items, next_cursor}`).

### Auth & account
| method | path | purpose |
|---|---|---|
| POST | `/auth/signup` | email + password → sends verification email |
| POST | `/auth/verify-email` | token |
| POST | `/auth/login` | sets `access_token` + `refresh_token` cookies |
| POST | `/auth/refresh` | rotates refresh |
| POST | `/auth/logout` | revokes the family |
| POST | `/auth/password/forgot`, `/auth/password/reset` | |
| GET | `/auth/google/start` | redirect to Google (login scopes) |
| GET | `/auth/google/callback` | creates/links the user, sets cookies |
| GET | `/users/me` | profile, onboarding step, flags |
| PATCH | `/users/me` | name, timezone, daily_send_cap, follow_up_days |
| GET | `/users/me/export` | JSON export of all user data (zip) |
| DELETE | `/users/me` | requires password/re-auth; schedules a purge (immediate soft-lock) |

### Resumes
| method | path | purpose |
|---|---|---|
| POST | `/resumes` | upload (multipart) → 202 |
| GET | `/resumes` | versions list |
| GET | `/resumes/{id}` | status + profile |
| PATCH | `/resumes/{id}/profile` | user edits (full profile body, validated) |
| POST | `/resumes/{id}/activate` | set active |
| POST | `/resumes/{id}/reparse` | re-run parsing |
| GET | `/resumes/{id}/file` | download original (decrypted stream) |
| DELETE | `/resumes/{id}` | |

### Preferences
| GET / PUT | `/preferences` | full replace with validation |

### Searches
| method | path | purpose |
|---|---|---|
| POST | `/searches` | start a run → `202 {run_id}`; `409` if one is active; `402` if over budget |
| GET | `/searches/{id}` | status, progress, stage_detail, counts, per-source results |
| GET | `/searches` | recent runs |
| POST | `/searches/{id}/cancel` | |
| GET | `/searches/estimate` | estimated LLM cost of a run |

### Jobs & matches
| method | path | purpose |
|---|---|---|
| GET | `/jobs` | feed: `min_score, recommendation[], source[], remote_type[], posted_after, q, include_filtered, sort(score|posted|similarity)` |
| GET | `/jobs/{id}` | job + company + match + application summary |
| POST | `/jobs/{id}/dismiss` / `/undismiss` | |
| POST | `/jobs/{id}/rescore` | force re-score for the current profile (costs budget) |
| POST | `/jobs/{id}/prepare-application` | `{kinds, tone}` → application + drafts + guardrails + contact |
| POST | `/jobs/{id}/save` | creates an application in `saved` |

### Applications
| method | path | purpose |
|---|---|---|
| GET | `/applications` | grouped by status (board) or a list |
| GET | `/applications/{id}` | full, with drafts + events |
| PATCH | `/applications/{id}` | edit subject/body/cover letter/notes/contact_email (re-runs deterministic guardrails) |
| POST | `/applications/{id}/regenerate` | `{kind, tone}` |
| POST | `/applications/{id}/verify` | re-run the LLM claim verifier |
| POST | `/applications/{id}/acknowledge-flags` | |
| POST | `/applications/{id}/send` | `Idempotency-Key` header; validations; → `202 {scheduled_send_at}` |
| POST | `/applications/{id}/cancel-send` | while queued |
| POST | `/applications/{id}/mark-applied-on-site` | after the site flow |
| POST | `/applications/{id}/status` | `{to_status, position}` (kanban moves) |
| POST | `/applications/{id}/follow-up-draft` | generate a follow-up email (sending is a separate click) |
| DELETE | `/applications/{id}` | |

### Integrations
| method | path | purpose |
|---|---|---|
| GET | `/integrations` | status for gmail and sheets |
| GET | `/integrations/{provider}/connect` | returns the Google consent URL (incremental scopes, `state` signed + PKCE) |
| GET | `/integrations/{provider}/callback` | stores encrypted tokens |
| DELETE | `/integrations/{provider}` | revokes at Google + deletes tokens |
| POST | `/integrations/sheets/sync` | manual full sync |
| POST | `/integrations/sheets/create` | create a new spreadsheet, or link an existing one by URL |

### Dashboard / usage / notifications / health
| GET | `/dashboard/stats?range=30d` | jobs found, avg score, applied, reply rate, interviews, funnel |
| GET | `/dashboard/missing-skills?top=10` | aggregated across top matches |
| GET | `/dashboard/applications-over-time?interval=week` | |
| GET | `/usage` | month to date, budget, by feature, daily series |
| GET | `/notifications`, POST `/notifications/read` | |
| GET | `/health/live`, `/health/ready` | ready checks DB + Redis |

OpenAPI: `/api/v1/openapi.json`, with docs at `/api/docs` (disabled in prod or behind auth). Every route has an `operation_id` set (e.g. `jobs_list`) so the orval hook names are stable.

---

## 12. Authentication, authorization, sessions

- **Why backend-owned auth instead of NextAuth**: Celery tasks, Gmail/Sheets tokens and the user table live in the backend. NextAuth would add a second session system and require syncing users. A single FastAPI auth keeps one source of truth. (This deviation is recorded in ADR-0001.)
- **Cookies, same-origin**: the Next.js app proxies `/api/v1/*` to the API (`next.config.mjs` rewrites), so the browser only ever talks to the web origin. Cookies are first-party: `HttpOnly; Secure; SameSite=Lax; Path=/`.
  - `access_token`: JWT (HS256 or EdDSA), 15 min, claims `sub, sid, exp, iat, ver`.
  - `refresh_token`: opaque random 256-bit, 30 days, rotating, hashed in DB, `Path=/api/v1/auth`.
- **CSRF**: double-submit token (`csrf_token` cookie, readable, + `X-CSRF-Token` header) on all state-changing requests, in addition to SameSite=Lax.
- **Server components**: Next.js RSC fetches forward the cookies to the API (`headers()` → `cookie`) for SSR data; client components use the generated hooks.
- **Google login**: Authlib, `openid email profile`, `state` + PKCE + nonce. Links to an existing user if the verified email matches (only when Google says `email_verified=true`).
- **Authorization**: every query is scoped by `user_id` from the token at the repository layer (`for_user(user_id)` helpers). Integration tests assert cross-user access returns 404.
- **Rate limits**: login 10/min/IP, signup 5/h/IP, upload 10/h/user, prepare-application 30/h/user, searches 6/h/user.
- Passwords: argon2id; min length 10; checked against a breached-password top list (local file).

---

## 13. Integrations: Gmail, Sheets, Hunter

### 13.1 Gmail

- Separate OAuth connect flow (incremental authorization) with scopes `gmail.send` and `gmail.readonly`, `access_type=offline`, `prompt=consent`. Tokens are encrypted (🔒) in `integrations`.
- ⚠️ **Google verification**: `gmail.readonly` is a *restricted* scope, and `gmail.send` is *sensitive*. While the OAuth app is in "Testing" mode it works for up to 100 named test users; tokens expire every 7 days. Production use requires Google OAuth verification and, for restricted scopes, an annual third-party security assessment (CASA). Plan: build and run in Testing mode; reply detection is designed so it can be disabled to drop `gmail.readonly` if verification is impractical (then only `gmail.send` + a manual "mark replied").
- **Send**: build MIME with `email.message.EmailMessage`: From = the connected address, To = contact, Subject, plain-text body (plus a simple HTML alternative), attachment = active resume original file (decrypted in memory, filename `Firstname_Lastname_Resume.pdf`). `users.messages.send` → store `id`, `threadId`.
- **Cap + delay**: an atomic Redis `INCR sends:{user}:{yyyy-mm-dd(user tz)}` with expiry, checked against `daily_send_cap` **at enqueue and again at send time**, and reconciled with `email_send_log`. Countdown = `random.uniform(30, 120)` s, and sends from the same user are spaced ≥30 s apart (a Redis "next allowed send" timestamp per user).
- **Token refresh**: google-auth refresh. On `invalid_grant` → integration `needs_reauth`, application → `ready` with error, notification + toast.
- **Reply detection**: every 15 min, per connected user, call `users.history.list(startHistoryId)` with `historyTypes=messageAdded`. For new messages in threads that match `applications.gmail_thread_id` and not from the user's own address:
  1. `last_reply_at` is set; status `applied → replied` automatically (event actor = `gmail`).
  2. `reply_classify/v1` (haiku, first 2k chars of the reply, PII-trimmed) → `interview | rejection | positive | auto_reply | other`. `auto_reply` doesn't change the stage. `interview`/`rejection` with confidence ≥ 0.8 move the stage automatically; otherwise they're shown as a suggestion chip on the card ("Looks like an interview invite, move?").
  3. Notification created.
  - Fallback if the `historyId` is too old (404): a full scan of tracked threads via `threads.get`.
  - Site applications: optional matching by sender domain = company domain in the last 14 days, as a suggestion only (never auto-move).

### 13.2 Google Sheets

- Scopes: `https://www.googleapis.com/auth/drive.file` (only files the app creates/opens) + `spreadsheets`. Prefer `drive.file`-only access to the app-created sheet to avoid a broad scope.
- "Connect Sheets" → create a spreadsheet "JobPilot AI Tracker" with tabs **Jobs** and **Applications**, frozen header rows, and basic formatting.
- Columns:
  - Jobs: `job_id, title, company, location, remote, source, score, recommendation, posted_at, url, discovered_at, status`
  - Applications: `application_id, job_title, company, channel, contact_email, status, sent_at, last_reply_at, follow_up_at, url, notes(optional)`
- Sync algorithm: read column A (ids) once → map id→row; build `batch_update` for changed rows + `append_rows` for new ones; ≤ 1 call per tab per sync. Debounced: changes enqueue `sheets_sync(user)` with a 5-min countdown and a dedupe key. Backoff on 429 (Sheets quota: 60 writes/min/user).
- The Sheet is a mirror, so edits made in the sheet are **not** read back. This is stated in the UI.

### 13.3 Contact discovery

```
1. job.contact_emails (regex over description) → pick the best (prefer careers@/jobs@/recruiting@/hr@ or a personal-looking name)
     → source=job_description, confidence=90
2. company domain (from the company_url / apply_url host when it isn't an ATS host like greenhouse.io, lever.co, myworkdayjobs.com; else Hunter domain lookup by company name)
3. if HUNTER_API_KEY: Hunter domain-search (department=hr/recruiting, type=personal|generic) → highest-confidence result
     → source=hunter_domain, confidence=Hunter score
   cached in company_contacts for 30 days (shared across users)
4. else → channel=site, UI shows "No email found, apply on site."
```
The user can always type or override a contact email (`source=manual`).

---

## 14. Frontend design

### 14.1 Global
- App shell: a collapsible sidebar (Jobs, Applications, Dashboard, Settings), a top bar with the search-run indicator, notifications bell, theme toggle and user menu.
- Dark mode via `next-themes` (class strategy), with all colors from shadcn CSS variables.
- Data: TanStack Query with sensible `staleTime` (feed 30 s, job 60 s), optimistic updates on kanban moves/dismiss, and `refetchInterval` while a run or parse is in progress.
- Feedback: skeletons for every list/detail; empty states with a primary action; sonner toasts for success/error; error boundaries per route.
- Forms: react-hook-form + zod (zod schemas generated by orval from OpenAPI where possible).
- Accessibility: keyboard-navigable kanban (dnd-kit keyboard sensor), focus rings, aria labels, WCAG AA contrast in both themes.
- Responsive: the kanban becomes a horizontal scroll with snap on mobile; the job detail stacks vertically.

### 14.2 Pages

**`/onboarding`** (stepper, resumable via `users.onboarding_step`)
1. Upload: dropzone (PDF/DOCX ≤5 MB) → parsing progress (statuses) → errors with a retry.
2. Review profile: editable sections (header/contact, summary, skills as editable chips with category + proficiency selects, experience entries with editable bullets, education, projects, certifications, preferred roles). "Looks good" saves.
3. Preferences: titles (chips, prefilled from preferred_roles), locations (autocomplete text + country), remote toggles, experience levels, salary floor, include/exclude keywords, excluded companies, sources (toggles with the scraping notice), daily search toggle + hour.
4. Integrations: Gmail and Sheets connect cards (each skippable) → "Find my first jobs" kicks off a run → redirect to `/jobs`.

**`/jobs`**
- Header: "Find jobs" button → a progress card (stage text, progress bar, per-source chips ok/failed/running; cancel).
- Filters bar: min score slider, recommendation multi-select, source, remote type, posted date, keyword search, "show filtered-out" toggle.
- Sort: score / newest / similarity.
- `JobCard`: title, company + logo, location/remote, salary if known, posted ago, score ring (color-coded), recommendation badge (Strong apply / Apply / Stretch / Skip), the `why_good_fit` sentence, 3 matched skill chips, a red-flag count, source icons, actions (Save, Dismiss, Open).
- Infinite scroll (cursor).

**`/jobs/[id]`**
- Left: description (sanitized HTML), company card, sources/links.
- Right: score summary, a breakdown **radar or horizontal bar chart** (Recharts), matched skills (green chips), missing skills (amber chips), red flags list with severity, the why-good-fit text, the hard-filter result.
- **Prepare application panel**:
  - Contact: found email + source + confidence badge, or "No email found, apply on site" + manual entry.
  - Tabs: Email | Cover letter | Resume tweaks. Tone selector + Regenerate. Version switcher.
  - Editor (textarea with a word counter and inline guardrail highlights; flags list with "Fix" / "Acknowledge").
  - Actions:
    - **Send via Gmail** (disabled with a tooltip reason when there's no contact, Gmail is disconnected, the cap is reached, or flags are unacknowledged) → **SendPreviewDialog**: from, to, subject, body, attachment name, remaining sends today, the "Will send in ~30–120 s; you can cancel" note, checkbox "I reviewed this email" → Confirm.
    - **Apply on site** → copies the cover letter to the clipboard, opens `apply_url` in a new tab, shows a checklist drawer ("Paste cover letter in 'Cover letter' field", "Upload resume: <filename> (download)", "Answer: years of experience = X", "Mark as applied when done").
    - **Save for later**.
  - Resume tweaks: a side-by-side original vs suggested view with a copy button per item.

**`/applications`**
- Kanban columns: Saved → Applied → Replied → Interview → Offer / Rejected (Offer and Rejected are the final columns, shown side by side).
- Card: company, title, channel icon, days since applied, follow-up due badge, reply badge, suggestion chip.
- Drag-and-drop between and within columns (dnd-kit sortable) → optimistic `POST /status` with fractional `kanban_position`.
- The card opens a drawer: timeline (`application_events`), sent email (read-only), notes, follow-up draft button, links.

**`/dashboard`**
- Stat cards: jobs found (30d), avg match score, applied, reply rate (replied/applied by email), interviews.
- Top missing skills: horizontal bar chart + "learning recommendation" text (the stretch skill-gap coach later).
- Applications over time: stacked bar/line by week (applied, replied, interviews).
- Funnel: discovered → saved → applied → replied → interview → offer.

**`/settings`** (tabs)
- Profile & account (name, timezone), Preferences (same form), Resume versions (list, activate, re-upload, download, delete), Integrations (Gmail, Sheets, Hunter key status; connect/disconnect/sync now), Sending limits (daily cap, follow-up days), AI usage (month-to-date cost vs budget meter, by-feature breakdown, daily chart), Scraping notice (toggle sources + the disclaimer text), Danger zone (export data, delete account with typed confirmation).

---

## 15. Safety, compliance, privacy

| Requirement | Implementation |
|---|---|
| Human-in-the-loop sending | The only path to Gmail send is `POST /applications/{id}/send`, which requires: a session cookie + CSRF, an idempotency key, `preview_confirmed=true` in the body (only set by the preview dialog), and flags resolved. No scheduled or bulk send code exists; follow-ups are drafts only. A test asserts that no task calls `gmail.send` except `send_application_email`, and that it refuses unless the status is `queued`, which only the endpoint can set. |
| Daily send cap | Default 25, configurable per user ≤ `MAX_DAILY_SEND_CAP` (env, default 50). Checked at enqueue + send. |
| Random delay | 30–120 s countdown + ≥30 s spacing per user. The user can cancel during the delay. |
| Scraping etiquette | No logins/credentials; public listings only; per-source rate limits + exponential backoff + circuit breaker; sources toggleable; a Settings notice: *"Job sources are accessed from public listings and may break without notice. You are responsible for complying with each site's terms of service."* |
| No auto form filling | The apply-on-site flow only opens the URL + clipboard + checklist. No browser automation exists in the codebase. |
| Encryption at rest | Files: AES-256-GCM with per-file DEKs wrapped by the master key. Text fields/tokens: MultiFernet (`ENCRYPTION_KEYS` comma list, first = active; `rotate_keys.py` re-encrypts). Plus DB/storage provider encryption. |
| No resume data in logs | A structlog processor drops known keys (`raw_text, profile, body, cover_letter, email, phone, token, password`) and regex-redacts emails/phones in messages. LLM request/response bodies are never logged (only ids, token counts, latency). Sentry `before_send` scrubs too. |
| Account deletion | `DELETE /users/me` → immediately revokes sessions, disconnects + revokes Google tokens, sets `deletion_requested_at`, and the purge task (≤1 h) deletes storage objects and then the `users` row (cascade). Global `jobs` remain (not personal data). Usage events are deleted with the user. The user is told that the Google Sheet they own is not deleted. |
| Data export | JSON zip of the profile, preferences, matches, applications and events. |
| Prompt injection | Scraped descriptions are wrapped as data; the model is told to ignore instructions inside them. Outputs are schema-validated; generation can't trigger actions. |
| Uploads | Size/type/magic-byte checks, a page limit of 10, parsed in the worker (not the API process). Library-based parsing only; macros are never executed. |
| Security headers | CSP, HSTS, X-Frame-Options DENY, Referrer-Policy, via `next.config` and the API middleware. |

---

## 16. AI cost controls

- `config/models.yaml` holds per-model prices (input/output/cache per 1M tokens). These values are maintained by the operator; they are **not hardcoded in code**.
- `UsageService.guarded_call()`:
  1. Estimate the cost (input tokens via a tokenizer approximation × price + max_tokens × output price).
  2. If `month_to_date + estimate > budget` → raise `BudgetExceeded` (API → 402 problem+json `budget_exceeded`; tasks mark the match `score_failed` with reason `budget`).
  3. After the call, record actual usage from the provider response.
- Warnings: notifications at 80% and 100% of budget.
- Pre-run estimate: `GET /searches/estimate` (≈ new jobs × normalize cost + N × score cost) is shown on the Find jobs button tooltip.
- Savings levers: rules-before-LLM normalization, batching, stage-1 filtering to N, a per-(resume version, job) score cache, prompt caching on static system prompts, the haiku tier for extraction, and truncated descriptions.
- Admin-level global daily ceiling (`GLOBAL_DAILY_AI_BUDGET_USD`) as a kill switch.

---

## 17. Observability, reliability, error handling

- **Logging**: structlog JSON with `request_id` (middleware, propagated into Celery headers), `user_id` (as a uuid, not an email), `task_id`, `run_id`, durations.
- **Metrics** (optional Prometheus `/metrics` in phase 8): run durations, source success rate, LLM latency/tokens/cost, send success, queue depth.
- **Tracing**: optional OpenTelemetry (FastAPI + Celery + httpx instrumentation) later.
- **Retries**: tenacity presets per integration (LLM 3x, sources 3x with longer backoff, Gmail 4x on 429/5xx, Sheets 5x on 429). Celery `autoretry_for` with `retry_backoff=True, retry_jitter=True`.
- **Graceful degradation**: a failed source → run `partial`; a failed LLM score → a stage-1-only card; Hunter down → apply-on-site; Gmail token revoked → needs_reauth state; Redis down → API returns 503 on enqueueing endpoints but reads still work.
- **Health**: `/health/live` (process), `/health/ready` (DB, Redis); Celery worker heartbeat key checked by `/health/ready?deep=1`.
- **Backups**: managed Postgres PITR; a storage bucket with versioning.

---

## 18. Configuration and environment variables

`.env.example` (grouped):

```dotenv
# --- Core ---
ENV=development                     # development | test | production
APP_BASE_URL=http://localhost:3000  # web origin (used for OAuth redirects and links)
API_INTERNAL_URL=http://api:8000    # used by Next.js rewrites/SSR
SECRET_KEY=change-me                # JWT signing
ENCRYPTION_KEYS=                    # comma-separated Fernet keys; first is active
FILE_MASTER_KEY=                    # base64 32 bytes for AES-GCM key wrapping
CORS_ORIGINS=http://localhost:3000

# --- Database / Redis ---
DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@postgres:5432/jobpilot
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# --- Storage ---
STORAGE_BACKEND=local               # local | s3
LOCAL_STORAGE_PATH=/data/uploads
S3_BUCKET=
S3_REGION=
S3_ENDPOINT_URL=                    # for R2/MinIO
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=

# --- AI ---
LLM_PROVIDER=anthropic              # anthropic | openai
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
EMBEDDING_PROVIDER=fastembed        # fastembed | openai
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DIM=768
DEFAULT_MONTHLY_AI_BUDGET_USD=5
GLOBAL_DAILY_AI_BUDGET_USD=50
STAGE1_TOP_N=30

# --- Sources ---
SOURCES_ENABLED=linkedin,indeed,glassdoor,google
SERPAPI_KEY=
JOBSPY_PROXIES=                     # optional, comma-separated
SOURCE_MAX_QUERIES_PER_RUN=6
JOB_TTL_DAYS=30

# --- Google OAuth ---
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_LOGIN_REDIRECT_URI=http://localhost:3000/api/v1/auth/google/callback
GOOGLE_INTEGRATION_REDIRECT_URI=http://localhost:3000/api/v1/integrations/{provider}/callback

# --- Contact discovery ---
HUNTER_API_KEY=

# --- Sending ---
DEFAULT_DAILY_SEND_CAP=25
MAX_DAILY_SEND_CAP=50
SEND_DELAY_MIN_SECONDS=30
SEND_DELAY_MAX_SECONDS=120
DEFAULT_FOLLOW_UP_DAYS=7

# --- Transactional email ---
MAIL_BACKEND=console                # console | resend | smtp
RESEND_API_KEY=
SMTP_URL=
MAIL_FROM="JobPilot AI <noreply@example.com>"

# --- Observability ---
LOG_LEVEL=INFO
SENTRY_DSN=

# --- Frontend ---
NEXT_PUBLIC_APP_NAME=JobPilot AI
```

---

## 19. Testing strategy and eval set

### 19.1 Backend unit (pure domain, fast, run on every commit)
- `test_scoring.py`: weighted sum, clamping, red-flag penalties, banding boundaries (79/80, 64/65, 49/50), blocker caps, weight version recompute.
- `test_filters.py`: each hard filter, including edge cases (unknown remote type never filters; unknown salary never filters; haversine radius).
- `test_dedupe.py`: company suffix stripping, title normalization (`Sr. Software Engineer (Remote) - REQ123` ≡ `Senior Software Engineer`), URL canonicalization, near-duplicate merge.
- `test_extraction_rules.py`: salary/years/emails/remote regex fixtures (≥30 cases).
- `test_guardrails.py`: fabricated number detected, fabricated skill detected, job-skill mention vs. claim, numbers in different formats, acceptable paraphrases pass, word-count limits, the subject format.
- `test_seniority.py`, `test_skills.py` (canonicalization), `test_crypto.py` (round trip, rotation).

### 19.2 Integration (Postgres via testcontainers with the pgvector image; Redis fake or container; Celery `task_always_eager`)
- Resume pipeline with `FakeLLM` returning fixture JSON.
- Search pipeline with `FakeJobSource` (incl. one failing source → `partial`).
- Matching pipeline: cache hits avoid LLM calls (assert the call count).
- Send flow: cap enforcement, idempotency, cancel during the delay, Gmail mocked via respx, attachment present in the MIME.
- Reply detection with recorded Gmail history fixtures.
- Sheets sync upsert logic with a fake gspread client.

### 19.3 API tests (httpx AsyncClient)
- Auth flows, cookie/CSRF behaviour, refresh rotation + reuse detection.
- Cross-user isolation (404s).
- Each endpoint's happy path + main errors (409 active run, 402 budget, 422 validation, 429 rate limit).
- Account deletion purges everything (row counts = 0 for the user, storage objects gone).

### 19.4 Eval set (`backend/evals/`)
- 10 anonymized resume/job pairs spanning: strong fit, near fit, seniority overreach, career switcher, missing must-have skill, location mismatch (remote vs onsite), domain mismatch, junior vs senior, overqualified, keyword-stuffed job.
- Each case: `expected_overall: [min, max]`, `expected_recommendation: [allowed values]`, `must_include_missing: [...]`, `must_flag: [...]`.
- `run_eval.py` runs the real provider (needs an API key), prints a table, writes `evals/results/<date>.json`, and exits non-zero if any case is out of range. It runs in `eval.yml` (manual dispatch + nightly), not in PR CI, to avoid cost/flakiness. It also includes 5 generation-guardrail cases that check emails contain no fabricated claims.

### 19.5 Frontend
- vitest + Testing Library: ScoreBadge banding, SendPreviewDialog gating logic, GuardrailFlags, KanbanBoard reorder reducer, form validation.
- Playwright smoke (against docker compose with fake providers via `ENV=e2e`): signup → upload fixture resume → review → preferences → run search (fake source) → open a job → prepare application → apply on site → see the card in kanban.

### 19.6 Quality gates in CI
- Backend: `ruff check`, `ruff format --check`, `mypy app` (strict for `domain/`, `providers/`, `services/`), `pytest --cov` (≥80% on `domain/`).
- Frontend: `eslint`, `tsc --noEmit`, `vitest run`, `next build`.
- OpenAPI drift: export the schema → regenerate the client → `git diff --exit-code frontend/src/api/generated`.

---

## 20. DevOps: Docker, CI, deployment

### 20.1 Docker Compose (dev)

| service | image / build | ports | notes |
|---|---|---|---|
| postgres | `pgvector/pgvector:pg16` | 5432 | volume `pgdata`; init script `CREATE EXTENSION vector, citext, pg_trgm` |
| redis | `redis:7-alpine` | 6379 | |
| api | `backend/Dockerfile` | 8000 | `uvicorn app.main:app --reload` in dev; runs `alembic upgrade head` on start (dev only) |
| worker | same image | | `celery -A app.tasks.celery_app worker -Q default,scrape,llm,email,sync -l info` |
| beat | same image | | `celery -A app.tasks.celery_app beat` |
| web | `frontend/Dockerfile` | 3000 | `pnpm dev` |
| flower (profile dev) | `mher/flower` | 5555 | |
| mailpit (profile dev) | `axllent/mailpit` | 8025 | catches transactional mail |
| minio (profile s3) | `minio/minio` | 9000/9001 | test S3 locally |

> **Windows note**: Celery doesn't officially support Windows, so the worker/beat always run in Docker (Docker Desktop + WSL2 backend). The `fastembed` model is downloaded at image build time and cached in a volume.

### 20.2 GitHub Actions `ci.yml`
- Triggers: PR + push to main.
- Jobs: `backend` (services: pgvector postgres, redis; uv sync; lint, type, test), `frontend` (pnpm install; lint, typecheck, test, build), `openapi-drift`, and `docker-build` (build images, no push, on main only).
- Caching: uv cache, pnpm store.

### 20.3 Production deployment
| part | target | notes |
|---|---|---|
| web | Vercel | env `API_INTERNAL_URL` → API public URL; rewrites keep cookies first-party |
| api | Railway / Render / Fly (Docker) | ≥2 instances; `alembic upgrade head` as a release command |
| worker, beat | same platform, separate services from the same image | exactly **one** beat instance |
| Postgres | Railway PG / Neon / Supabase (pgvector supported) | PITR on |
| Redis | Railway Redis / Upstash (TLS) | |
| Storage | Cloudflare R2 or AWS S3 (private bucket) | |
| Email | Resend | domain SPF/DKIM |
| Monitoring | Sentry + platform logs | |

Scraping from datacenter IPs may be blocked more often than from a residential connection; `JOBSPY_PROXIES` is the documented lever.

---

## 21. Phase-by-phase build plan

Each phase ends with: (1) a summary of what was built, (2) the file list, (3) run commands, (4) verification steps, and (5) **a stop for your review**.

### Phase 1: Foundation
**Build**
- Monorepo skeleton (§6), Makefile, `.env.example`, pre-commit.
- Docker Compose with all six services + dev profiles.
- Backend: settings, logging (with redaction), errors, DB base/session, **all models from §7** + the initial Alembic migration (extensions, enums, HNSW indexes), crypto utilities, Celery app with a `ping` task.
- Auth: signup, verify email (console mailer), login, refresh rotation, logout, Google login, CSRF, `GET /users/me`, rate limits.
- Frontend: Next.js 14 app with Tailwind + shadcn, theme toggle, app shell layout, login/signup pages, auth middleware, QueryProvider, orval setup + generated client, placeholder pages for every route with empty states.
- CI workflow (lint + tests).

**Verify**
- `docker compose up --build` → all healthy; `make migrate`; `/api/docs` loads.
- Sign up → verification link printed in the API logs → log in → land on `/onboarding` → refresh the page and stay logged in → log out.
- `make test` passes (auth, crypto, refresh reuse detection); CI is green.

### Phase 2: Resume
**Build**: storage providers, upload endpoint + validation, text extraction, the `resume_parse/v1` prompt + schema, LLM provider interface (Anthropic + OpenAI + Fake), usage ledger basics, skills canonicalization, the embedding provider (fastembed + OpenAI + Fake), the `parse_resume`/`embed_resume` tasks, profile PATCH + versioning, the onboarding steps 1–2 UI (dropzone, progress, profile editor), the Settings → resume versions list.
**Verify**: upload the sample PDF and DOCX → parsed profile appears in <60 s → edit skills → `profile_version` increments → embedding is non-null (`SELECT vector_dims(embedding)` = 768). Scanned PDF → a clear error. Tests: extraction fixtures, a parse pipeline with FakeLLM.

### Phase 3: Discovery
**Build**: preferences CRUD + onboarding step 3 UI, the `JobSource` interface, JobSpy sources (4), the SerpAPI source, rate limiter + circuit breaker, normalization (rules + LLM gap fill), HTML cleaning, dedupe (hash + URL + near-dup), companies, job embeddings, search run orchestration with progress + per-source status, cancel, `/searches` endpoints, the Find-jobs button + live progress UI, and a basic unranked job list.
**Verify**: run a search for "Python Developer, Remote" → progress advances through stages → per-source chips → jobs stored; rerunning creates no duplicates (`duplicates` count > 0). Disable network for one source (or a fake failure) → run `partial`. Tests: dedupe, extraction rules, pipeline with FakeJobSource.

### Phase 4: Matching
**Build**: hard filters, stage-1 pgvector query, the `match_score/v1` prompt, scoring domain logic + `scoring.yaml`, the score cache, the score_chunk tasks, the ranked feed with filters/sort/badges/infinite scroll, the job detail page with the breakdown chart, skill chips, red flags, filtered-out view, dismiss/rescore, and the budget check + `/searches/estimate`.
**Verify**: the feed is ordered by score with explanations; a second run makes no LLM calls for already-scored jobs (check the `usage_events` count); editing the profile → re-score is triggered only for the new version; filters behave correctly. Tests: scoring, filters, cache.

### Phase 5: Apply
**Build**: contact discovery (regex + Hunter + cache), the fact sheet, generation prompts (email, cover letter, tweaks) with guard includes, word-count enforcement, the subject in code, guardrail validation (deterministic + LLM verifier), drafts/versions/tone regenerate, the Prepare panel UI with inline flags; Gmail OAuth connect/disconnect, MIME send with attachment, the send queue with delay + caps + cancel + idempotency, the SendPreviewDialog; the apply-on-site flow (clipboard + checklist + mark applied); save for later.
**Verify**: prepare an application → the email is ≤150 words with the correct subject; inject a fabricated skill in the editor → a block flag appears and Send is disabled until fixed/acknowledged; send to your own second address → it arrives with the PDF attached after 30–120 s; a 26th send in one day is rejected; cancel within the delay works. Tests: guardrails, send flow, cap.

### Phase 6: Tracking
**Build**: the kanban board (dnd-kit, optimistic, fractional ordering, keyboard support), the application drawer + timeline, status events, Gmail reply detection (history API + classifier + suggestions), follow-up reminders + follow-up draft, in-app notifications, dashboard stats + charts (missing skills, over time, funnel).
**Verify**: drag cards → the order persists after reload; reply to a sent email from the recipient inbox → within 15 min the card moves to Replied with a notification; set follow-up days = 0 in dev → a reminder appears; the dashboard numbers match DB queries.

### Phase 7: Sheets + schedules + notifications
**Build**: Sheets connect (create/link), the debounced upsert sync, manual sync, scheduled daily searches (per-user hour, tz-aware), the daily digest email of new strong matches (Resend/SMTP; mailpit in dev), notification preferences.
**Verify**: connect Sheets → a sheet is created with two tabs; change a status → the row updates within ~5 min (or immediately with Sync now); set the daily search hour to the next 15-min tick → a run happens automatically; the digest appears in mailpit.

### Phase 8: Hardening + deployment
**Build**: complete the test suite to the coverage targets, the eval set + `eval.yml`, full rate-limit review, the cost tracking UI (usage tab, warnings), account export/deletion end-to-end, security headers/CSP, key rotation script, Sentry, a README (Mermaid architecture, setup, env vars, screenshots), deployment configs (Vercel project settings, `railway.json`/`render.yaml`/`fly.toml`), production checklist, runbooks.
**Verify**: CI green; `make eval` within ranges; the deployed app works end to end with a test user; deleting the account removes all data (verified by query); Lighthouse ≥90 on accessibility.

### Rough effort (for planning only)
| phase | relative size |
|---|---|
| 1 Foundation | L |
| 2 Resume | M |
| 3 Discovery | L |
| 4 Matching | M |
| 5 Apply | L |
| 6 Tracking | M |
| 7 Sheets/schedules | S–M |
| 8 Hardening | M |

---

## 22. Stretch features

| feature | approach |
|---|---|
| Skill-gap coach | Aggregate `missing_skills` across matches with score ≥60 weighted by score; group by canonical skill/category; one LLM call per month (cached) to produce a learning plan with free resources; shown on the dashboard. |
| Interview prep | `interview_prep/v1` prompt on application status `interview`: 10 likely questions (technical/behavioural/company), with talking points drawn **only** from the fact sheet. Stored as a draft kind. |
| Chrome extension | MV3 extension; the content script reads the job page title/company/description (read-only, on the user's click); calls `POST /api/v1/extension/score` with an extension-scoped token (separate, revocable); shows a score popup. No form filling. |
| Multiple resumes | `resumes.label` + multiple embeddings; stage 1 picks the best resume per job by cosine; stage 2 scores with that resume; the feed shows "Best with: Backend resume". |
| Salary insight | Aggregate salary ranges of stored jobs by normalized title + location (median/p25/p75, min sample 10), optionally enriched with the SerpAPI salary data. |

---

## 23. Risks and mitigations

| risk | impact | mitigation |
|---|---|---|
| Job boards block or change markup (JobSpy breaks) | no new jobs | multiple sources, SerpAPI fallback, circuit breaker, `partial` runs, pinned JobSpy version + quick upgrade path, user notice |
| Google OAuth verification for Gmail restricted scopes | can't launch Gmail features publicly | stay in Testing mode (≤100 users) initially; reply detection can be disabled to drop `gmail.readonly`; budget for the CASA assessment if going public |
| LLM hallucinated claims in emails | reputational harm to the user | fact-sheet-only context, deterministic + LLM guardrails, block flags, mandatory preview |
| LLM cost overrun | money | two-stage scoring, caching, budgets, global kill switch |
| Score inconsistency across runs | user distrust | low temperature, rubric anchors, code-computed final score, eval set, cached scores per version |
| Prompt injection via job descriptions | wrong scores / weird drafts | data tagging, schema validation, no tool access/actions from the LLM |
| Email deliverability / spam flags | lost applications | sends come from the user's own Gmail, low caps, delays, no tracking pixels, plain text |
| PII leakage | legal/privacy | encryption, log redaction, deletion, minimal PII to the LLM (contact info stripped) |
| Embedding model change | stale vectors | `embedding_model` per row + re-embed task |
| Datacenter IP blocking in prod | fewer results | proxy support; documented; SerpAPI |

---

## 24. Open decisions for you

Please confirm or change these before Phase 1 starts:

1. **Auth**: backend-owned JWT in httpOnly cookies via a same-origin Next.js proxy (recommended), or NextAuth?
2. **Default LLM provider**: Anthropic Claude (recommended, with OpenAI as an alternative), or OpenAI first?
3. **Embeddings**: local `fastembed` bge-base 768-d by default (free, private), or OpenAI `text-embedding-3-small`?
4. **Scoring weights**: skills .35 / experience .25 / seniority .15 / domain .15 / location .10, with bands 80/65/50. OK?
5. **Gmail scopes**: accept that public launch needs Google verification; start in Testing mode?
6. **Transactional email** (verification + digest): Resend, or SMTP?
7. **Deployment target for the backend**: Railway, Render or Fly?
8. **Package managers**: `uv` (Python) and `pnpm` (JS). OK?
9. **Folder structure (§6) and database schema (§7)**: approved as is, or what should change?

Once these are confirmed, Phase 1 begins.

---

## 25. Zero-cost stack (build and run for free)

**Short answer: yes.** Every paid item in this plan has a free option. The only things that genuinely cost money are a hosted LLM above its free quota and Google's security assessment if you ever launch Gmail features publicly. For personal use, or a small group of up to 100 test users, the whole project runs at $0.

> Free tiers change often. Check each provider's current limits page before relying on a number below.

### 25.1 What is already free

All of these are open source or free APIs with no change needed: Next.js, FastAPI, PostgreSQL + pgvector, Redis, Celery, `python-jobspy`, `fastembed` (local embeddings), pdfplumber, python-docx, gspread, the Gmail API, the Google Sheets API, Google OAuth, Docker, and GitHub Actions (unlimited on public repos, 2,000 min/month on private ones).

### 25.2 Swaps for the paid parts

| Need | Paid default in this plan | Free replacement | Limits / caveats |
|---|---|---|---|
| LLM, main | Claude / OpenAI | **Google Gemini API free tier** (Flash / Flash-Lite models) | Rate limits per project (RPM and requests/day). **On the free tier, Google may use your prompts to improve its products**, which means resume text. Fine for your own resume; not acceptable for other users' data. |
| LLM, fast/cheap tasks | Claude Haiku | **Groq free tier** (open models such as Llama / Qwen; OpenAI-compatible API) | Per-model rate limits; very fast. |
| LLM, fully private | — | **Ollama** running a local model (e.g. an 8B Qwen or Llama model) | Free and private. Needs ~8–16 GB RAM; slow on CPU-only machines; lower quality on parsing/scoring than hosted models. |
| Embeddings | OpenAI | **fastembed (already the default)** | Runs locally; free. |
| Google Jobs fallback | SerpAPI | SerpAPI's free plan, or simply leave it off | Small monthly search quota; JobSpy's Google source covers most cases. |
| Email lookup | Hunter.io | Hunter's free plan, or regex only | Small monthly quota; regex over descriptions + "apply on site" works without it. |
| Transactional email (verification, digest) | Resend paid | **Resend free plan**, or **Gmail SMTP** with an app password | Resend's free plan has daily/monthly send limits that are plenty for this app. |
| File storage | AWS S3 | **Local disk** on the server, or **Cloudflare R2** free tier | R2 has a free storage allowance and no egress fees. |
| Error tracking | Sentry paid | Sentry free developer plan, or logs only | |
| Domain + HTTPS | paid domain | **Cloudflare Tunnel** (free `*.trycloudflare.com` or your own domain) or a free DuckDNS subdomain + Caddy | Google OAuth needs HTTPS for any non-localhost redirect URI. |

### 25.3 Free hosting options

| Option | How | Verdict |
|---|---|---|
| **A. Run on your own PC** (recommended to start) | `docker compose up` on your Windows machine (Docker Desktop + WSL2). Use it at `http://localhost:3000`, which Google OAuth allows without HTTPS. | **$0, simplest, fully private.** Searches and reply checks run only while your PC is on. |
| **B. Oracle Cloud Always Free VM** (recommended for 24/7) | One Always Free ARM VM runs the whole Docker Compose stack (api, worker, beat, postgres, redis). The frontend goes on **Vercel Hobby** (free, non-commercial), or runs on the same VM. HTTPS via Cloudflare Tunnel or Caddy. | **$0, always on, enough RAM** for everything including fastembed. Signup asks for a card for identity verification; Always Free resources aren't charged. Idle free instances can be reclaimed, so keep it in use. |
| C. Split free PaaS tiers | Vercel (web) + Neon or Supabase free Postgres (pgvector supported) + Upstash free Redis + Render free web service (API) | **Not recommended.** Render has no free background workers, so Celery has nowhere to run. Render's free web services sleep after ~15 min idle. Celery's constant polling burns through Upstash's free command quota. Supabase pauses idle free projects. |

### 25.4 Plan changes for the free stack

1. **More LLM adapters** behind the existing `LLMProvider` interface:
   - `GeminiProvider` (structured JSON output via `response_schema`)
   - `OpenAICompatibleProvider` (one adapter covers Groq, Ollama, OpenRouter and OpenAI, configured with `base_url` + `api_key`)
   - New env vars: `LLM_PROVIDER=gemini|groq|ollama|anthropic|openai`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OLLAMA_BASE_URL=http://host.docker.internal:11434/v1`.
   - An optional `ollama` service in Docker Compose (profile `local-llm`).
2. **Rate limits from config, not cost.** Free tiers are limited by requests per minute/day, not dollars. The Redis token bucket in front of the LLM reads `LLM_RPM` and `LLM_RPD` per provider, and the usage page shows "requests left today" next to (zero) cost.
3. **Lower stage-2 default:** `STAGE1_TOP_N=15` on free tiers (instead of 30), so one search fits in the daily request quota. Rule-based normalization becomes the main path; the LLM gap fill is off by default (`NORMALIZE_WITH_LLM=false`).
4. **Model routing per provider** in `config/models.yaml`. Example for Gemini: Flash for parsing, scoring and generation; Flash-Lite for normalization, claim checks and reply classification.
5. **Graceful quota handling:** an LLM 429 "quota exhausted" response marks remaining jobs `score_failed` with reason `quota`, the run ends as `partial`, and the feed shows "N jobs waiting for scoring, retry tomorrow" instead of failing.
6. **Privacy notice:** when the active provider's free tier may use data for training (Gemini free tier), Settings shows that warning, and the README says not to put other people's resumes through it. For multi-user privacy, use Ollama or a paid tier.
7. **Gmail in Testing mode:** free and fine for ≤100 users you add as test users. **Refresh tokens expire after 7 days in Testing mode**, so the app detects `invalid_grant`, marks Gmail `needs_reauth`, and shows a one-click "Reconnect Gmail" banner.
8. **Deployment (§20.3) for the free stack:** Option A for development, and Option B for always-on. The `docker-compose.prod.yml` targets a single VM, with Caddy (or `cloudflared`) as the HTTPS entry point.

### 25.5 Recommended free setup

| Layer | Choice |
|---|---|
| LLM | Gemini free tier for your own use (switch to Ollama if you want everything private, or to Groq if Gemini limits are hit) |
| Embeddings | fastembed (local) |
| Jobs | JobSpy (LinkedIn, Indeed, Glassdoor, Google); SerpAPI off |
| Contacts | Regex only; Hunter free key optional |
| Email | Gmail API (Testing mode) for applications; Gmail SMTP for digests |
| Database / queue | Postgres + pgvector and Redis in Docker |
| Hosting | Your PC now → Oracle Always Free VM + Cloudflare Tunnel for 24/7 |
| CI | GitHub Actions |
| **Monthly cost** | **$0** |
