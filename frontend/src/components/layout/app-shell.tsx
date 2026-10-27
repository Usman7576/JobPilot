"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/fetcher";
import { useUsersGetMe } from "@/lib/api/generated/users/users";

import { SidebarNav } from "./sidebar-nav";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

function Brand() {
  return (
    <Link href="/jobs" className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="bg-primary text-primary-foreground grid size-7 place-items-center rounded-md text-xs">
        JP
      </span>
      JobPilot AI
    </Link>
  );
}

/** Sends the user to /login when the session is really gone (the fetcher already tried a refresh). */
function SessionGuard({ error }: { error: unknown }) {
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [error, pathname, router]);
  return null;
}

// The URL is only known at request time on dynamic routes like /jobs/[id], so the parts
// that read it stream in behind Suspense while the rest of the shell prerenders.
function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full rounded-md" />}>
      <SidebarNav onNavigate={onNavigate} />
    </Suspense>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const me = useUsersGetMe();

  return (
    <div className="flex min-h-svh flex-1">
      <Suspense>
        <SessionGuard error={me.error} />
      </Suspense>
      <aside className="bg-sidebar hidden w-60 shrink-0 flex-col gap-6 border-r p-4 md:flex">
        <Brand />
        <Nav />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-background/80 sticky top-0 z-10 flex h-14 items-center gap-2 border-b px-4 backdrop-blur">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-4">
              <SheetHeader className="p-0 pb-4">
                <SheetTitle asChild>
                  <div>
                    <Brand />
                  </div>
                </SheetTitle>
              </SheetHeader>
              <Nav onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>
          <div className="md:hidden">
            <Brand />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <UserMenu user={me.data} />
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}
