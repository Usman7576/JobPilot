"use client";

import { MailCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/auth/form-field";
import { GoogleButton } from "@/components/auth/google-button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useAuthSignup } from "@/lib/api/generated/auth/auth";
import { errorMessage, zodResolver } from "@/lib/forms";

const schema = z
  .object({
    full_name: z.string().trim().max(120).optional(),
    email: z.email("Enter a valid email"),
    password: z.string().min(10, "Use at least 10 characters").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    path: ["confirm"],
    message: "Passwords don't match",
  });
type Values = z.infer<typeof schema>;

export function SignupForm() {
  const signup = useAuthSignup();
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const errors = form.formState.errors;

  const onSubmit = form.handleSubmit(({ full_name, email, password }) =>
    signup.mutate({ data: { full_name: full_name || null, email, password } }),
  );

  if (signup.isSuccess) {
    return (
      <div className="grid justify-items-center gap-3 text-center">
        <MailCheck className="text-primary size-10" aria-hidden />
        <p className="font-medium">Check your inbox</p>
        <p className="text-muted-foreground text-sm">
          We sent a verification link to <strong>{form.getValues("email")}</strong>. Open it to
          activate your account.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <form onSubmit={onSubmit} className="grid gap-4" noValidate>
        <FormField
          label="Full name (optional)"
          autoComplete="name"
          error={errors.full_name?.message}
          {...form.register("full_name")}
        />
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...form.register("email")}
        />
        <FormField
          label="Password"
          type="password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...form.register("password")}
        />
        <FormField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          error={errors.confirm?.message}
          {...form.register("confirm")}
        />
        {signup.isError && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(signup.error)}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" className="w-full" disabled={signup.isPending}>
          {signup.isPending ? "Creating account…" : "Create account"}
        </Button>
      </form>
      <GoogleButton />
    </div>
  );
}
