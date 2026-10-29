import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/common/page-header";
import { PreferencesForm } from "@/components/preferences/preferences-form";
import { AnswerBankCard } from "@/components/settings/answer-bank-card";
import { DangerZone } from "@/components/settings/danger-zone";
import { GmailCard } from "@/components/settings/gmail-card";
import { ScheduleCard } from "@/components/settings/schedule-card";
import { SheetsCard } from "@/components/settings/sheets-card";
import { UsageCard } from "@/components/settings/usage-card";

import { AccountSettings } from "./account-settings";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="Your account, connected accounts, job preferences and sources."
      />
      <div className="grid gap-10">
        <AccountSettings />
        <section className="grid gap-4">
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">Connected accounts</h2>
          </div>
          {/* Reads ?gmail=... after Google redirects back, so it needs a Suspense boundary. */}
          <Suspense>
            <GmailCard />
          </Suspense>
          <Suspense>
            <SheetsCard />
          </Suspense>
        </section>
        <section className="grid gap-4">
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">Schedule</h2>
          </div>
          <ScheduleCard />
        </section>
        <section className="grid gap-4">
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">Job preferences</h2>
            <p className="text-muted-foreground text-sm">
              Used by &ldquo;Find jobs&rdquo; and, later, by scheduled daily searches.
            </p>
          </div>
          <PreferencesForm />
        </section>
        <section className="grid gap-4">
          <h2 className="text-lg font-semibold">Application forms</h2>
          <AnswerBankCard />
        </section>
        <section className="grid gap-4">
          <h2 className="text-lg font-semibold">AI usage</h2>
          <UsageCard />
        </section>
        <section className="grid gap-4">
          <h2 className="text-lg font-semibold">Danger zone</h2>
          <DangerZone />
        </section>
      </div>
    </>
  );
}
