/**
 * Hook that keeps the UI context store's route information in sync
 * with Next.js navigation.  Mount once in the dashboard layout.
 */

"use client";

import { useEffect } from "react";
import { usePathname, useParams } from "next/navigation";
import { useUIContextStore } from "../stores/ui-context-store";

export function useRouteSync() {
  const pathname = usePathname();
  const params = useParams();
  const setRoute = useUIContextStore((s) => s.setRoute);

  useEffect(() => {
    setRoute(pathname, (params ?? {}) as Record<string, string>);
  }, [pathname, params, setRoute]);
}
