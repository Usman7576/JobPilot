"use client";

import Link from "next/link";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthCard } from "@/components/auth/auth-card";
import { FormField } from "@/components/auth/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useAuthForgotPassword } from "@/lib/api/generated/auth/auth";
import { errorMessage, zodResolver } from "@/lib/forms";

const schema = z.object({ email: z.email("Enter a valid email") });
type Values = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const forgot = useAuthForgotPassword();
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const onSubmit = form.handleSubmit((data) => forgot.mutate({ data }));

  return (
    <AuthCard
      title="Reset your password"
      description="We'll email you a link to choose a new password."
      footer={
        <Link href="/login" className="text-foreground underline underline-offset-4">
          Back to sign in
        </Link>
      }
    >
      {forgot.isSuccess ? (
        <p className="text-sm">{forgot.data.message}</p>
      ) : (
        <form onSubmit={onSubmit} className="grid gap-4" noValidate>
          <FormField
            label="Email"
            type="email"
            autoComplete="email"
            error={form.formState.errors.email?.message}
            {...form.register("email")}
          />
          {forgot.isError && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(forgot.error)}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={forgot.isPending}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthCard>
  );
}
