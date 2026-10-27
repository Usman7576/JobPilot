import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";

import { AccountSettings } from "./account-settings";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Your account, sending limits and integrations." />
      <AccountSettings />
    </>
  );
}
