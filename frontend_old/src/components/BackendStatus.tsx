"use client";

// Runs in the browser on purpose: a browser request is what exercises the
// backend's CORS allow-list, which a server-side fetch would bypass.

import { useEffect, useState } from "react";

import { api, type Health } from "@/lib/api";

type Status =
  | { state: "checking" }
  | { state: "waking" }
  | { state: "ok"; version: string }
  | { state: "down"; reason: string };

export function BackendStatus() {
  const [status, setStatus] = useState<Status>({ state: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    api<Health>("/health", {
      signal: controller.signal,
      onSlow: () => setStatus((s) => (s.state === "checking" ? { state: "waking" } : s)),
    }).then((res) => {
      if (res.ok) setStatus({ state: "ok", version: res.data.version });
      else if (res.kind !== "aborted") setStatus({ state: "down", reason: res.message });
    });
    return () => controller.abort();
  }, []);

  let label = "Checking Dawat…";
  let dot = "bg-night/40";
  if (status.state === "waking") {
    label = "Waking up Dawat AI… the free server sleeps when idle, this can take up to a minute.";
    dot = "bg-gold";
  } else if (status.state === "ok") {
    label = `Dawat is online (v${status.version})`;
    dot = "bg-veg";
  } else if (status.state === "down") {
    label = status.reason;
    dot = "bg-destructive";
  }

  return (
    // The dot is inline so it stays beside the first word when the label wraps on a narrow screen (ui-checker, 360 px).
    <p role="status" aria-live="polite" className="max-w-md text-sm">
      <span aria-hidden="true" className={`mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle ${dot}`} />
      {label}
    </p>
  );
}
