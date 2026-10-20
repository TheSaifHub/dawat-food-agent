import React from 'react';
import { notFound } from 'next/navigation';
import { RESTAURANTS_DATA, Restaurant } from '@/data/mockData';
import { MenuItemRow } from '@/components/MenuItemRow';
import { MapPlaceholder } from '@/components/MapPlaceholder';
import { FoodIllustration } from '@/components/FoodIllustration';
import { CartBill } from '@/components/CartBill';
import { MapPin, ShieldCheck, Sparkles, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

// Pre-render all restaurant paths statically
export function generateStaticParams() {
  return RESTAURANTS_DATA.map((restaurant) => ({
    id: restaurant.id,
  }));
}

interface RestaurantPageProps {
  params: Promise<{ id: string }>;
}

export default async function RestaurantDetailPage({ params }: RestaurantPageProps) {
  const { id } = await params;
  const restaurant = RESTAURANTS_DATA.find((r) => r.id === id);

  if (!restaurant) {
    notFound();
  }

  // Group items by category
  const categories = restaurant.menuCategories;
  const menuByCategory = categories.map((cat) => ({
    categoryName: cat,
    items: restaurant.menu.filter((m) => m.category === cat),
  }));

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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 font-sans">
      {/* Back to Listing link */}
      <div>
        <Link
          href="/restaurants"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#574652] hover:text-[#5B1E4E] transition-colors focus-visible:ring-1 focus-visible:ring-[#5B1E4E] rounded py-1 px-2"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to All Kitchens</span>
        </Link>
      </div>

      {/* 1. Restaurant Header */}
      <section className="bg-white rounded-3xl border border-[#EADFCF] shadow-xs overflow-hidden">
        {/* Banner with Nizami Pattern and Food Art */}
        <div className="relative bg-[#5B1E4E] text-[#FAF6EF] p-6 sm:p-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 overflow-hidden">
          <div className="absolute inset-0 opacity-15 nizami-pattern-dark pointer-events-none" />

          <div className="relative z-10 space-y-2 max-w-xl">
            <div className="flex flex-wrap items-center gap-2">
              {restaurant.isPureVeg ? (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#2E7D32] text-white">
                  100% Pure Vegetarian
                </span>
              ) : (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white/20 text-[#FAF6EF] border border-white/30">
                  Deccani Kitchen
                </span>
              )}
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#D8AE4A] text-[#22161F]">
                {restaurant.heroBadge}
              </span>
            </div>

            <h1 className="font-serif text-3xl sm:text-4xl font-bold text-white tracking-tight">
              {restaurant.name}
            </h1>
            <p className="text-sm text-[#FAF6EF]/90 italic font-serif">
              &ldquo;{restaurant.tagline}&rdquo;
            </p>
            <p className="text-xs text-[#FAF6EF]/75 font-sans pt-1">
              {restaurant.address}
            </p>
          </div>

          <div className="relative z-10 shrink-0 self-center sm:self-auto">
            <div className="w-24 h-24 rounded-2xl bg-white/10 backdrop-blur-md border border-white/20 p-2 flex items-center justify-center">
              <FoodIllustration type={primaryFoodType} size={80} />
            </div>
          </div>
        </div>

        {/* Header Stats Bar: Distance & Delivery fee (Hard rule compliant) */}
        <div className="p-4 sm:p-5 bg-[#FAF6EF] border-t border-[#EADFCF] flex flex-wrap items-center justify-between gap-4 text-xs font-medium text-[#22161F]">
          <div className="flex flex-wrap items-center gap-4 sm:gap-6">
            <span className="flex items-center gap-1.5 font-semibold">
              <MapPin className="w-4 h-4 text-[#5B1E4E]" aria-hidden="true" />
              <span>{restaurant.distanceKm} km from your area</span>
            </span>

            <span>&bull;</span>

            <span className="font-semibold">
              {restaurant.deliveryFee === 0 ? (
                <span className="text-[#2E7D32]">Free Delivery</span>
              ) : (
                `₹${restaurant.deliveryFee} delivery fee`
              )}
            </span>

            <span>&bull;</span>

            <span className="text-[#574652]">
              Price Tier: <strong className="text-[#22161F]">{restaurant.priceLevel}</strong>
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-[11px] text-[#574652]">
            <ShieldCheck className="w-3.5 h-3.5 text-[#2E7D32]" />
            <span>Single Kitchen Billing Guarantee</span>
          </div>
        </div>
      </section>

      {/* 2. Map Placeholder & Locality Overview */}
      <section className="space-y-2">
        <h2 className="font-serif text-xl font-bold text-[#22161F]">
          Location &amp; Delivery Zone
        </h2>
        <MapPlaceholder
          restaurantName={restaurant.name}
          distanceKm={restaurant.distanceKm}
          locality={restaurant.locality}
        />
      </section>

      {/* 3. Main Body: Menu categorized by category + Cart Bill sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start pt-4">
        {/* Left Column: Menu Categories */}
        <div className="lg:col-span-8 space-y-10">
          {/* Category Anchor Pills */}
          <div className="sticky top-20 z-20 bg-[#FAF6EF]/95 backdrop-blur-md py-2 flex items-center gap-2 overflow-x-auto no-scrollbar border-b border-[#EADFCF]">
            {menuByCategory.map(({ categoryName }) => (
              <a
                key={categoryName}
                href={`#cat-${categoryName.replace(/\s+/g, '-').toLowerCase()}`}
                className="shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold bg-white border border-[#EADFCF] text-[#22161F] hover:border-[#5B1E4E] hover:text-[#5B1E4E] transition-colors focus-visible:ring-1 focus-visible:ring-[#5B1E4E]"
              >
                {categoryName}
              </a>
            ))}
          </div>

          {/* Menu Sections */}
          {menuByCategory.map(({ categoryName, items }) => (
            <section
              key={categoryName}
              id={`cat-${categoryName.replace(/\s+/g, '-').toLowerCase()}`}
              className="space-y-4 scroll-mt-36"
            >
              <div className="flex items-center justify-between pb-2 border-b-2 border-[#5B1E4E]/20">
                <h2 className="font-serif text-2xl font-bold text-[#22161F]">
                  {categoryName}
                </h2>
                <span className="text-xs text-[#574652] font-sans">
                  {items.length} {items.length === 1 ? 'dish' : 'dishes'}
                </span>
              </div>

              <div className="space-y-3">
                {items.map((item) => (
                  <MenuItemRow
                    key={item.id}
                    restaurant={{
                      id: restaurant.id,
                      name: restaurant.name,
                      deliveryFee: restaurant.deliveryFee,
                    }}
                    item={item}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>

        {/* Right Column: Sticky Cart and Checkout Summary */}
        <div className="lg:col-span-4 sticky top-28 space-y-4">
          <CartBill />
        </div>
      </div>
    </div>
  );
}
