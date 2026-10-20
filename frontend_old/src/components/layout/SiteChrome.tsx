// The parts of every page: skip link, demo banner, header, footer (CLAUDE.md: the demo banner and the
// OpenStreetMap credit must always be visible).

import Link from "next/link";

import { DawatLogo } from "@/components/brand/DawatLogo";

export const DEMO_NOTICE = "Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant.";

/** Lets keyboard users jump past the header. Hidden until focused. It shows over the night banner or the plum
 *  header, where the default plum ring vanishes, so its ring is gold (5.8:1 on plum). */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-ivory focus:px-4 focus:py-2 focus:text-plum focus:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-plum"
    >
      Skip to main content
    </a>
  );
}

export function DemoBanner() {
  // D-059: under `npm run dev:local` only (false in every production build), say which data this is.
  const localMode = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DAWAT_DEV_LOGIN === "1";
  return (
    <p className="bg-night px-4 py-2 text-center text-xs text-ivory sm:text-sm" role="note">
      {DEMO_NOTICE}
      {localMode ? <strong className="ml-2 font-semibold">Local development: local data, dev sign-in.</strong> : null}
    </p>
  );
}

export function SiteHeader({ children }: { children?: React.ReactNode }) {
  return (
    <header className="bg-plum text-ivory">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        {/* On plum the default plum focus ring would vanish, so header controls use gold (5.8:1 on plum). */}
        <Link href="/" className="flex items-center gap-3 rounded-md focus-visible:outline-gold">
          <DawatLogo size={40} title="" className="ring-1 ring-gold/40 rounded-[14px]" />
          <span className="font-display text-3xl font-semibold leading-none">Dawat</span>
          <span className="sr-only">, home</span>
        </Link>
        {children ? <nav aria-label="Main" className="flex items-center gap-2">{children}</nav> : null}
      </div>
      <div aria-hidden="true" className="h-px bg-gold/70" />
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-border bg-muted">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 pb-24 pt-6 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          <span className="font-display text-lg font-semibold text-plum">Dawat</span> · Every order, a feast.
        </p>
        <p>
          Restaurant names and locations ©{" "}
          <a
            href="https://www.openstreetmap.org/copyright"
            className="inline-block py-1 text-plum underline underline-offset-2 hover:text-plum-deep"
            target="_blank"
            rel="noopener noreferrer"
          >
            OpenStreetMap contributors
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        </p>
      </div>
    </footer>
  );
}
