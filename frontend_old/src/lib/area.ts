"use client";

// The delivery area the visitor is browsing for (Phase 7c). In order: what the page's link says (?area=), what
// this browser last picked, then a signed-in user's saved default area. Browser storage is only a convenience: it
// can be empty or blocked (private windows), so every read and write is guarded and the page works without it.

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { accessToken } from "@/lib/auth";

const KEY = "dawat.area";

export function rememberArea(areaId: string): void {
  try {
    window.localStorage.setItem(KEY, areaId);
  } catch {
    /* storage blocked: nothing to remember, nothing breaks */
  }
}

function storedArea(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

type Prefs = { preferences: Record<string, { value: unknown }> };

/** null while deciding, "" when there is no area yet (show the picker), else an area id. */
export function usePreferredArea(fromUrl: string | null): string | null {
  const { session } = useSession();
  const [area, setArea] = useState<string | null>(fromUrl || null);

  useEffect(() => {
    if (fromUrl) {
      queueMicrotask(() => setArea(fromUrl));
      return;
    }
    const stored = storedArea();
    if (stored) {
      queueMicrotask(() => setArea(stored));
      return;
    }
    if (session.state === "loading") return;
    if (session.state !== "signed_in") {
      queueMicrotask(() => setArea(""));
      return;
    }
    let cancelled = false;
    void (async () => {
      const res = await api<Prefs>("/me/preferences", { token: await accessToken() });
      const saved = res.ok ? res.data.preferences.default_area?.value : undefined;
      if (!cancelled) setArea(typeof saved === "string" ? saved : "");
    })();
    return () => {
      cancelled = true;
    };
  }, [fromUrl, session.state]);

  return area;
}
