/**
 * Zustand store for UI context that page components register into.
 *
 * The agent reads this store (via client tool round-trip) to understand
 * what the user currently sees on screen.
 */

import { create } from "zustand";

export interface UIContextSnapshot {
  pathname: string;
  params: Record<string, string>;
  pageContext: Record<string, unknown>;
  capturedAt: string;
}

interface UIContextState {
  pathname: string;
  params: Record<string, string>;
  pageContext: Record<string, unknown>;

  setRoute: (pathname: string, params: Record<string, string>) => void;
  registerContext: (key: string, data: unknown) => void;
  unregisterContext: (key: string) => void;
  getSnapshot: () => UIContextSnapshot;
}

export const useUIContextStore = create<UIContextState>((set, get) => ({
  pathname: "",
  params: {},
  pageContext: {},

  setRoute: (pathname, params) => set({ pathname, params }),

  registerContext: (key, data) =>
    set((state) => ({
      pageContext: { ...state.pageContext, [key]: data },
    })),

  unregisterContext: (key) =>
    set((state) => {
      const next = { ...state.pageContext };
      delete next[key];
      return { pageContext: next };
    }),

  getSnapshot: () => {
    const { pathname, params, pageContext } = get();
    return {
      pathname,
      params,
      pageContext,
      capturedAt: new Date().toISOString(),
    };
  },
}));
