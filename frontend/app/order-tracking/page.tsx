'use client';

import React from 'react';
import Link from 'next/link';
import { useDawat } from '@/context/DawatContext';
import { StatusTimeline } from '@/components/StatusTimeline';
import { MapPlaceholder } from '@/components/MapPlaceholder';
import {
  PackageCheck,
  MapPin,
  Sparkles,
  Receipt,
  Phone,
  ShieldCheck,
  ArrowRight,
  Utensils,
} from 'lucide-react';

export default function OrderTrackingPage() {
  const { activeOrder, openChatWithPrompt } = useDawat();

  const currentOrder = activeOrder || {
    orderId: 'DWT-90214',
    restaurantId: 'nawabs-dastarkhwan',
    restaurantName: "Nawab's Dastarkhwan",
    date: 'Just now',
    items: [
      { name: 'Mutton Dum Biryani (Kacchi Gosht)', quantity: 1, price: 440 },
      { name: 'Mirchi Ka Salan (Classic)', quantity: 1, price: 180 },
    ],
    itemTotal: 620,
    deliveryFee: 25,
    gst: 31,
    grandTotal: 676,
    status: 'Preparing' as const,
    deliveryAddress: 'Villa 18, Gulmohar Enclave, Road 45, Jubilee Hills',
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 font-sans">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#EADFCF]">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-[#5B1E4E] uppercase tracking-wider">
            <PackageCheck className="w-4 h-4 text-[#2E7D32]" />
            <span>Simulated Active Order &bull; Hyderabad</span>
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-[#22161F] mt-1">
            Order Tracking: {currentOrder.orderId}
          </h1>
          <p className="text-xs text-[#574652] mt-0.5">
            Placed from {currentOrder.restaurantName} &bull; Handi Dum In Progress
          </p>
        </div>

        {/* AI Concierge Help CTA */}
        <button
          type="button"
          onClick={() =>
            openChatWithPrompt(
              `Check up on order ${currentOrder.orderId} from ${currentOrder.restaurantName}. How is the handi simmering?`
            )
          }
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] text-xs font-semibold shadow-xs transition-all self-start sm:self-auto min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
        >
          <Sparkles className="w-4 h-4 text-[#D8AE4A]" aria-hidden="true" />
          <span>Need help? Ask Dawat AI</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Live Map & Status Timeline */}
        <div className="lg:col-span-7 space-y-6">
          {/* Simulated Map Visual */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-[#574652]">
              <span className="font-medium text-[#22161F]">Rider &amp; Kitchen Route</span>
              <span>Remaining Distance: <strong className="text-[#5B1E4E]">1.2 km</strong></span>
            </div>
            <MapPlaceholder
              restaurantName={currentOrder.restaurantName}
              distanceKm={1.2}
              locality="Road 10, Banjara Hills to Jubilee Hills"
              isTracking={true}
            />
          </div>

          {/* Status Timeline Component */}
          <StatusTimeline initialStage="kitchen" />
        </div>

        {/* Right Column: Order Recap & Receipt */}
        <div className="lg:col-span-5 space-y-6">
          {/* Order Details Card */}
          <div className="bg-white rounded-2xl border border-[#EADFCF] p-5 shadow-xs space-y-4 font-sans">
            <div className="flex items-center justify-between pb-3 border-b border-[#FAF6EF]">
              <div className="flex items-center gap-2">
                <Receipt className="w-4 h-4 text-[#5B1E4E]" />
                <h3 className="font-serif text-lg font-bold text-[#22161F]">
                  Order Receipt
                </h3>
              </div>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-[#5B1E4E]/10 text-[#5B1E4E] font-semibold">
                Paid (Simulated)
              </span>
            </div>

            {/* Restaurant Info */}
            <div className="flex items-center gap-3 p-3 rounded-xl bg-[#FAF6EF] border border-[#EADFCF]">
              <div className="w-10 h-10 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] flex items-center justify-center shrink-0">
                <Utensils className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <h4 className="font-serif text-base font-bold text-[#22161F] truncate">
                  {currentOrder.restaurantName}
                </h4>
                <span className="text-xs text-[#574652]">
                  Acacia charcoal woodsmoke dum
                </span>
              </div>
            </div>

            {/* Items */}
            <div className="space-y-2 text-xs">
              <span className="font-semibold text-[#574652] uppercase tracking-wider block">
                Items in this Dastarkhwan
              </span>
              <div className="divide-y divide-[#FAF6EF]">
                {currentOrder.items.map((item, i) => (
                  <div key={i} className="py-2 flex justify-between items-center text-[#22161F]">
                    <span>
                      <span className="font-bold text-[#5B1E4E]">{item.quantity}x</span> {item.name}
                    </span>
                    <span className="font-semibold">₹{item.price * item.quantity}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Bill Summary */}
            <div className="pt-3 border-t border-[#EADFCF] space-y-2 text-xs text-[#574652]">
              <div className="flex justify-between">
                <span>Food Item Subtotal</span>
                <span className="font-semibold text-[#22161F]">₹{currentOrder.itemTotal}</span>
              </div>
              <div className="flex justify-between">
                <span>Delivery Fee (Distance-based)</span>
                <span className="font-semibold text-[#22161F]">
                  {currentOrder.deliveryFee === 0 ? 'FREE' : `₹${currentOrder.deliveryFee}`}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Restaurant GST (5%)</span>
                <span className="font-semibold text-[#22161F]">₹{currentOrder.gst}</span>
              </div>
              <div className="pt-2 border-t border-[#EADFCF] flex justify-between items-center text-sm font-bold text-[#22161F]">
                <span className="font-serif text-base">Grand Total</span>
                <span className="text-[#5B1E4E] text-lg font-mono">₹{currentOrder.grandTotal}</span>
              </div>
            </div>

            {/* Delivery Destination */}
            <div className="pt-3 border-t border-[#FAF6EF] flex items-start gap-2.5 text-xs">
              <MapPin className="w-4 h-4 text-[#5B1E4E] shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-[#22161F] block">
                  Delivering to:
                </span>
                <span className="text-[#574652] block">
                  {currentOrder.deliveryAddress}
                </span>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex flex-col sm:flex-row gap-3">
            <Link
              href="/restaurants"
              className="flex-1 px-4 py-3 rounded-xl border border-[#EADFCF] bg-white text-[#22161F] hover:bg-[#FAF6EF] text-xs font-semibold text-center min-h-[44px] flex items-center justify-center transition-colors"
            >
              Order Another Feast
            </Link>
            <Link
              href="/profile"
              className="flex-1 px-4 py-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] text-xs font-semibold text-center min-h-[44px] flex items-center justify-center transition-colors"
            >
              View Order History
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
