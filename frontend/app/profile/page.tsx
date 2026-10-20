'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useDawat } from '@/context/DawatContext';
import { MOCK_ORDERS_HISTORY, PastOrder, RESTAURANTS_DATA } from '@/data/mockData';
import {
  User,
  MapPin,
  Clock,
  Sparkles,
  Heart,
  Flame,
  Leaf,
  Plus,
  ShieldCheck,
  CheckCircle2,
  RotateCcw,
} from 'lucide-react';

export default function ProfilePage() {
  const {
    activePersona,
    switchPersona,
    openChatWithPrompt,
    addToCart,
  } = useDawat();

  const [dietPreference, setDietPreference] = useState(activePersona.dietaryPreference);
  const [spiceTolerance, setSpiceTolerance] = useState(activePersona.spiceTolerance);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleSavePreferences = (e: React.FormEvent) => {
    e.preventDefault();
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2500);
  };

  const handleReorder = (order: PastOrder) => {
    const restaurant = RESTAURANTS_DATA.find((r) => r.id === order.restaurantId) || RESTAURANTS_DATA[0];
    // Add first item as demo re-order
    if (restaurant.menu.length > 0) {
      addToCart(restaurant, restaurant.menu[0]);
    }
    openChatWithPrompt(`Re-order my feast from ${order.restaurantName} (${order.orderId})`);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 font-sans">
      {/* Profile Header & Active Persona Switcher */}
      <div className="bg-white rounded-3xl border border-[#EADFCF] p-6 sm:p-8 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-2xl bg-[#5B1E4E] text-[#FAF6EF] flex items-center justify-center font-serif text-2xl font-bold shrink-0">
            {activePersona.name.charAt(0)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[#22161F]">
                {activePersona.name}
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#5B1E4E]/10 text-[#5B1E4E] border border-[#5B1E4E]/20">
                {activePersona.roleBadge}
              </span>
            </div>
            <p className="text-xs text-[#574652] mt-0.5">
              {activePersona.email} &bull; Default Location: {activePersona.defaultAddress.area}, Hyderabad
            </p>
          </div>
        </div>

        {/* Persona Quick Toggle Bar */}
        <div className="bg-[#FAF6EF] p-2 rounded-2xl border border-[#EADFCF] flex items-center gap-2 self-start md:self-auto">
          <span className="text-[11px] font-semibold text-[#574652] px-2">Demo Role:</span>
          <button
            type="button"
            onClick={() => switchPersona('arjun')}
            className={`px-3 py-2 rounded-xl text-xs font-semibold transition-all min-h-[44px] ${
              activePersona.id === 'arjun'
                ? 'bg-[#5B1E4E] text-[#FAF6EF] shadow-xs'
                : 'bg-white text-[#22161F] hover:bg-white/80'
            }`}
          >
            Arjun (Spicy)
          </button>
          <button
            type="button"
            onClick={() => switchPersona('priya')}
            className={`px-3 py-2 rounded-xl text-xs font-semibold transition-all min-h-[44px] ${
              activePersona.id === 'priya'
                ? 'bg-[#5B1E4E] text-[#FAF6EF] shadow-xs'
                : 'bg-white text-[#22161F] hover:bg-white/80'
            }`}
          >
            Priya (Veg)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Saved Preferences & Addresses */}
        <div className="lg:col-span-5 space-y-6">
          {/* 1. Saved Dietary & Culinary Preferences */}
          <section className="bg-white rounded-2xl border border-[#EADFCF] p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-[#FAF6EF]">
              <h2 className="font-serif text-lg font-bold text-[#22161F] flex items-center gap-2">
                <Heart className="w-4 h-4 text-[#5B1E4E]" />
                <span>Saved Taste Preferences</span>
              </h2>
              <span className="text-[11px] text-[#574652]">Synced with Dawat AI</span>
            </div>

            <form onSubmit={handleSavePreferences} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#574652] mb-1.5">
                  Dietary Classification
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setDietPreference('Vegetarian')}
                    className={`p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 min-h-[44px] ${
                      dietPreference === 'Vegetarian'
                        ? 'bg-[#2E7D32]/10 border-[#2E7D32] text-[#2E7D32]'
                        : 'border-[#EADFCF] bg-[#FAF6EF]/40 text-[#574652]'
                    }`}
                  >
                    <Leaf className="w-4 h-4" />
                    <span>Pure Vegetarian</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setDietPreference('Non-Vegetarian')}
                    className={`p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 min-h-[44px] ${
                      dietPreference === 'Non-Vegetarian'
                        ? 'bg-[#5B1E4E]/10 border-[#5B1E4E] text-[#5B1E4E]'
                        : 'border-[#EADFCF] bg-[#FAF6EF]/40 text-[#574652]'
                    }`}
                  >
                    <Flame className="w-4 h-4" />
                    <span>Non-Vegetarian</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#574652] mb-1.5">
                  Spice Tolerance Profile
                </label>
                <select
                  value={spiceTolerance}
                  onChange={(e) => setSpiceTolerance(e.target.value as any)}
                  className="w-full px-3 py-2.5 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/40 text-xs text-[#22161F] font-medium min-h-[44px] focus:outline-none focus:ring-2 focus:ring-[#5B1E4E]"
                >
                  <option value="Not spicy">Not spicy (Mild fragrant notes only)</option>
                  <option value="Mild">Mild (Gentle whole spices)</option>
                  <option value="Medium">Medium (Balanced Nizami warmth)</option>
                  <option value="Hot">Hot (Fiery Guntur chillies &amp; black pepper)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#574652] mb-1.5">
                  Favorite Hyderabad Delicacies
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {activePersona.favoriteCuisines.map((fav) => (
                    <span
                      key={fav}
                      className="px-2.5 py-1 rounded-lg bg-[#FAF6EF] border border-[#EADFCF] text-xs text-[#22161F] font-medium"
                    >
                      {fav}
                    </span>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] text-xs font-semibold transition-all min-h-[44px] flex items-center justify-center gap-1.5 focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
              >
                {saveSuccess ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-[#D8AE4A]" />
                    <span>Preferences Updated</span>
                  </>
                ) : (
                  <span>Save Preferences</span>
                )}
              </button>
            </form>
          </section>

          {/* 2. Saved Addresses */}
          <section className="bg-white rounded-2xl border border-[#EADFCF] p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-[#FAF6EF]">
              <h2 className="font-serif text-lg font-bold text-[#22161F] flex items-center gap-2">
                <MapPin className="w-4 h-4 text-[#5B1E4E]" />
                <span>Saved Addresses</span>
              </h2>
            </div>

            <div className="space-y-3">
              {activePersona.savedAddresses.map((addr) => (
                <div
                  key={addr.id}
                  className="p-3.5 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/40 space-y-1 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[#5B1E4E]">{addr.label}</span>
                    <span className="text-[10px] text-[#2E7D32] bg-[#2E7D32]/10 px-2 py-0.5 rounded font-semibold">
                      Verified Locality
                    </span>
                  </div>
                  <p className="text-[#22161F] font-medium">{addr.line1}</p>
                  <p className="text-[#574652]">{addr.area}, {addr.city} - {addr.pincode}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* Right Column: Order History */}
        <div className="lg:col-span-7 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-serif text-2xl font-bold text-[#22161F]">
                Past Feasts &amp; Order History
              </h2>
              <p className="text-xs text-[#574652]">
                Re-order your favorite Hyderabad meals with one click
              </p>
            </div>
          </div>

          <div className="space-y-4">
            {MOCK_ORDERS_HISTORY.map((order) => (
              <div
                key={order.orderId}
                className="bg-white rounded-2xl border border-[#EADFCF] p-5 shadow-xs space-y-4 hover:border-[#5B1E4E] transition-all"
              >
                {/* Order Top Bar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-[#FAF6EF]">
                  <div>
                    <h3 className="font-serif text-lg font-bold text-[#22161F]">
                      {order.restaurantName}
                    </h3>
                    <div className="flex items-center gap-2 text-xs text-[#574652]">
                      <span>Order #{order.orderId}</span>
                      <span>&bull;</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-[#5B1E4E]" />
                        {order.date}
                      </span>
                    </div>
                  </div>

                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#2E7D32]/10 text-[#2E7D32] self-start sm:self-auto border border-[#2E7D32]/20">
                    {order.status}
                  </span>
                </div>

                {/* Items */}
                <div className="space-y-1.5 text-xs text-[#22161F]">
                  {order.items.map((it, idx) => (
                    <div key={idx} className="flex justify-between items-center">
                      <span>
                        <strong className="text-[#5B1E4E]">{it.quantity}x</strong> {it.name}
                      </span>
                      <span className="text-[#574652]">₹{it.price * it.quantity}</span>
                    </div>
                  ))}
                </div>

                {/* Order Total & Actions */}
                <div className="pt-3 border-t border-[#EADFCF] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-[11px] text-[#574652] block">Bill Total (One Kitchen)</span>
                    <span className="font-mono text-base font-bold text-[#5B1E4E]">
                      ₹{order.grandTotal}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 self-stretch sm:self-auto">
                    <button
                      type="button"
                      onClick={() => handleReorder(order)}
                      className="flex-1 sm:flex-initial px-4 py-2 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] text-xs font-semibold transition-all flex items-center justify-center gap-1.5 min-h-[44px]"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Re-order Feast</span>
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        openChatWithPrompt(
                          `Review my past order ${order.orderId} from ${order.restaurantName} and suggest complementary desserts`
                        )
                      }
                      className="px-3 py-2 rounded-xl border border-[#EADFCF] text-[#5B1E4E] hover:bg-[#F5EDF3] text-xs font-semibold transition-colors min-h-[44px] flex items-center justify-center gap-1"
                      title="Ask Dawat AI about this order"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-[#D8AE4A]" />
                      <span className="hidden sm:inline">Ask AI</span>
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
