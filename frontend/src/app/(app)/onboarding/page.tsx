import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";

import { OnboardingFlow } from "./onboarding-flow";

export const metadata: Metadata = { title: "Get started" };

export default function OnboardingPage() {
  return (
    <>
      <PageHeader
        title="Let's set you up"
        description="Four quick steps and JobPilot starts finding jobs that fit you."
      />
      <OnboardingFlow />
    </>
  );
}
