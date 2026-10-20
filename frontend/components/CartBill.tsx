'use client';

import React from 'react';
import { useDawat } from '@/context/DawatContext';
import { Receipt, ShieldCheck, MapPin, ArrowRight } from 'lucide-react';

interface CartBillProps {
  onPlaceOrder?: () => void;
  showCheckoutButton?: boolean;
}

export function CartBill({ onPlaceOrder, showCheckoutButton = true }: CartBillProps) {
  const {
    cart,
    cartRestaurantName,
    cartSubtotal,
    cartDeliveryFee,
    cartGst,
    cartGrandTotal,
    activePersona,
  } = useDawat();

  if (cart.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-[#EADFCF] p-8 text-center font-sans space-y-3">
        <Receipt className="w-10 h-10 text-[#877682] mx-auto opacity-50" aria-hidden="true" />
        <h3 className="font-serif text-xl font-bold text-[#22161F]">Your Dawat feast is empty</h3>
        <p className="text-xs text-[#574652] max-w-xs mx-auto">
          Explore authentic Hyderabad restaurants or ask Dawat AI to curate a personalized Nizami meal.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-[#EADFCF] shadow-xs overflow-hidden font-sans">
      {/* Bill Header */}
      <div className="bg-[#FAF6EF] p-4 border-b border-[#EADFCF] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Receipt className="w-4 h-4 text-[#5B1E4E]" aria-hidden="true" />
          <h3 className="font-serif text-base font-bold text-[#22161F]">
            Order Bill Summary
          </h3>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-[#5B1E4E]/10 text-[#5B1E4E] border border-[#5B1E4E]/20">
          Single Kitchen: {cartRestaurantName}
        </span>
      </div>

      {/* Bill Details */}
      <div className="p-5 space-y-4">
        {/* Delivery Destination Snippet */}
        <div className="flex items-start gap-2.5 p-3 rounded-xl bg-[#FAF6EF]/60 border border-[#EADFCF] text-xs">
          <MapPin className="w-4 h-4 text-[#5B1E4E] shrink-0 mt-0.5" aria-hidden="true" />
          <div className="min-w-0">
            <span className="font-semibold text-[#22161F] block">
              Delivering to {activePersona.defaultAddress.label} ({activePersona.name})
            </span>
            <span className="text-[#574652] truncate block">
              {activePersona.defaultAddress.line1}, {activePersona.defaultAddress.area}
            </span>
          </div>
        </div>

        {/* Pricing Breakdown strictly fulfilling requirements */}
        <div className="space-y-2.5 text-xs text-[#574652] pt-1">
          <div className="flex justify-between items-center">
            <span>Item Subtotal ({cart.reduce((s, i) => s + i.quantity, 0)} items)</span>
            <span className="font-semibold text-[#22161F]">₹{cartSubtotal}</span>
          </div>

          <div className="flex justify-between items-center">
            <div className="flex items-center gap-1">
              <span>Delivery Fee</span>
              {cartDeliveryFee === 0 && (
                <span className="text-[10px] text-[#2E7D32] bg-[#2E7D32]/10 px-1.5 py-0.2 rounded font-medium">
                  Free Partner
                </span>
              )}
            </div>
            <span className={`font-semibold ${cartDeliveryFee === 0 ? 'text-[#2E7D32]' : 'text-[#22161F]'}`}>
              {cartDeliveryFee === 0 ? 'FREE' : `₹${cartDeliveryFee}`}
            </span>
          </div>

          <div className="flex justify-between items-center">
            <span>Taxes & Restaurant GST (5%)</span>
            <span className="font-semibold text-[#22161F]">₹{cartGst}</span>
          </div>

          <div className="pt-3 border-t border-[#EADFCF] flex justify-between items-center text-sm font-bold text-[#22161F]">
            <span className="font-serif text-base">To Pay</span>
            <span className="text-[#5B1E4E] text-lg font-mono">₹{cartGrandTotal}</span>
          </div>
        </div>

        {/* Guarantee microcopy */}
        <div className="flex items-center gap-1.5 text-[11px] text-[#574652] pt-1">
          <ShieldCheck className="w-3.5 h-3.5 text-[#2E7D32] shrink-0" aria-hidden="true" />
          <span>One bill per restaurant guarantee &bull; 100% contactless simulated delivery</span>
        </div>

        {/* Action Button */}
        {showCheckoutButton && (
          <button
            type="button"
            onClick={onPlaceOrder}
            className="w-full mt-2 h-12 px-6 rounded-xl font-semibold text-sm bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] shadow-sm transition-all flex items-center justify-center gap-2 focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
          >
            <span>Place Order &bull; ₹{cartGrandTotal}</span>
            <ArrowRight className="w-4 h-4 text-[#FAF6EF]" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
