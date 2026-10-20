"use client";

// The header's cart count, from the backend's cart (GET /cart). Display only: nothing is priced or changed here.
// null = not signed in or not known yet.

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { accessToken } from "@/lib/auth";
import { useSession } from "@/lib/session";

type CartCount = { items?: unknown; branches?: { items: { qty: number }[] }[] };

export function useServerCartCount(refreshKey: string): number | null {
  const { session } = useSession();
  const signedIn = session.state === "signed_in";
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    async function load() {
      if (!signedIn) {
        if (live) setCount(null);
        return;
      }
      const res = await api<CartCount>("/cart", { token: await accessToken() });
      if (!live || !res.ok) return;
      const n = (res.data.branches ?? []).reduce((sum, b) => sum + b.items.reduce((s, l) => s + l.qty, 0), 0);
      setCount(n);
    }
    queueMicrotask(() => void load());
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => {
      live = false;
      window.removeEventListener("focus", onFocus);
    };
  }, [signedIn, refreshKey]);

  return count;
}

export function useAreaList(): { area_id: string; name: string }[] | null {
  const [areas, setAreas] = useState<{ area_id: string; name: string }[] | null>(null);
  useEffect(() => {
    let live = true;
    void api<{ areas: { area_id: string; name: string }[] }>("/areas").then((res) => {
      if (live && res.ok && res.data.areas?.length) setAreas(res.data.areas);
    });
    return () => {
      live = false;
    };
  }, []);
  return areas;
}
