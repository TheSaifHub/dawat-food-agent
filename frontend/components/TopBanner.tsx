import React from 'react';
import { Info } from 'lucide-react';

export function TopBanner() {
  return (
    <aside
      aria-label="Demo Disclaimer Banner"
      className="w-full bg-[#5B1E4E] text-[#FAF6EF] border-b border-[#D8AE4A]/30 py-2 px-3 text-xs sm:text-sm font-sans flex items-center justify-center gap-2 text-center"
    >
      <Info className="w-4 h-4 text-[#D8AE4A] shrink-0" aria-hidden="true" />
      <p className="tracking-wide">
        <span className="font-semibold text-white">Demo project.</span> Menus, prices and orders are simulated. Not affiliated with any restaurant.
      </p>
    </aside>
  );
}
