"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormField } from "@/components/auth/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getUsersGetMeQueryKey,
  useUsersGetMe,
  useUsersUpdateMe,
} from "@/lib/api/generated/users/users";
import { errorMessage, zodResolver } from "@/lib/forms";

const schema = z.object({
  full_name: z.string().trim().max(120),
  timezone: z.string().min(1, "Pick a timezone"),
  daily_send_cap: z.coerce.number<string>().int().min(1, "At least 1"),
  follow_up_days: z.coerce
    .number<string>()
    .int()
    .min(1, "At least 1 day")
    .max(60, "At most 60 days"),
});
type Values = z.infer<typeof schema>;

// Browsers list canonical zones only (no plain "UTC"), so UTC is added explicitly.
const TIMEZONES = [
  "UTC",
  ...(typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : []),
].filter((tz, i, all) => all.indexOf(tz) === i);

export function AccountSettings() {
  const queryClient = useQueryClient();
  const me = useUsersGetMe();
  const update = useUsersUpdateMe();
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (me.data) {
      form.reset({
        full_name: me.data.full_name ?? "",
        timezone: me.data.timezone,
        daily_send_cap: me.data.daily_send_cap,
        follow_up_days: me.data.follow_up_days,
      });
    }
  }, [me.data, form]);

  if (!me.data) {
    return <Skeleton className="h-80 w-full max-w-2xl rounded-xl" />;
  }

  const onSubmit = form.handleSubmit((values) =>
    update.mutate(
      { data: { ...values, full_name: values.full_name || null } },
      {
        onSuccess: (user) => {
          queryClient.setQueryData(getUsersGetMeQueryKey(), user);
          toast.success("Settings saved");
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    ),
  );
  const errors = form.formState.errors;

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Account
          {me.data.email_verified && <Badge variant="secondary">Verified</Badge>}
        </CardTitle>
        <CardDescription>{me.data.email}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
          <FormField
            label="Full name"
            error={errors.full_name?.message}
            {...form.register("full_name")}
          />
          <div className="grid gap-2">
            <label htmlFor="timezone" className="text-sm font-medium">
              Timezone
            </label>
            <select
              id="timezone"
              className="border-input bg-background h-9 rounded-md border px-3 text-sm"
              {...form.register("timezone")}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
          <FormField
            label="Daily email send cap"
            type="number"
            min={1}
            error={errors.daily_send_cap?.message}
            {...form.register("daily_send_cap")}
          />
          <FormField
            label="Follow-up reminder after (days)"
            type="number"
            min={1}
            max={60}
            error={errors.follow_up_days?.message}
            {...form.register("follow_up_days")}
          />
          <div className="sm:col-span-2">
            <Button type="submit" disabled={update.isPending || !form.formState.isDirty}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
