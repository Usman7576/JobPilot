"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/auth/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useAuthResetPassword } from "@/lib/api/generated/auth/auth";
import { errorMessage, zodResolver } from "@/lib/forms";

const schema = z
  .object({
    password: z.string().min(10, "Use at least 10 characters").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });
type Values = z.infer<typeof schema>;

export function ResetForm() {
  const token = useSearchParams().get("token");
  const reset = useAuthResetPassword();
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  if (!token) {
    return <p className="text-muted-foreground text-sm">This reset link is incomplete.</p>;
  }
  if (reset.isSuccess) {
    return (
      <div className="grid gap-4">
        <p className="text-sm">{reset.data.message}</p>
        <Button asChild className="w-full">
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    );
  }

  const onSubmit = form.handleSubmit(({ password }) => reset.mutate({ data: { token, password } }));
  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <FormField
        label="New password"
        type="password"
        autoComplete="new-password"
        error={form.formState.errors.password?.message}
        {...form.register("password")}
      />
      <FormField
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        error={form.formState.errors.confirm?.message}
        {...form.register("confirm")}
      />
      {reset.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(reset.error)}</AlertDescription>
        </Alert>
      )}
      <Button type="submit" className="w-full" disabled={reset.isPending}>
        Update password
      </Button>
    </form>
  );
}
