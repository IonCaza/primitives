"use client";

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { api, setSessionExpiredHandler } from "./api-client";
import { queryClient } from "./query-client";
import type { User, LoginResponse, MfaChallengeResponse, MfaSetupRequiredResponse, PasswordChangeRequiredResponse } from "./types";

function isMfaChallenge(r: LoginResponse): r is MfaChallengeResponse {
  return "requires_mfa" in r && r.requires_mfa === true;
}

function isMfaSetupRequired(r: LoginResponse): r is MfaSetupRequiredResponse {
  return "requires_mfa_setup" in r && r.requires_mfa_setup === true;
}

function isPasswordChangeRequired(r: LoginResponse): r is PasswordChangeRequiredResponse {
  return "password_change_required" in r && r.password_change_required === true;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<"ok" | "mfa_pending" | "mfa_setup_required" | "password_change_required">;
  logout: () => void;
  refresh: () => Promise<void>;
  mfaPending: boolean;
  mfaSetupRequired: boolean;
  mfaToken: string | null;
  mfaMethod: string | null;
  mfaMethods: string[];
  passwordChangeToken: string | null;
  verifyMfa: (code: string, method: string) => Promise<void>;
  completeMfaSetup: (accessToken: string, refreshToken: string) => Promise<void>;
  clearMfaState: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [mfaPending, setMfaPending] = useState(false);
  const [mfaSetupRequired, setMfaSetupRequired] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaMethod, setMfaMethod] = useState<string | null>(null);
  const [mfaMethods, setMfaMethods] = useState<string[]>([]);
  const [passwordChangeToken, setPasswordChangeToken] = useState<string | null>(null);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
    setMfaPending(false);
    setMfaSetupRequired(false);
    setMfaToken(null);
    setMfaMethod(null);
    setPasswordChangeToken(null);
    queryClient.clear();
  }, []);

  useEffect(() => {
    setSessionExpiredHandler(logout);
  }, [logout]);

  const refresh = useCallback(async () => {
    try {
      const u = await api.me();
      setUser(u);
    } catch {
      setUser(null);
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      refresh();
    } else {
      setLoading(false);
    }
  }, [refresh]);

  const clearMfaState = useCallback(() => {
    setMfaPending(false);
    setMfaSetupRequired(false);
    setMfaToken(null);
    setMfaMethod(null);
    setMfaMethods([]);
  }, []);

  const login = async (username: string, password: string): Promise<"ok" | "mfa_pending" | "mfa_setup_required" | "password_change_required"> => {
    clearMfaState();
    setPasswordChangeToken(null);
    const result = await api.login({ username, password });

    if (isPasswordChangeRequired(result)) {
      setPasswordChangeToken(result.password_change_token);
      return "password_change_required";
    }

    if (isMfaChallenge(result)) {
      setMfaPending(true);
      setMfaToken(result.mfa_token);
      setMfaMethod(result.mfa_method);
      setMfaMethods(result.mfa_methods ?? []);
      return "mfa_pending";
    }

    if (isMfaSetupRequired(result)) {
      setMfaSetupRequired(true);
      setMfaToken(result.mfa_setup_token);
      return "mfa_setup_required";
    }

    localStorage.setItem("access_token", result.access_token);
    localStorage.setItem("refresh_token", result.refresh_token);
    await refresh();
    return "ok";
  };

  const verifyMfa = async (code: string, method: string) => {
    if (!mfaToken) throw new Error("No MFA token available");
    const tokens = await api.mfaVerify({ mfa_token: mfaToken, code, method });
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    clearMfaState();
    await refresh();
  };

  const completeMfaSetup = async (accessToken: string, refreshToken: string) => {
    localStorage.setItem("access_token", accessToken);
    localStorage.setItem("refresh_token", refreshToken);
    clearMfaState();
    await refresh();
  };

  return (
    <AuthContext.Provider value={{
      user, loading, login, logout, refresh,
      mfaPending, mfaSetupRequired, mfaToken, mfaMethod, mfaMethods,
      passwordChangeToken,
      verifyMfa, completeMfaSetup, clearMfaState,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
