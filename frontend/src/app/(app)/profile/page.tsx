import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";

import { ProfileView } from "./profile-view";

export const metadata: Metadata = { title: "Profile" };

export default function ProfilePage() {
  return (
    <>
      <PageHeader
        title="Profile"
        description="Your resume, as JobPilot understands it. Matching and applications use this."
      />
      <ProfileView />
    </>
  );
}
