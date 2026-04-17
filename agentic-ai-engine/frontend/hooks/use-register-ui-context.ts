/**
 * Hook for page components to register their visible data into the
 * UI context store.  Automatically unregisters on unmount.
 *
 * Usage:
 *   useRegisterUIContext("delivery", { stats, sprints, filters });
 */

"use client";

import { useEffect, useRef } from "react";
import { useUIContextStore } from "../stores/ui-context-store";

export function useRegisterUIContext(key: string, data: unknown) {
  const register = useUIContextStore((s) => s.registerContext);
  const unregister = useUIContextStore((s) => s.unregisterContext);
  const serializedRef = useRef<string>("");

  useEffect(() => {
    const serialized = JSON.stringify(data);
    if (serialized !== serializedRef.current) {
      serializedRef.current = serialized;
      register(key, data);
    }
    return () => {
      unregister(key);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, JSON.stringify(data), register, unregister]);
}
