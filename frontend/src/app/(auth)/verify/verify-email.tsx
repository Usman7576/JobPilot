"use client";

import { CircleCheck, CircleX, Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { useAuthVerifyEmail } from "@/lib/api/generated/auth/auth";
import { errorMessage } from "@/lib/forms";

export function VerifyEmail() {
  const token = useSearchParams().get("token");
  const verify = useAuthVerifyEmail();
  const sent = useRef(false);

  useEffect(() => {
    // Tokens are single-use, so make sure dev double-mounting doesn't send twice.
    if (token && !sent.current) {
      sent.current = true;
      verify.mutate({ data: { token } });
    }
  }, [token, verify]);

  if (!token) {
    return <p className="text-muted-foreground text-sm">This verification link is incomplete.</p>;
  }
  if (verify.isError) {
    return (
      <div className="grid justify-items-center gap-3 text-center">
        <CircleX className="text-destructive size-10" aria-hidden />
        <p className="text-sm">{errorMessage(verify.error)}</p>
        <Button asChild variant="outline">
          <Link href="/login">Back to sign in</Link>
        </Button>
      </div>
    );
  }
  if (verify.isSuccess) {
    return (
      <div className="grid justify-items-center gap-3 text-center">
        <CircleCheck className="size-10 text-emerald-600" aria-hidden />
        <p className="text-sm">Your email is verified.</p>
        <Button asChild className="w-full">
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    );
  }
  return (
    <div className="text-muted-foreground flex items-center justify-center gap-2 text-sm">
      <Loader2 className="size-4 animate-spin" aria-hidden /> Verifying…
    </div>
  );
}
