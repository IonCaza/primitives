"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { MfaSetupDialog } from "@/components/mfa-setup-dialog";

export default function MfaSetupPage() {
  const router = useRouter();
  const { mfaSetupRequired, mfaToken, completeMfaSetup } = useAuth();

  useEffect(() => {
    if (!mfaSetupRequired) {
      router.replace("/login");
    }
  }, [mfaSetupRequired, router]);

  if (!mfaSetupRequired || !mfaToken) return null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <MfaSetupDialog
        open
        dismissible={false}
        setupToken={mfaToken}
        onComplete={async (at, rt) => {
          await completeMfaSetup(at, rt);
          router.push("/dashboard");
        }}
      />
    </div>
  );
}
