'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { DawatLogo } from './DawatLogo';
import { useDawat } from '@/context/DawatContext';
import { HYDERABAD_AREAS } from '@/data/mockData';
import { useSession } from '@/lib/session';
import { useRouter } from 'next/navigation';
import { useAreaList, useServerCartCount } from '@/lib/servercart';
import {
  MapPin,
  ShoppingBag,
  Sparkles,
  User,
  ChevronDown,
  Menu,
  X,
  Compass,
} from 'lucide-react';

export function Header() {
  const pathname = usePathname();
  const {
    selectedArea,
    setSelectedArea,
    totalCartItemCount,
    setIsChatOpen,
  } = useDawat();

  // Real data behind the same elements: the signed-in user (GET /me), the server cart count, the real area list.
  const router = useRouter();
  const { session, signOut } = useSession();
  const realCount = useServerCartCount(pathname);
  const realAreas = useAreaList();
  const signedIn = session.state === 'signed_in';
  const profileName = signedIn ? session.me.display_name : 'Sign in';
  const profileFirstName = signedIn ? session.me.display_name.split(' ')[0] : 'Sign in';
  async function handleSignOut() {
    await signOut();
    router.replace('/login');
  }
  const cartCount = signedIn ? (realCount ?? 0) : totalCartItemCount;
  const areaNames = realAreas ? realAreas.map((a) => a.name) : HYDERABAD_AREAS;

  const [isAreaDropdownOpen, setIsAreaDropdownOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 w-full bg-[#FAF6EF]/95 backdrop-blur-md border-b border-[#EADFCF] shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20 gap-2 sm:gap-4">
          {/* Logo & Area Selector */}
          <div className="flex items-center gap-3 sm:gap-6 min-w-0">
            <Link
              href="/"
              className="flex items-center focus-visible:ring-2 focus-visible:ring-[#5B1E4E] rounded-lg shrink-0"
              aria-label="Dawat Home"
            >
              <DawatLogo variant="full" size="md" className="hidden sm:inline-flex" />
              <DawatLogo variant="emblem-only" size="sm" className="sm:hidden" />
            </Link>

            {/* Hyderabad Area Selector */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsAreaDropdownOpen((prev) => !prev)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-[#FFFFFF] border border-[#EADFCF] text-[#22161F] text-xs sm:text-sm font-sans hover:border-[#5B1E4E] transition-all min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
                aria-expanded={isAreaDropdownOpen}
                aria-haspopup="listbox"
                aria-label={`Select delivery location in Hyderabad, currently ${selectedArea}`}
              >
                <MapPin className="w-4 h-4 text-[#5B1E4E] shrink-0" aria-hidden="true" />
                <span className="font-medium truncate max-w-[110px] sm:max-w-[150px]">
                  {selectedArea}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-[#574652] shrink-0" aria-hidden="true" />
              </button>

              {isAreaDropdownOpen && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setIsAreaDropdownOpen(false)}
                  />
                  <div
                    role="listbox"
                    aria-label="Hyderabad Areas"
                    className="absolute left-0 mt-2 w-56 bg-[#FFFFFF] border border-[#EADFCF] rounded-2xl shadow-xl py-2 z-50 overflow-y-auto max-h-80 font-sans"
                  >
                    <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#574652] border-b border-[#FAF6EF]">
                      Deliver in Hyderabad
                    </div>
                    {areaNames.map((area) => (
                      <button
                        key={area}
                        type="button"
                        role="option"
                        aria-selected={selectedArea === area}
                        onClick={() => {
                          setSelectedArea(area);
                          setIsAreaDropdownOpen(false);
                        }}
                        className={`w-full text-left px-3 py-2.5 text-sm flex items-center justify-between hover:bg-[#FAF6EF] transition-colors min-h-[44px] ${
                          selectedArea === area
                            ? 'font-semibold text-[#5B1E4E] bg-[#F5EDF3]'
                            : 'text-[#22161F]'
                        }`}
                      >
                        <span>{area}</span>
                        {selectedArea === area && (
                          <span className="w-2 h-2 rounded-full bg-[#5B1E4E]" />
                        )}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Desktop Navigation Links & AI CTA */}
          <nav className="hidden lg:flex items-center gap-6">
            <Link
              href="/restaurants"
              className={`text-sm font-medium transition-colors hover:text-[#5B1E4E] ${
                pathname === '/restaurants' ? 'text-[#5B1E4E] font-semibold border-b-2 border-[#5B1E4E] pb-1' : 'text-[#22161F]'
              }`}
            >
              Restaurants
            </Link>

            {/* Dawat AI Header Launcher */}
            <button
              type="button"
              onClick={() => setIsChatOpen(true)}
              className="flex items-center gap-2 px-3.5 py-2 rounded-full bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] shadow-sm transition-all text-xs font-semibold tracking-wide border border-[#D8AE4A]/40 min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#D8AE4A]"
            >
              <Sparkles className="w-3.5 h-3.5 text-[#D8AE4A]" aria-hidden="true" />
              <span>Ask Dawat AI</span>
            </button>
          </nav>

          {/* Right Action Icons: Persona Switcher, Cart & Mobile Menu */}
          <div className="flex items-center gap-2 sm:gap-3">
            {/* Profile Link */}
            <Link
              href={signedIn ? '/profile' : '/login'}
              className="p-2 sm:px-3 sm:py-2 rounded-full text-[#22161F] hover:bg-[#FAF6EF] border border-[#EADFCF] sm:border-transparent hover:border-[#EADFCF] flex items-center gap-1.5 transition-colors min-h-[44px] min-w-[44px] justify-center focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
              aria-label={signedIn ? `Profile: ${profileName}` : 'Sign in'}
            >
              <User className="w-4 h-4 text-[#5B1E4E]" aria-hidden="true" />
              <span className="hidden md:inline text-xs font-medium text-[#22161F]">
                {profileFirstName}
              </span>
            </Link>

            {signedIn && (
              <button
                type="button"
                onClick={() => void handleSignOut()}
                className="hidden lg:flex p-2 sm:px-3 sm:py-2 rounded-full text-[#22161F] hover:bg-[#FAF6EF] border border-[#EADFCF] sm:border-transparent hover:border-[#EADFCF] items-center gap-1.5 transition-colors min-h-[44px] justify-center focus-visible:ring-2 focus-visible:ring-[#5B1E4E] text-xs font-medium"
              >
                Sign out
              </button>
            )}

            {/* Cart Link with Live Item Counter Badge */}
            <Link
              href="/cart"
              className="relative flex items-center gap-2 px-3 sm:px-4 py-2 rounded-full bg-[#FFFFFF] border border-[#EADFCF] text-[#22161F] hover:border-[#5B1E4E] hover:text-[#5B1E4E] transition-all min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
              aria-label={`Cart with ${cartCount} items`}
            >
              <ShoppingBag className="w-4 h-4 text-[#5B1E4E]" aria-hidden="true" />
              <span className="hidden sm:inline text-xs font-semibold">Cart</span>
              {cartCount > 0 && (
                <span className="bg-[#5B1E4E] text-[#FAF6EF] text-[11px] font-bold px-2 py-0.5 rounded-full shrink-0">
                  {cartCount}
                </span>
              )}
            </Link>

            {/* Mobile Menu Hamburger */}
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              className="lg:hidden p-2 text-[#22161F] hover:bg-[#FAF6EF] rounded-lg min-h-[44px] min-w-[44px] flex items-center justify-center focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
              aria-expanded={isMobileMenuOpen}
              aria-label="Toggle mobile menu"
            >
              {isMobileMenuOpen ? (
                <X className="w-6 h-6 text-[#5B1E4E]" aria-hidden="true" />
              ) : (
                <Menu className="w-6 h-6 text-[#5B1E4E]" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        {/* Mobile Dropdown Menu Drawer */}
        {isMobileMenuOpen && (
          <div className="lg:hidden py-4 border-t border-[#EADFCF] space-y-3 font-sans animate-in slide-in-from-top-2">
            <div className="grid grid-cols-2 gap-2 pt-1">
              <Link
                href="/restaurants"
                onClick={() => setIsMobileMenuOpen(false)}
                className="flex items-center gap-2 p-3 rounded-xl bg-white border border-[#EADFCF] text-sm text-[#22161F] min-h-[44px]"
              >
                <Compass className="w-4 h-4 text-[#5B1E4E]" />
                <span>Restaurants</span>
              </Link>
              <button
                type="button"
                onClick={() => {
                  setIsMobileMenuOpen(false);
                  setIsChatOpen(true);
                }}
                className="flex items-center gap-2 p-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] text-sm font-medium min-h-[44px]"
              >
                <Sparkles className="w-4 h-4 text-[#D8AE4A]" />
                <span>Dawat AI</span>
              </button>
              <Link
                href="/order-tracking"
                onClick={() => setIsMobileMenuOpen(false)}
                className="flex items-center gap-2 p-3 rounded-xl bg-white border border-[#EADFCF] text-sm text-[#22161F] min-h-[44px]"
              >
                <span>Track Order</span>
              </Link>
              {signedIn ? (
                <button
                  type="button"
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    void handleSignOut();
                  }}
                  className="flex items-center gap-2 p-3 rounded-xl bg-white border border-[#EADFCF] text-sm text-[#22161F] min-h-[44px]"
                >
                  <span>Sign out</span>
                </button>
              ) : (
              <Link
                href="/login"
                onClick={() => setIsMobileMenuOpen(false)}
                className="flex items-center gap-2 p-3 rounded-xl bg-white border border-[#EADFCF] text-sm text-[#22161F] min-h-[44px]"
              >
                <span>Sign in</span>
              </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
