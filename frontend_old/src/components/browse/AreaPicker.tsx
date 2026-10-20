"use client";

// Which area to deliver to. A native <select>: 170 areas, keyboard and screen-reader friendly with no extra code,
// and on phones it opens the system picker.

import { useEffect, useId, useRef, useState } from "react";

import { api, type AreasResponse } from "@/lib/api";

export function AreaPicker({ value, onChange, label = "Deliver to", focusWhenReady = false }: {
  value: string;
  onChange: (areaId: string) => void;
  label?: string;
  /** Move focus into the list once it has loaded (it is disabled, so unfocusable, until then). */
  focusWhenReady?: boolean;
}) {
  const id = useId();
  const select = useRef<HTMLSelectElement>(null);
  const [areas, setAreas] = useState<AreasResponse["areas"] | null>(null);
  const [failed, setFailed] = useState(false);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api<AreasResponse>("/areas", { signal: controller.signal, onSlow: () => setSlow(true) }).then((res) => {
      if (res.ok) setAreas([...res.data.areas].sort((a, b) => a.name.localeCompare(b.name)));
      else if (res.kind !== "aborted") setFailed(true);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (focusWhenReady && areas) select.current?.focus();
  }, [focusWhenReady, areas]);

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <select
        ref={select}
        id={id}
        value={value}
        disabled={!areas}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 min-w-56 rounded-lg border border-input bg-card px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <option value="" disabled>{areas ? "Choose your area" : failed ? "Couldn't load areas" : "Loading areas…"}</option>
        {areas?.map((a) => <option key={a.area_id} value={a.area_id}>{a.name}</option>)}
      </select>
      {!areas && slow && !failed ? (
        <p className="max-w-72 text-sm text-muted-foreground">Waking up Dawat AI… the free server sleeps when idle, this can take up to a minute.</p>
      ) : null}
    </div>
  );
}
