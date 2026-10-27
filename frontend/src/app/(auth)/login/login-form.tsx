"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormField } from "@/components/auth/form-field";
import { GoogleButton } from "@/components/auth/google-button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/fetcher";
import { useAuthLogin, useAuthResendVerification } from "@/lib/api/generated/auth/auth";
import { errorMessage, zodResolver } from "@/lib/forms";
import { safeNextPath } from "@/lib/navigation";

const schema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

const OAUTH_ERRORS: Record<string, string> = {
  google_disabled: "Google sign-in isn't configured on this server.",
  google_cancelled: "Google sign-in was cancelled.",
  google_state: "Google sign-in expired. Please try again.",
  google_failed: "Google sign-in failed. Please try again.",
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const oauthError = OAUTH_ERRORS[params.get("error") ?? ""];
  const login = useAuthLogin();
  const resend = useAuthResendVerification();
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  const notVerified = login.error instanceof ApiError && login.error.code === "email_not_verified";

  const onSubmit = form.handleSubmit((values) =>
    login.mutate(
      { data: values },
      {
        onSuccess: (user) => {
          const fallback = user.onboarding_step === "done" ? "/jobs" : "/onboarding";
          router.replace(safeNextPath(params.get("next")) ?? fallback);
        },
      },
    ),
  );

  const resendVerification = () =>
    resend.mutate(
      { data: { email: form.getValues("email") } },
      {
        onSuccess: () => toast.success("Verification email sent. Check your inbox."),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );

  return (
    <div className="grid gap-4">
      {oauthError && (
        <Alert variant="destructive">
          <AlertDescription>{oauthError}</AlertDescription>
        </Alert>
      )}
      <form onSubmit={onSubmit} className="grid gap-4" noValidate>
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />
        <FormField
          label="Password"
          type="password"
          autoComplete="current-password"
          error={form.formState.errors.password?.message}
          hint={
            <Link href="/forgot-password" className="text-sm underline-offset-4 hover:underline">
              Forgot password?
            </Link>
          }
          {...form.register("password")}
        />
        {login.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {errorMessage(login.error)}
              {notVerified && (
                <Button
                  type="button"
                  variant="link"
                  className="h-auto p-0"
                  disabled={resend.isPending}
                  onClick={resendVerification}
                >
                  Resend the verification email
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <GoogleButton />
    </div>
  );
}
