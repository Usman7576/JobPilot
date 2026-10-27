import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";

import { VerifyEmail } from "./verify-email";

export const metadata: Metadata = { title: "Verify email" };

export default function VerifyPage() {
  return (
    <AuthCard title="Email verification">
      <Suspense>
        <VerifyEmail />
      </Suspense>
    </AuthCard>
  );
}
