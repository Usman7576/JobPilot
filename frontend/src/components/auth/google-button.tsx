"use client";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useAuthGetConfig } from "@/lib/api/generated/auth/auth";

export function GoogleButton() {
  const { data } = useAuthGetConfig({ query: { staleTime: Infinity } });
  if (!data?.google_login_enabled) return null;
  return (
    <>
      <div className="flex items-center gap-3">
        <Separator className="flex-1" />
        <span className="text-muted-foreground text-xs uppercase">or</span>
        <Separator className="flex-1" />
      </div>
      <Button variant="outline" className="w-full" asChild>
        {/* Full page navigation: the API redirects to Google and back. */}
        <a href="/api/v1/auth/google/start">Continue with Google</a>
      </Button>
    </>
  );
}
