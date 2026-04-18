"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Lock, Loader2, Mail, Smartphone, KeyRound, Shield, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api-client";
import { useAuthProviders } from "@/hooks/use-settings";
import type { OidcProviderPublicItem } from "@/lib/types";

const TRUSTED_DEVICE_DAYS = 30;

function RememberDeviceCheckbox({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-input accent-primary"
      />
      <span>Remember this device for {TRUSTED_DEVICE_DAYS} days</span>
    </label>
  );
}

function MfaVerifyForm({ mfaToken, mfaMethod, mfaMethods, onVerified }: {
  mfaToken: string;
  mfaMethod: string | null;
  mfaMethods: string[];
  onVerified: () => void;
}) {
  const { verifyMfa } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [rememberDevice, setRememberDevice] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const hasTotp = mfaMethods.includes("totp");
  const hasEmail = mfaMethods.includes("email");
  const defaultTab = mfaMethod === "email" && hasEmail ? "email" : hasTotp ? "totp" : "email";

  async function handleVerify(method: string) {
    setError("");
    setLoading(true);
    try {
      // Recovery codes are an emergency mechanism; do not offer a 30-day bypass
      // on a device the user is recovering account access from.
      const remember = method === "recovery" ? false : rememberDevice;
      await verifyMfa(code, method, remember);
      onVerified();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendEmail() {
    setError("");
    setSendingEmail(true);
    try {
      await api.mfaSendEmailOtp({ mfa_token: mfaToken });
      setEmailSent(true);
      setCooldown(60);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to send email";
      setError(msg);
      const match = msg.match(/wait (\d+) seconds/);
      if (match) setCooldown(parseInt(match[1], 10));
    } finally {
      setSendingEmail(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="text-center">
        <p className="text-sm text-muted-foreground">Two-factor authentication is required</p>
      </div>
      {error && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
      )}
      <Tabs defaultValue={defaultTab} className="w-full">
        <TabsList className={`grid w-full ${hasTotp && hasEmail ? "grid-cols-3" : "grid-cols-2"}`}>
          {hasTotp && <TabsTrigger value="totp" className="gap-1.5 text-xs"><Smartphone className="h-3.5 w-3.5" /> Authenticator</TabsTrigger>}
          {hasEmail && <TabsTrigger value="email" className="gap-1.5 text-xs"><Mail className="h-3.5 w-3.5" /> Email</TabsTrigger>}
          <TabsTrigger value="recovery" className="gap-1.5 text-xs"><KeyRound className="h-3.5 w-3.5" /> Recovery</TabsTrigger>
        </TabsList>

        <TabsContent value="totp" className="space-y-3 pt-2">
          <p className="text-sm text-muted-foreground">Enter the 6-digit code from your authenticator app.</p>
          <Input
            ref={inputRef}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="000000"
            className="text-center text-lg tracking-widest"
            maxLength={6}
            autoComplete="one-time-code"
            onKeyDown={(e) => { if (e.key === "Enter" && code.length === 6) handleVerify("totp"); }}
          />
          <RememberDeviceCheckbox checked={rememberDevice} onChange={setRememberDevice} />
          <Button className="w-full" disabled={loading || code.length !== 6} onClick={() => handleVerify("totp")}>
            {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Verifying...</> : "Verify"}
          </Button>
        </TabsContent>

        <TabsContent value="email" className="space-y-3 pt-2">
          {!emailSent ? (
            <>
              <p className="text-sm text-muted-foreground">We&apos;ll send a verification code to your registered email.</p>
              <Button className="w-full" variant="outline" onClick={handleSendEmail} disabled={sendingEmail || cooldown > 0}>
                {sendingEmail ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Sending...</> : cooldown > 0 ? `Send code (${cooldown}s)` : "Send code"}
              </Button>
            </>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">Enter the 6-digit code sent to your email.</p>
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                className="text-center text-lg tracking-widest"
                maxLength={6}
                autoComplete="one-time-code"
                onKeyDown={(e) => { if (e.key === "Enter" && code.length === 6) handleVerify("email"); }}
              />
              <RememberDeviceCheckbox checked={rememberDevice} onChange={setRememberDevice} />
              <Button className="w-full" disabled={loading || code.length !== 6} onClick={() => handleVerify("email")}>
                {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Verifying...</> : "Verify"}
              </Button>
              <Button variant="ghost" size="sm" className="w-full" onClick={handleSendEmail} disabled={sendingEmail || cooldown > 0}>
                {cooldown > 0 ? `Resend code (${cooldown}s)` : "Resend code"}
              </Button>
            </>
          )}
        </TabsContent>

        <TabsContent value="recovery" className="space-y-3 pt-2">
          <p className="text-sm text-muted-foreground">Enter one of your recovery codes.</p>
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="XXXXXXXX"
            className="text-center text-lg tracking-widest font-mono"
            autoComplete="off"
            onKeyDown={(e) => { if (e.key === "Enter" && code.length >= 8) handleVerify("recovery"); }}
          />
          <Button className="w-full" disabled={loading || code.length < 8} onClick={() => handleVerify("recovery")}>
            {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Verifying...</> : "Verify"}
          </Button>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ProviderIcon({ type }: { type: string }) {
  if (type === "azure_entra") return <Globe className="h-4 w-4" />;
  if (type === "keycloak") return <Shield className="h-4 w-4" />;
  return <Globe className="h-4 w-4" />;
}

function providerLabel(provider: OidcProviderPublicItem): string {
  if (provider.provider_type === "azure_entra") return `Sign in with ${provider.name}`;
  if (provider.provider_type === "keycloak") return `Sign in with ${provider.name}`;
  return `Sign in with ${provider.name}`;
}

function OidcButtons({ providers }: { providers: OidcProviderPublicItem[] }) {
  const apiBase = typeof window !== "undefined" ? "/api" : "";
  const frontendUrl = typeof window !== "undefined" ? window.location.origin : "";

  return (
    <div className="space-y-2">
      {providers.map((p) => (
        <Button
          key={p.slug}
          variant="outline"
          className="w-full gap-2"
          onClick={() => {
            const redirectUri = encodeURIComponent(`${frontendUrl}/auth/oidc/callback`);
            window.location.href = `${apiBase}/auth/oidc/${p.slug}/authorize?redirect_uri=${redirectUri}`;
          }}
        >
          <ProviderIcon type={p.provider_type} />
          {providerLabel(p)}
        </Button>
      ))}
    </div>
  );
}

function OrDivider() {
  return (
    <div className="relative my-4">
      <Separator />
      <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-3 text-xs text-muted-foreground">
        or
      </span>
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { login, mfaPending, mfaToken, mfaMethod, mfaMethods, clearMfaState } = useAuth();
  const { data: authProviders } = useAuthProviders();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showLocalForm, setShowLocalForm] = useState(false);

  const oidcProviders = authProviders?.oidc_providers ?? [];
  const localLoginEnabled = authProviders?.local_login_enabled ?? true;
  const hasOidc = oidcProviders.length > 0;
  const showLocal = localLoginEnabled || showLocalForm;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(username, password);
      if (result === "ok") {
        router.push("/dashboard");
      } else if (result === "mfa_setup_required") {
        router.push("/mfa-setup");
      } else if (result === "password_change_required") {
        router.push("/change-password");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-primary/[0.08] via-transparent to-transparent" />
      <Card className="relative w-full max-w-md animate-in fade-in zoom-in-95 slide-in-from-bottom-4 duration-500">
        <CardHeader className="text-center">
          <div className="relative mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-lg bg-primary shadow-lg shadow-primary/25">
            <Lock className="h-6 w-6 text-primary-foreground" />
          </div>
          <CardTitle className="text-2xl">{mfaPending ? "Verify your identity" : "Welcome back"}</CardTitle>
          <CardDescription>
            {mfaPending ? "Complete two-factor authentication to continue" : "Sign in to your account"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mfaPending && mfaToken ? (
            <>
              <MfaVerifyForm mfaToken={mfaToken} mfaMethod={mfaMethod} mfaMethods={mfaMethods} onVerified={() => router.push("/dashboard")} />
              <Button variant="ghost" size="sm" className="mt-3 w-full" onClick={clearMfaState}>
                Back to login
              </Button>
            </>
          ) : (
            <>
              {hasOidc && <OidcButtons providers={oidcProviders} />}

              {hasOidc && showLocal && <OrDivider />}

              {showLocal && (
                <form onSubmit={handleSubmit} className="space-y-4">
                  {error && (
                    <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
                  )}
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus={!hasOidc} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input id="password" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} required />
                  </div>
                  <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? "Signing in..." : "Sign in"}
                  </Button>
                </form>
              )}

              {!localLoginEnabled && !showLocalForm && (
                <button
                  onClick={() => setShowLocalForm(true)}
                  className="mt-4 block w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  Admin login
                </button>
              )}

              <p className="mt-4 text-center text-sm text-muted-foreground">
                First time?{" "}
                <a href="/setup" className="text-primary underline-offset-4 hover:underline">Create admin account</a>
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
