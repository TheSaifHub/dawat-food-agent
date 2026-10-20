'use client';

import React from 'react';
import Link from 'next/link';
import { DawatLogo } from './DawatLogo';
import { MapPin, Sparkles, ShieldCheck, Heart } from 'lucide-react';

export function Footer() {
  return (
    <footer className="mt-auto bg-[#22161F] text-[#FAF6EF] border-t-2 border-[#D8AE4A]/30">
      {/* Decorative Nizami Gold Crest Line */}
      <div className="h-1 w-full bg-gradient-to-r from-transparent via-[#D8AE4A] to-transparent opacity-80" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-10">
          {/* Brand Column */}
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center gap-3">
              <DawatLogo variant="full" size="md" />
            </div>
            <p className="text-sm text-[#FAF6EF]/80 max-w-md font-sans leading-relaxed">
              Dawat celebrates the rich culinary heritage of Hyderabad—from royal Nizami charcoal dum biryanis to traditional samovar Irani chai. Powered by Dawat AI, your private dining concierge.
            </p>
            <div className="flex flex-wrap items-center gap-4 text-xs text-[#FAF6EF]/70 pt-2">
              <span className="flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-[#D8AE4A]" aria-hidden="true" />
                Hyderabad, Telangana
              </span>
              <span className="flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-[#D8AE4A]" aria-hidden="true" />
                AI-Curated Feasts
              </span>
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-[#D8AE4A]" aria-hidden="true" />
                Simulated Architecture
              </span>
            </div>
          </div>

          {/* Quick Screen Links */}
          <div>
            <h2 className="text-base font-serif font-semibold text-white tracking-wider mb-4 border-b border-[#D8AE4A]/30 pb-2">
              App Screens
            </h2>
            <ul className="space-y-2.5 text-sm font-sans">
              <li>
                <Link
                  href="/"
                  className="text-[#FAF6EF]/80 hover:text-white hover:underline focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors"
                >
                  1. Home & Area Picker
                </Link>
              </li>
              <li>
                <Link
                  href="/restaurants"
                  className="text-[#FAF6EF]/80 hover:text-white hover:underline focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors"
                >
                  2. Restaurant Directory & Filters
                </Link>
              </li>
              <li>
                <Link
                  href="/restaurant/nawabs-dastarkhwan"
                  className="text-[#FAF6EF]/80 hover:text-white hover:underline focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors"
                >
                  3. Restaurant Menu (Nawab&apos;s)
                </Link>
              </li>
              <li>
                <Link
                  href="/cart"
                  className="text-[#FAF6EF]/80 hover:text-white hover:underline focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors"
                >
                  4. Single-Restaurant Cart & Checkout
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h2 className="text-base font-serif font-semibold text-white tracking-wider mb-4 border-b border-[#D8AE4A]/30 pb-2">
              User & Concierge
            </h2>
            <ul className="space-y-2.5 text-sm font-sans">
              <li>
                <Link
                  href="/order-tracking"
                  className="text-[#FAF6EF]/80 hover:text-white hover:underline focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors"
                >
                  5. Order Tracking & Timeline
                </Link>
              </li>
              <li>
                <Link
                  href="/profile"
                  className="text-[#FAF6EF]/80 hover:text-white hover:underline focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors"
                >
                  6. Profile, Preferences & History
                </Link>
              </li>
              <li>
                <Link
                  href="/login"
                  className="text-[#FAF6EF]/80 hover:text-white hover:underline focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors"
                >
                  7. Login (Priya / Arjun Quick Personas)
                </Link>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => {
                    const event = new CustomEvent('open-dawat-ai');
                    window.dispatchEvent(event);
                  }}
                  className="text-[#FAF6EF]/80 hover:text-white flex items-center gap-1.5 focus-visible:ring-1 focus-visible:ring-[#D8AE4A] transition-colors text-left"
                >
                  8. Dawat AI Ordering Assistant
                  <span className="text-[10px] bg-[#5B1E4E] text-[#FAF6EF] px-1.5 py-0.5 rounded border border-[#D8AE4A]/50">
                    Live
                  </span>
                </button>
              </li>
            </ul>
          </div>
        </div>

        {/* Hard Rule Mandated Attribution & Copyright */}
        <div className="pt-8 border-t border-[#FAF6EF]/10 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-[#FAF6EF]/70 font-sans">
          <p className="tracking-wide text-center sm:text-left">
            Restaurant names and locations © OpenStreetMap contributors
          </p>
          <p className="flex items-center gap-1">
            Dawat © 2026. Made with <Heart className="w-3.5 h-3.5 text-[#D8AE4A] fill-[#D8AE4A]" /> in Hyderabad.
          </p>
        </div>
      </div>
    </footer>
  );
}
