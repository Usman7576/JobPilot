# ADR 0001: Backend-owned auth with same-origin cookies

- Status: accepted
- Date: 2026-10-27

## Context

The spec allowed "JWT (access + refresh) or NextAuth". Users, Gmail/Sheets OAuth tokens and
all background work (Celery) live in the FastAPI backend.

## Decision

FastAPI owns authentication:

- Email + password (argon2id) with email verification, and Google sign-in (OAuth code + PKCE).
- Short-lived JWT access token (15 min) in an httpOnly cookie.
- Opaque refresh token (30 days), stored hashed, rotated on every use, with reuse detection
  that revokes the whole session family. Its cookie is scoped to `/api/v1/auth`.
- Double-submit CSRF token (`csrf_token` cookie + `X-CSRF-Token` header) on unsafe methods.
- Next.js rewrites `/api/v1/*` to the API, so the browser only ever talks to one origin and
  every cookie is first-party (`SameSite=Lax`).
- A non-secret `jp_session` hint cookie lets the Next.js route guard (`src/proxy.ts`) decide
  whether to show `/login`; it grants nothing by itself.

## Consequences

- One user table and one session model; Celery and the API share it.
- No NextAuth adapter or session syncing.
- The frontend must send the CSRF header (done centrally in `src/lib/api/fetcher.ts`).
