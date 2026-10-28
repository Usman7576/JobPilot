import { NextResponse, type NextRequest } from "next/server";

// Pages that need a signed-in user. The API still validates every request; this only
// decides whether to send the visitor to /login first.
const PROTECTED_PREFIXES = [
  "/onboarding",
  "/jobs",
  "/applications",
  "/dashboard",
  "/profile",
  "/settings",
];
const SESSION_HINT_COOKIE = "jp_session";

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  // The homepage is for visitors; signed-in users go straight to their jobs.
  if (pathname === "/" && request.cookies.has(SESSION_HINT_COOKIE)) {
    return NextResponse.redirect(new URL("/jobs", request.url));
  }
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (!isProtected || request.cookies.has(SESSION_HINT_COOKIE)) {
    return NextResponse.next();
  }
  const login = new URL("/login", request.url);
  login.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
