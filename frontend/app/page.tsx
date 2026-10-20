'use client';

import React from 'react';
import Link from 'next/link';
import { useDawat } from '@/context/DawatContext';
import {
  CUISINES_LIST,
  FAMOUS_CHAINS,
  RESTAURANTS_DATA,
  HYDERABAD_AREAS,
} from '@/data/mockData';
import { RestaurantCard } from '@/components/RestaurantCard';
import { FoodIllustration } from '@/components/FoodIllustration';
import { DawatLogo } from '@/components/DawatLogo';
import {
  Sparkles,
  MapPin,
  ArrowRight,
  Flame,
  Leaf,
  ChevronRight,
  Building2,
  Clock,
  ShieldCheck,
} from 'lucide-react';

export default function HomePage() {
  const {
    selectedArea,
    setSelectedArea,
    openChatWithPrompt,
    activePersona,
    switchPersona,
  } = useDawat();

  const curatedRestaurants = RESTAURANTS_DATA.slice(0, 4);

  return (
    <div className="space-y-12 pb-16 font-sans">
      {/* 1. Hero Section with Nizami Arch Silhouette & "Just ask Dawat AI" Spotlight */}
      <section className="relative bg-[#5B1E4E] text-[#FAF6EF] overflow-hidden border-b-4 border-[#D8AE4A]">
        {/* Subtle geometric pattern */}
        <div className="absolute inset-0 opacity-15 nizami-pattern-dark pointer-events-none" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16 relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            {/* Left Brand & Headline */}
            <div className="lg:col-span-7 space-y-6">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 backdrop-blur-md border border-[#D8AE4A]/50 text-xs text-[#FAF6EF]">
                <Sparkles className="w-3.5 h-3.5 text-[#D8AE4A]" aria-hidden="true" />
                <span className="tracking-wide">Hyderabad&apos;s Royal Culinary Heritage</span>
              </div>

              <div className="space-y-3">
                <h1 className="font-serif text-3xl sm:text-5xl lg:text-6xl font-bold text-white tracking-tight leading-[1.15]">
                  Every order, <br />
                  <span className="italic font-normal text-[#FAF6EF]/95">
                    a Nizami feast.
                  </span>
                </h1>
                <p className="text-sm sm:text-base text-[#FAF6EF]/85 max-w-xl font-sans leading-relaxed">
                  Authentic charcoal dum biryanis, 12-hour simmered haleem, and fragrant Irani chai delivered from the finest dastarkhwans of the Deccan.
                </p>
              </div>

              {/* Quick Area Picker in Hero */}
              <div className="bg-white p-3 rounded-2xl shadow-xl flex flex-col sm:flex-row items-stretch sm:items-center gap-2 max-w-lg border border-[#EADFCF]">
                <div className="flex items-center gap-2.5 px-3 py-2 text-[#22161F] flex-1">
                  <MapPin className="w-5 h-5 text-[#5B1E4E] shrink-0" aria-hidden="true" />
                  <div className="text-left">
                    <span className="text-[10px] uppercase font-bold text-[#574652] block">
                      Delivering in Hyderabad
                    </span>
                    <select
                      value={selectedArea}
                      onChange={(e) => setSelectedArea(e.target.value)}
                      className="bg-transparent font-medium text-sm text-[#22161F] focus:outline-none cursor-pointer pr-4"
                      aria-label="Select Hyderabad Delivery Area"
                    >
                      {HYDERABAD_AREAS.map((a) => (
                        <option key={a} value={a} className="text-[#22161F]">
                          {a}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <Link
                  href="/restaurants"
                  className="px-5 py-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] text-xs font-semibold uppercase tracking-wider flex items-center justify-center gap-2 transition-all min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
                >
                  <span>Explore Menus</span>
                  <ArrowRight className="w-4 h-4 text-[#FAF6EF]" aria-hidden="true" />
                </Link>
              </div>

              {/* Persona Pill Hints */}
              <div className="flex items-center gap-2 text-xs text-[#FAF6EF]/80 pt-1">
                <span className="text-[11px]">Browsing as:</span>
                <span className="px-2.5 py-0.5 rounded-full bg-white/15 text-white font-medium border border-white/20">
                  {activePersona.name} ({activePersona.dietaryPreference})
                </span>
                <Link
                  href="/login"
                  className="underline hover:text-white transition-colors text-[11px]"
                >
                  Change Persona
                </Link>
              </div>
            </div>

            {/* Right: "Just ask Dawat AI" Interactive Showcase Box */}
            <div className="lg:col-span-5">
              <div className="bg-[#FAF6EF] text-[#22161F] rounded-3xl p-6 shadow-2xl border-2 border-[#D8AE4A] space-y-5">
                <div className="flex items-center justify-between pb-3 border-b border-[#EADFCF]">
                  <div className="flex items-center gap-2.5">
                    <div className="w-10 h-10 rounded-xl bg-[#5B1E4E] flex items-center justify-center text-[#D8AE4A]">
                      <Sparkles className="w-5 h-5 text-[#D8AE4A]" aria-hidden="true" />
                    </div>
                    <div>
                      <h2 className="font-serif text-lg font-bold text-[#22161F] leading-tight">
                        Just ask Dawat AI
                      </h2>
                      <p className="text-xs text-[#574652]">
                        Your private Nizami ordering concierge
                      </p>
                    </div>
                  </div>
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#5B1E4E]/10 text-[#5B1E4E]">
                    Simulated AI
                  </span>
                </div>

                <p className="text-xs text-[#574652] leading-relaxed">
                  Tell Dawat AI what your party craves. It selects the ideal restaurants in {selectedArea}, calculates portions, and builds your single-restaurant bill.
                </p>

                {/* Instant Prompt Starters */}
                <div className="space-y-2">
                  <div className="text-[11px] font-bold text-[#574652] uppercase tracking-wider">
                    Try a 1-tap request:
                  </div>

                  <button
                    type="button"
                    onClick={() =>
                      openChatWithPrompt(
                        'Plan a 4-person family dinner under ₹1,200 with biryani and starters'
                      )
                    }
                    className="w-full p-2.5 rounded-xl bg-white border border-[#EADFCF] hover:border-[#5B1E4E] text-left text-xs text-[#22161F] hover:bg-[#F5EDF3] transition-all flex items-center justify-between group min-h-[44px]"
                  >
                    <span className="font-medium group-hover:text-[#5B1E4E]">
                      &ldquo;Plan a 4-person family dinner under ₹1,200&rdquo;
                    </span>
                    <ChevronRight className="w-4 h-4 text-[#574652] group-hover:text-[#5B1E4E] shrink-0" />
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      openChatWithPrompt(
                        'Recommend the spiciest mutton biryani with mirchi salan and roomali'
                      )
                    }
                    className="w-full p-2.5 rounded-xl bg-white border border-[#EADFCF] hover:border-[#5B1E4E] text-left text-xs text-[#22161F] hover:bg-[#F5EDF3] transition-all flex items-center justify-between group min-h-[44px]"
                  >
                    <span className="font-medium group-hover:text-[#5B1E4E]">
                      &ldquo;Spicy mutton feast with salan &amp; roomali&rdquo;
                    </span>
                    <ChevronRight className="w-4 h-4 text-[#574652] group-hover:text-[#5B1E4E] shrink-0" />
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      openChatWithPrompt(
                        'Curate a mild 100% vegetarian lunch with Bagara Baingan and Thali'
                      )
                    }
                    className="w-full p-2.5 rounded-xl bg-white border border-[#EADFCF] hover:border-[#5B1E4E] text-left text-xs text-[#22161F] hover:bg-[#F5EDF3] transition-all flex items-center justify-between group min-h-[44px]"
                  >
                    <span className="font-medium group-hover:text-[#5B1E4E]">
                      &ldquo;Mild vegetarian lunch for kids and family&rdquo;
                    </span>
                    <ChevronRight className="w-4 h-4 text-[#574652] group-hover:text-[#5B1E4E] shrink-0" />
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => openChatWithPrompt('Hello Dawat AI! What is fresh and special in Hyderabad today?')}
                  className="w-full py-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] font-semibold text-xs tracking-wider uppercase flex items-center justify-center gap-2 transition-all min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
                >
                  <Sparkles className="w-4 h-4 text-[#D8AE4A]" aria-hidden="true" />
                  <span>Launch Concierge Dialogue</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Cuisine Shortcuts */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-serif text-2xl sm:text-3xl font-bold text-[#22161F]">
              Hyderabad Specialties
            </h2>
            <p className="text-xs sm:text-sm text-[#574652]">
              Explore culinary masterpieces perfected over three centuries
            </p>
          </div>
          <Link
            href="/restaurants"
            className="text-xs sm:text-sm font-semibold text-[#5B1E4E] hover:underline flex items-center gap-1 focus-visible:ring-1 focus-visible:ring-[#5B1E4E]"
          >
            <span>All Cuisines</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Scrollable / Grid of Cuisines with Neutral Food Vector Art */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {CUISINES_LIST.map((c) => (
            <Link
              key={c.id}
              href={`/restaurants?cuisine=${encodeURIComponent(c.name)}`}
              className="p-3.5 bg-white rounded-2xl border border-[#EADFCF] hover:border-[#5B1E4E] transition-all hover:shadow-md flex flex-col items-center text-center space-y-2 group focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
            >
              <div className="w-14 h-14 rounded-full bg-[#FAF6EF] flex items-center justify-center group-hover:scale-105 transition-transform">
                <FoodIllustration type={c.iconName as any} size={48} />
              </div>
              <div>
                <span className="font-serif text-sm font-bold text-[#22161F] group-hover:text-[#5B1E4E] block leading-tight">
                  {c.name}
                </span>
                <span className="text-[11px] text-[#574652] block mt-0.5">
                  {c.count} kitchens
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* 3. Chains Near You (Hard rule requirement) */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-serif text-2xl sm:text-3xl font-bold text-[#22161F]">
              Chains Near You in {selectedArea}
            </h2>
            <p className="text-xs sm:text-sm text-[#574652]">
              Legacy brands with multiple authentic branches across Hyderabad
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FAMOUS_CHAINS.map((chain) => (
            <div
              key={chain.name}
              className="p-5 bg-white rounded-2xl border border-[#EADFCF] hover:border-[#5B1E4E] shadow-xs space-y-3 flex flex-col justify-between"
            >
              <div className="space-y-2">
                <div className="w-9 h-9 rounded-xl bg-[#5B1E4E]/10 text-[#5B1E4E] flex items-center justify-center">
                  <Building2 className="w-5 h-5" aria-hidden="true" />
                </div>
                <h3 className="font-serif text-lg font-bold text-[#22161F] leading-tight">
                  {chain.name}
                </h3>
                <p className="text-xs text-[#5B1E4E] font-medium">
                  {chain.highlight}
                </p>
                <p className="text-[11px] text-[#574652] leading-relaxed">
                  Branches: {chain.branches}
                </p>
              </div>

              <div className="pt-3 border-t border-[#FAF6EF] flex items-center justify-between text-xs text-[#22161F]">
                <span className="flex items-center gap-1 text-[#574652]">
                  <MapPin className="w-3.5 h-3.5 text-[#5B1E4E]" />
                  <span>{chain.distanceKm} km</span>
                </span>
                <span className="font-semibold">
                  {chain.deliveryFee === 0 ? (
                    <span className="text-[#2E7D32]">Free delivery</span>
                  ) : (
                    `₹${chain.deliveryFee} fee`
                  )}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 4. Curated Kitchens Selection */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-serif text-2xl sm:text-3xl font-bold text-[#22161F]">
              Handcrafted Kitchens Delivering to {selectedArea}
            </h2>
            <p className="text-xs sm:text-sm text-[#574652]">
              Real distance &amp; delivery fee. No star ratings, no artificial time promises.
            </p>
          </div>
          <Link
            href="/restaurants"
            className="text-xs sm:text-sm font-semibold text-[#5B1E4E] hover:underline flex items-center gap-1 focus-visible:ring-1 focus-visible:ring-[#5B1E4E]"
          >
            <span>See All ({RESTAURANTS_DATA.length})</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {curatedRestaurants.map((restaurant) => (
            <RestaurantCard key={restaurant.id} restaurant={restaurant} />
          ))}
        </div>
      </section>

      {/* 5. The Dawat Promise Banner */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-[#FAF6EF] rounded-3xl p-6 sm:p-8 border-2 border-[#EADFCF] flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="space-y-2 max-w-xl">
            <h3 className="font-serif text-2xl font-bold text-[#22161F]">
              The Dawat Nizami Dastarkhwan Standard
            </h3>
            <p className="text-xs sm:text-sm text-[#574652] leading-relaxed">
              We never pool multiple orders from distant restaurants into one box. You get one dedicated bill per kitchen, freshly packed in insulated thermal carriers with zero compromises on dum aroma.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-[#EADFCF] text-xs font-semibold text-[#22161F]">
              <ShieldCheck className="w-4 h-4 text-[#2E7D32]" />
              <span>One Bill Per Kitchen</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-[#EADFCF] text-xs font-semibold text-[#22161F]">
              <Sparkles className="w-4 h-4 text-[#D8AE4A]" />
              <span>Dawat AI Concierge</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
