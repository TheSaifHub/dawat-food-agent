'use client';

import React from 'react';
import Link from 'next/link';
import { Restaurant } from '@/data/mockData';
import { FoodIllustration } from './FoodIllustration';
import { useDawat } from '@/context/DawatContext';
import { MapPin, ArrowRight, Sparkles } from 'lucide-react';

interface RestaurantCardProps {
  restaurant: Restaurant;
}

export function RestaurantCard({ restaurant }: RestaurantCardProps) {
  const { openChatWithPrompt } = useDawat();

  const primaryFoodType = restaurant.cuisines.some((c) => c.toLowerCase().includes('biryani'))
    ? 'biryani'
    : restaurant.cuisines.some((c) => c.toLowerCase().includes('chai'))
    ? 'chai'
    : restaurant.cuisines.some((c) => c.toLowerCase().includes('haleem'))
    ? 'haleem'
    : restaurant.isPureVeg
    ? 'thali'
    : 'kebab';

  return (
    <article className="group bg-white rounded-2xl border border-[#EADFCF] hover:border-[#5B1E4E] transition-all duration-200 shadow-xs hover:shadow-md overflow-hidden flex flex-col justify-between font-sans">
      <div>
        {/* Top Visual Area with Nizami Arch Motif & Neutral Food Illustration */}
        <div className="relative bg-[#FAF6EF] p-5 border-b border-[#EADFCF] flex items-center justify-between overflow-hidden">
          {/* Subtle geometric pattern backdrop */}
          <div className="absolute inset-0 opacity-40 nizami-pattern" />

          {/* Left badge & tag info */}
          <div className="relative z-10 flex flex-col gap-2 max-w-[65%]">
            <div className="flex flex-wrap items-center gap-1.5">
              {restaurant.isPureVeg ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-[#2E7D32]/10 text-[#2E7D32] border border-[#2E7D32]/30">
                  <span className="w-2 h-2 rounded-full bg-[#2E7D32]" />
                  Pure Veg
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-[#5B1E4E]/10 text-[#5B1E4E] border border-[#5B1E4E]/20">
                  <span className="w-2 h-2 rounded-full bg-[#7B241C]" />
                  Deccani Kitchen
                </span>
              )}

              <span className="text-xs font-semibold text-[#574652] px-2 py-0.5 rounded bg-white/80 border border-[#EADFCF]">
                {restaurant.priceLevel}
              </span>
            </div>

            <span className="text-xs text-[#574652] font-medium leading-tight">
              {restaurant.heroBadge}
            </span>
          </div>

          {/* Right Neutral Food Illustration (No copyrighted images rule) */}
          <div className="relative z-10 drop-shadow-xs transform group-hover:scale-105 transition-transform duration-200">
            <FoodIllustration type={primaryFoodType} size={72} />
          </div>
        </div>

        {/* Content Area */}
        <div className="p-5 space-y-3">
          <div>
            <h3 className="font-serif text-xl font-bold text-[#22161F] group-hover:text-[#5B1E4E] transition-colors leading-snug">
              <Link
                href={`/restaurant/${restaurant.id}`}
                className="focus-visible:ring-2 focus-visible:ring-[#5B1E4E] rounded"
              >
                {restaurant.name}
              </Link>
            </h3>
            <p className="text-xs text-[#574652] mt-1 line-clamp-1 italic font-serif">
              &ldquo;{restaurant.tagline}&rdquo;
            </p>
          </div>

          {/* Hard Rule Mandated Metrics: Distance & Delivery Fee (NO star ratings, NO fake time estimates) */}
          <div className="flex items-center justify-between text-xs font-medium py-2 px-3 rounded-xl bg-[#FAF6EF] border border-[#EADFCF]">
            <span className="flex items-center gap-1.5 text-[#22161F]">
              <MapPin className="w-3.5 h-3.5 text-[#5B1E4E]" aria-hidden="true" />
              <span>{restaurant.distanceKm} km away</span>
              <span className="text-[#877682]">&bull;</span>
              <span className="text-[#574652]">{restaurant.locality}</span>
            </span>

            <span
              className={`font-semibold ${
                restaurant.deliveryFee === 0 ? 'text-[#2E7D32]' : 'text-[#22161F]'
              }`}
            >
              {restaurant.deliveryFee === 0 ? 'Free Delivery' : `₹${restaurant.deliveryFee} fee`}
            </span>
          </div>

          {/* Cuisines Tags */}
          <div className="flex flex-wrap gap-1.5 pt-1">
            {restaurant.cuisines.map((cuisine) => (
              <span
                key={cuisine}
                className="text-[11px] font-sans px-2 py-0.5 rounded-md bg-white border border-[#EADFCF] text-[#574652]"
              >
                {cuisine}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Card Footer Actions */}
      <div className="p-4 pt-0 border-t border-transparent mt-2 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() =>
            openChatWithPrompt(`Tell me the best dishes and spice levels at ${restaurant.name}`)
          }
          className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#5B1E4E] hover:bg-[#F5EDF3] border border-[#5B1E4E]/20 transition-colors min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
          aria-label={`Ask Dawat AI about ${restaurant.name}`}
        >
          <Sparkles className="w-3.5 h-3.5 text-[#D8AE4A]" aria-hidden="true" />
          <span>Ask AI</span>
        </button>

        <Link
          href={`/restaurant/${restaurant.id}`}
          className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] transition-all min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
        >
          <span>View Menu</span>
          <ArrowRight className="w-3.5 h-3.5 text-[#FAF6EF]" aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}
