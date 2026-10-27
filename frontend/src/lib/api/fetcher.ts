/**
 * Fetch wrapper used by every generated API hook (orval mutator).
 *
 * - Same-origin requests: Next.js rewrites /api/v1/* to the FastAPI server, so the
 *   auth cookies are first-party.
 * - Sends the double-submit CSRF header on state-changing requests.
 * - On 401, refreshes the session once (shared across concurrent calls) and retries.
 * - Turns problem+json errors into ApiError.
 */

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const NO_REFRESH_PATHS = ["/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout"];

export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  detail?: string;
  code: string;
  errors?: { loc: (string | number)[]; msg: string; type: string }[];
  /** Endpoint-specific extras, e.g. `run_id` on a 409 from POST /searches. */
  [extra: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.status = problem.status;
    this.code = problem.code;
    this.problem = problem;
  }
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : undefined;
}

function withCsrf(init: RequestInit): RequestInit {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (UNSAFE_METHODS.has(method)) {
    const token = readCookie("csrf_token");
    if (token) headers.set("X-CSRF-Token", token);
  }
  return { ...init, headers, credentials: "same-origin" };
}

let refreshing: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", withCsrf({ method: "POST" }))
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: Partial<ProblemDetails> = {};
  try {
    body = (await response.json()) as Partial<ProblemDetails>;
  } catch {
    // Non-JSON error (e.g. proxy failure): fall through to the generic problem.
  }
  return new ApiError({
    ...body,
    title: body.title ?? response.statusText ?? "Request failed",
    status: response.status,
    detail: body.detail,
    code: body.code ?? "http_error",
    errors: body.errors,
  });
}

export async function customFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  let response = await fetch(url, withCsrf(init));

  const canRefresh = !NO_REFRESH_PATHS.some((p) => url.startsWith(p));
  if (response.status === 401 && canRefresh && (await refreshSession())) {
    response = await fetch(url, withCsrf(init));
  }

  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

// Orval uses these to type errors and request bodies in the generated hooks.
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- orval passes the error type
export type ErrorType<_E> = ApiError;
export type BodyType<B> = B;

export default customFetch;
