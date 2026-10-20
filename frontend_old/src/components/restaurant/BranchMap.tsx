"use client";

// Where the branch is (Phase 7d): Leaflet with OpenStreetMap tiles, credited on the map as the tile policy requires.
// Leaflet touches `window` on import, so it is loaded inside the effect, in the browser only. A circle marker needs no
// image files (Leaflet's default pin images break under bundlers). The street and area are also written as text
// next to the map, so the map is never the only way to know where the branch is.

import "leaflet/dist/leaflet.css";

import { useEffect, useRef } from "react";

export function BranchMap({ lat, lon, label }: { lat: number; lon: number; label: string }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let map: import("leaflet").Map | null = null;
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !box.current) return;
      map = L.map(box.current, { center: [lat, lon], zoom: 15, scrollWheelZoom: false });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
      }).addTo(map);
      const marker = L.circleMarker([lat, lon], { radius: 10, color: "#5B1E4E", weight: 3, fillColor: "#D8AE4A", fillOpacity: 0.9 })
        .addTo(map)
        .bindTooltip(label);
      // The tooltip makes the marker a tab stop; give it a name (ui-checker, 7d).
      const el = marker.getElement();
      el?.setAttribute("role", "img");
      el?.setAttribute("aria-label", `Map marker: ${label}`);
    });
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [lat, lon, label]);

  return (
    <div
      ref={box}
      role="region"
      aria-label={`Map showing ${label}`}
      className="relative z-0 h-64 w-full overflow-hidden rounded-xl border border-border"
    />
  );
}
