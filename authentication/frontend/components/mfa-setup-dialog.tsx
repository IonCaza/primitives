"use client";

import { useState, useEffect } from "react";
import { Smartphone, Mail, Loader2, Copy, Check, Download, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api-client";
import type { MfaTotpInitResponse } from "@/lib/types";

type Step = "choose" | "totp-scan" | "email-verify" | "recovery" | "done";

interface MfaSetupDialogProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  dismissible?: boolean;
  setupToken?: string | null;
  onComplete: (accessToken: string, refreshToken: string) => void;
}

export function MfaSetupDialog({ open, onOpenChange, dismissible = true, setupToken, onComplete }: MfaSetupDialogProps) {
  const [step, setStep] = useState<Step>("choose");
  const [totpData, setTotpData] = useState<MfaTotpInitResponse | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [savedCodes, setSavedCodes] = useState(false);
  const [mfaOptions, setMfaOptions] = useState<{ totp: boolean; email: boolean } | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  useEffect(() => {
    if (!open) return;
    setOptionsLoading(true);
    api.mfaSetupOptions(setupToken ?? undefined)
      .then(setMfaOptions)
      .catch(() => setMfaOptions({ totp: true, email: false }))
      .finally(() => setOptionsLoading(false));
  }, [open, setupToken]);

  function reset() {
    setStep("choose");
    setTotpData(null);
    setCode("");
    setError("");
    setLoading(false);
    setRecoveryCodes([]);
    setCopied(false);
    setEmailSent(false);
    setSavedCodes(false);
  }

  async function handleChooseTotp() {
    setError("");
    setLoading(true);
    try {
      const data = await api.mfaTotpInit(setupToken ?? undefined);
      setTotpData(data);
      setStep("totp-scan");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to initialize TOTP");
    } finally {
      setLoading(false);
    }
  }

  async function handleChooseEmail() {
    setError("");
    setLoading(true);
    try {
      await api.mfaEmailInit(setupToken ?? undefined);
      setEmailSent(true);
      setCooldown(60);
      setStep("email-verify");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to send verification email";
      setError(msg);
      const match = msg.match(/wait (\d+) seconds/);
      if (match) setCooldown(parseInt(match[1], 10));
    } finally {
      setLoading(false);
    }
  }

  async function handleTotpConfirm() {
    if (!totpData) return;
    setError("");
    setLoading(true);
    try {
      const result = await api.mfaTotpConfirm({ secret: totpData.secret, code }, setupToken ?? undefined);
      if (result.access_token && result.refresh_token) {
        localStorage.setItem("_mfa_at", result.access_token);
        localStorage.setItem("_mfa_rt", result.refresh_token);
      }
      if (result.recovery_codes.length > 0) {
        setRecoveryCodes(result.recovery_codes);
        setStep("recovery");
      } else {
        setStep("done");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setLoading(false);
    }
  }

  async function handleEmailConfirm() {
    setError("");
    setLoading(true);
    try {
      const result = await api.mfaEmailConfirm({ code }, setupToken ?? undefined);
      if (result.access_token && result.refresh_token) {
        localStorage.setItem("_mfa_at", result.access_token);
        localStorage.setItem("_mfa_rt", result.refresh_token);
      }
      if (result.recovery_codes.length > 0) {
        setRecoveryCodes(result.recovery_codes);
        setStep("recovery");
      } else {
        setStep("done");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setLoading(false);
    }
  }

  async function handleResendEmail() {
    setError("");
    try {
      await api.mfaEmailInit(setupToken ?? undefined);
      setEmailSent(true);
      setCooldown(60);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to resend email";
      setError(msg);
      const match = msg.match(/wait (\d+) seconds/);
      if (match) setCooldown(parseInt(match[1], 10));
    }
  }

  function handleCopyCodes() {
    navigator.clipboard.writeText(recoveryCodes.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleDownloadCodes() {
    const blob = new Blob([recoveryCodes.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleFinish() {
    const at = localStorage.getItem("_mfa_at");
    const rt = localStorage.getItem("_mfa_rt");
    localStorage.removeItem("_mfa_at");
    localStorage.removeItem("_mfa_rt");
    if (at && rt) {
      onComplete(at, rt);
    } else {
      onComplete("", "");
    }
    reset();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={dismissible ? (v) => { if (!v) reset(); onOpenChange?.(v); } : undefined}
    >
      <DialogContent
        className="max-w-lg"
        onPointerDownOutside={dismissible ? undefined : (e) => e.preventDefault()}
        onEscapeKeyDown={dismissible ? undefined : (e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>
            {step === "choose" && "Set up two-factor authentication"}
            {step === "totp-scan" && "Scan QR code"}
            {step === "email-verify" && "Verify your email"}
            {step === "recovery" && "Save your recovery codes"}
            {step === "done" && "MFA enabled"}
          </DialogTitle>
        </DialogHeader>

        {error && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
        )}

        {step === "choose" && (
          optionsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className={`grid gap-3 ${mfaOptions?.email !== false ? "sm:grid-cols-2" : "sm:grid-cols-1"}`}>
              <Card className="cursor-pointer hover:border-primary/50 transition-colors" onClick={handleChooseTotp}>
                <CardContent className="flex flex-col items-center gap-3 p-6 text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                    <Smartphone className="h-6 w-6 text-primary" />
                  </div>
                  <div>
                    <p className="font-medium">Authenticator App</p>
                    <p className="text-xs text-muted-foreground mt-1">Use Google Authenticator, Authy, or similar</p>
                  </div>
                </CardContent>
              </Card>
              {mfaOptions?.email !== false && (
                <Card className="cursor-pointer hover:border-primary/50 transition-colors" onClick={handleChooseEmail}>
                  <CardContent className="flex flex-col items-center gap-3 p-6 text-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                      <Mail className="h-6 w-6 text-primary" />
                    </div>
                    <div>
                      <p className="font-medium">Email Verification</p>
                      <p className="text-xs text-muted-foreground mt-1">Receive a code at your registered email</p>
                    </div>
                  </CardContent>
                </Card>
              )}
              {loading && (
                <div className="col-span-full flex items-center justify-center py-2">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}
            </div>
          )
        )}

        {step === "totp-scan" && totpData && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Scan the QR code below with your authenticator app, then enter the 6-digit code to verify.
            </p>
            <div className="flex justify-center">
              <img
                src={`data:image/png;base64,${totpData.qr_code_base64}`}
                alt="TOTP QR Code"
                className="h-48 w-48 rounded-lg border bg-white p-2"
              />
            </div>
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground">Can&apos;t scan? Enter manually</summary>
              <code className="mt-2 block break-all rounded bg-muted px-3 py-2 font-mono text-xs">
                {totpData.secret}
              </code>
            </details>
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              className="text-center text-lg tracking-widest"
              maxLength={6}
              autoComplete="one-time-code"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter" && code.length === 6) handleTotpConfirm(); }}
            />
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => { setStep("choose"); setCode(""); setError(""); }}>
                Back
              </Button>
              <Button className="flex-1" disabled={loading || code.length !== 6} onClick={handleTotpConfirm}>
                {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Verifying...</> : "Verify & enable"}
              </Button>
            </div>
          </div>
        )}

        {step === "email-verify" && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {emailSent
                ? "Enter the 6-digit code sent to your registered email."
                : "We'll send a verification code to your registered email."}
            </p>
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              className="text-center text-lg tracking-widest"
              maxLength={6}
              autoComplete="one-time-code"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter" && code.length === 6) handleEmailConfirm(); }}
            />
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => { setStep("choose"); setCode(""); setError(""); setEmailSent(false); }}>
                Back
              </Button>
              <Button className="flex-1" disabled={loading || code.length !== 6} onClick={handleEmailConfirm}>
                {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Verifying...</> : "Verify & enable"}
              </Button>
            </div>
            <Button variant="ghost" size="sm" className="w-full" onClick={handleResendEmail} disabled={cooldown > 0}>
              {cooldown > 0 ? `Resend code (${cooldown}s)` : "Resend code"}
            </Button>
          </div>
        )}

        {step === "recovery" && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Save these recovery codes in a safe place. Each code can only be used once to sign in if you lose access to your authenticator.
            </p>
            <div className="grid grid-cols-2 gap-2 rounded-lg border bg-muted/50 p-4">
              {recoveryCodes.map((c, i) => (
                <code key={i} className="text-center font-mono text-sm">{c}</code>
              ))}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={handleCopyCodes}>
                {copied ? <><Check className="mr-1.5 h-3.5 w-3.5" /> Copied</> : <><Copy className="mr-1.5 h-3.5 w-3.5" /> Copy</>}
              </Button>
              <Button variant="outline" size="sm" className="flex-1" onClick={handleDownloadCodes}>
                <Download className="mr-1.5 h-3.5 w-3.5" /> Download
              </Button>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={savedCodes} onChange={(e) => setSavedCodes(e.target.checked)} className="rounded" />
              I have saved my recovery codes
            </label>
            <Button className="w-full" disabled={!savedCodes} onClick={() => setStep("done")}>
              Continue
            </Button>
          </div>
        )}

        {step === "done" && (
          <div className="space-y-4 text-center">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
              <ShieldCheck className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            <p className="font-medium">Two-factor authentication is enabled</p>
            <p className="text-sm text-muted-foreground">Your account is now more secure.</p>
            <Button className="w-full" onClick={handleFinish}>
              Continue to app
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
