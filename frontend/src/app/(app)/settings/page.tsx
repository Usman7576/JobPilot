import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";
import { PreferencesForm } from "@/components/preferences/preferences-form";

import { AccountSettings } from "./account-settings";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Your account, job preferences and sources." />
      <div className="grid gap-10">
        <AccountSettings />
        <section className="grid gap-4">
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">Job preferences</h2>
            <p className="text-muted-foreground text-sm">
              Used by &ldquo;Find jobs&rdquo; and, later, by scheduled daily searches.
            </p>
          </div>
          <PreferencesForm />
        </section>
      </div>
    </>
  );
}
