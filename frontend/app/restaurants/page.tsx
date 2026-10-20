'use client';

import React, { useState, useMemo } from 'react';
import { RESTAURANTS_DATA, CUISINES_LIST } from '@/data/mockData';
import { RestaurantCard } from '@/components/RestaurantCard';
import { useDawat } from '@/context/DawatContext';
import {
  SlidersHorizontal,
  RotateCcw,
  MapPin,
  Check,
  Search,
  Sparkles,
} from 'lucide-react';

export default function RestaurantListingPage() {
  const { selectedArea, openChatWithPrompt, activePersona } = useDawat();

  // Filter states
  const [vegOnly, setVegOnly] = useState(activePersona.dietaryPreference === 'Vegetarian');
  const [selectedCuisine, setSelectedCuisine] = useState<string>('all');
  const [selectedPrice, setSelectedPrice] = useState<string>('all');
  const [maxDistance, setMaxDistance] = useState<number>(10);
  const [deliveryFeeFilter, setDeliveryFeeFilter] = useState<'all' | 'free' | 'under30'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'distance' | 'price' | 'delivery'>('distance');

  // Filter computation
  const filteredRestaurants = useMemo(() => {
    return RESTAURANTS_DATA.filter((r) => {
      // Veg only
      if (vegOnly && !r.isPureVeg) {
        return false;
      }
      // Cuisine
      if (selectedCuisine !== 'all') {
        const matchesCuisine = r.cuisines.some((c) =>
          c.toLowerCase().includes(selectedCuisine.toLowerCase())
        );
        if (!matchesCuisine) return false;
      }
      // Price
      if (selectedPrice !== 'all' && r.priceLevel !== selectedPrice) {
        return false;
      }
      // Distance
      if (r.distanceKm > maxDistance) {
        return false;
      }
      // Delivery fee
      if (deliveryFeeFilter === 'free' && r.deliveryFee !== 0) {
        return false;
      }
      if (deliveryFeeFilter === 'under30' && r.deliveryFee >= 30) {
        return false;
      }
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchName = r.name.toLowerCase().includes(q);
        const matchCuisine = r.cuisines.some((c) => c.toLowerCase().includes(q));
        const matchLocality = r.locality.toLowerCase().includes(q);
        if (!matchName && !matchCuisine && !matchLocality) return false;
      }

      return true;
    }).sort((a, b) => {
      if (sortBy === 'distance') return a.distanceKm - b.distanceKm;
      if (sortBy === 'delivery') return a.deliveryFee - b.deliveryFee;
      if (sortBy === 'price') return a.priceLevel.length - b.priceLevel.length;
      return 0;
    });
  }, [vegOnly, selectedCuisine, selectedPrice, maxDistance, deliveryFeeFilter, searchQuery, sortBy]);

  const resetFilters = () => {
    setVegOnly(false);
    setSelectedCuisine('all');
    setSelectedPrice('all');
    setMaxDistance(10);
    setDeliveryFeeFilter('all');
    setSearchQuery('');
    setSortBy('distance');
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 font-sans">
      {/* Header & Area context */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-[#5B1E4E] uppercase tracking-wider">
              <MapPin className="w-3.5 h-3.5" />
              <span>Hyderabad &bull; Delivering in {selectedArea}</span>
            </div>
            <h1 className="font-serif text-3xl sm:text-4xl font-bold text-[#22161F] mt-1">
              Dastarkhwans &amp; Kitchens
            </h1>
          </div>

          {/* Quick AI Search helper */}
          <button
            type="button"
            onClick={() =>
              openChatWithPrompt(
                `Find the best restaurants near ${selectedArea} matching my preferences (${activePersona.roleBadge})`
              )
            }
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] text-xs font-semibold shadow-xs transition-all self-start sm:self-auto min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
          >
            <Sparkles className="w-4 h-4 text-[#D8AE4A]" aria-hidden="true" />
            <span>Filter with Dawat AI</span>
          </button>
        </div>

        <p className="text-xs sm:text-sm text-[#574652] max-w-2xl">
          Order from authenticated Hyderabad kitchens with verified distances and clear delivery fees. No star ratings, no artificial estimates.
        </p>
      </div>

      {/* Search & Filter Control Bar */}
      <div className="bg-white p-4 sm:p-5 rounded-2xl border border-[#EADFCF] shadow-xs space-y-4">
        {/* Top Search & Reset Row */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[#877682] absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by restaurant name, cuisine (e.g. Biryani, Haleem), or locality..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/50 text-xs sm:text-sm text-[#22161F] placeholder-[#877682] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#5B1E4E] min-h-[44px]"
            />
          </div>

          <div className="flex items-center gap-2">
            {/* Sort Dropdown */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="px-3 py-2.5 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/50 text-xs text-[#22161F] font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#5B1E4E] min-h-[44px]"
              aria-label="Sort restaurants"
            >
              <option value="distance">Sort by: Distance (Nearest)</option>
              <option value="delivery">Sort by: Delivery Fee</option>
              <option value="price">Sort by: Price Level</option>
            </select>

            {/* Reset Button */}
            <button
              type="button"
              onClick={resetFilters}
              className="px-3 py-2.5 rounded-xl border border-[#EADFCF] bg-white text-[#574652] hover:text-[#22161F] hover:bg-[#FAF6EF] text-xs font-semibold flex items-center gap-1.5 transition-colors min-h-[44px]"
              title="Reset all filters"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Reset</span>
            </button>
          </div>
        </div>

        {/* Filter Controls Row: Veg Only, Cuisine, Price, Distance, Delivery Fee */}
        <div className="pt-2 border-t border-[#FAF6EF] flex flex-wrap items-center gap-2.5">
          {/* Veg Only Toggle */}
          <button
            type="button"
            onClick={() => setVegOnly((prev) => !prev)}
            className={`px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-2 transition-all min-h-[44px] border ${
              vegOnly
                ? 'bg-[#2E7D32] text-white border-[#2E7D32]'
                : 'bg-white text-[#22161F] border-[#EADFCF] hover:border-[#2E7D32]'
            }`}
            aria-pressed={vegOnly}
          >
            <div
              className={`w-3.5 h-3.5 rounded-xs border flex items-center justify-center ${
                vegOnly ? 'border-white' : 'border-[#2E7D32]'
              }`}
            >
              <div className={`w-1.5 h-1.5 rounded-full ${vegOnly ? 'bg-white' : 'bg-[#2E7D32]'}`} />
            </div>
            <span>Pure Veg Only</span>
          </button>

          {/* Cuisine Selector */}
          <select
            value={selectedCuisine}
            onChange={(e) => setSelectedCuisine(e.target.value)}
            className="px-3 py-2 rounded-xl border border-[#EADFCF] bg-white text-xs text-[#22161F] font-medium min-h-[44px] focus:outline-none focus:ring-2 focus:ring-[#5B1E4E]"
            aria-label="Filter by Cuisine"
          >
            <option value="all">All Cuisines</option>
            <option value="Biryani">Dum Biryani</option>
            <option value="Mughlai">Nizami Mughlai</option>
            <option value="Pure Veg">Pure Veg Nizami</option>
            <option value="Irani">Irani Chai &amp; Osmania</option>
            <option value="Haleem">Slow-Cooked Haleem</option>
            <option value="Kebab">Kebabs &amp; Tandoor</option>
            <option value="Dessert">Meetha &amp; Desserts</option>
          </select>

          {/* Price Selector */}
          <select
            value={selectedPrice}
            onChange={(e) => setSelectedPrice(e.target.value)}
            className="px-3 py-2 rounded-xl border border-[#EADFCF] bg-white text-xs text-[#22161F] font-medium min-h-[44px] focus:outline-none focus:ring-2 focus:ring-[#5B1E4E]"
            aria-label="Filter by Price Tier"
          >
            <option value="all">All Prices</option>
            <option value="₹">₹ (Budget-friendly)</option>
            <option value="₹₹">₹₹ (Moderate Dastarkhwan)</option>
            <option value="₹₹₹">₹₹₹ (Royal Feast)</option>
          </select>

          {/* Max Distance Selector */}
          <select
            value={maxDistance}
            onChange={(e) => setMaxDistance(Number(e.target.value))}
            className="px-3 py-2 rounded-xl border border-[#EADFCF] bg-white text-xs text-[#22161F] font-medium min-h-[44px] focus:outline-none focus:ring-2 focus:ring-[#5B1E4E]"
            aria-label="Filter by Distance"
          >
            <option value={10}>Any Distance (up to 10 km)</option>
            <option value={2}>Under 2 km (Immediate vicinity)</option>
            <option value={3}>Under 3 km</option>
            <option value={5}>Under 5 km</option>
          </select>

          {/* Delivery Fee Selector */}
          <select
            value={deliveryFeeFilter}
            onChange={(e) => setDeliveryFeeFilter(e.target.value as any)}
            className="px-3 py-2 rounded-xl border border-[#EADFCF] bg-white text-xs text-[#22161F] font-medium min-h-[44px] focus:outline-none focus:ring-2 focus:ring-[#5B1E4E]"
            aria-label="Filter by Delivery Fee"
          >
            <option value="all">Any Delivery Fee</option>
            <option value="free">Free Delivery Only</option>
            <option value="under30">Under ₹30 Delivery Fee</option>
          </select>
        </div>
      </div>

      {/* Results Count & Grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-xs text-[#574652]">
          <span>
            Showing <strong className="text-[#22161F]">{filteredRestaurants.length}</strong> verified kitchens
          </span>
          {vegOnly && (
            <span className="text-[#2E7D32] font-semibold">
              Filter: 100% Pure Vegetarian
            </span>
          )}
        </div>

        {filteredRestaurants.length === 0 ? (
          <div className="bg-white rounded-2xl border border-[#EADFCF] p-12 text-center space-y-4">
            <SlidersHorizontal className="w-12 h-12 text-[#877682] mx-auto opacity-40" />
            <h3 className="font-serif text-2xl font-bold text-[#22161F]">
              No kitchens matched these exact filters
            </h3>
            <p className="text-xs text-[#574652] max-w-sm mx-auto">
              Try adjusting your distance slider, removing the pure veg constraint, or ask Dawat AI to suggest kitchens that fit your party.
            </p>
            <button
              type="button"
              onClick={resetFilters}
              className="px-5 py-2.5 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] text-xs font-semibold hover:bg-[#49173E] min-h-[44px]"
            >
              Clear All Filters
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredRestaurants.map((restaurant) => (
              <RestaurantCard key={restaurant.id} restaurant={restaurant} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
