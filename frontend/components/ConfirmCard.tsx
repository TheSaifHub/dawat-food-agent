'use client';

import React from 'react';
import { Check, X, ShoppingBag } from 'lucide-react';

interface ConfirmCardProps {
  confirmationId: string;
  title: string;
  restaurantName: string;
  itemsSummary: string;
  totalAmount: number;
  onConfirm: (confId: string) => void;
  onReject: (confId: string) => void;
}

export function ConfirmCard({
  confirmationId,
  title,
  restaurantName,
  itemsSummary,
  totalAmount,
  onConfirm,
  onReject,
}: ConfirmCardProps) {
  return (
    <div className="bg-[#FAF6EF] border-2 border-[#5B1E4E] rounded-2xl p-4 shadow-sm space-y-3 font-sans">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-full bg-[#5B1E4E] text-[#FAF6EF] flex items-center justify-center shrink-0">
          <ShoppingBag className="w-3.5 h-3.5" aria-hidden="true" />
        </div>
        <div>
          <h4 className="font-serif text-base font-bold text-[#22161F] leading-tight">
            Order Confirmation
          </h4>
          <span className="text-[11px] text-[#574652]">{restaurantName}</span>
        </div>
      </div>

      {/* Summary */}
      <div className="bg-white p-3 rounded-xl border border-[#EADFCF] text-xs space-y-1.5">
        <div className="font-semibold text-[#5B1E4E]">{title}</div>
        <p className="text-[#574652] leading-snug">{itemsSummary}</p>
        <div className="pt-1 border-t border-[#FAF6EF] flex justify-between items-center font-bold text-[#22161F]">
          <span>Total (incl. estimated taxes)</span>
          <span className="font-mono text-[#5B1E4E] text-sm">₹{totalAmount}</span>
        </div>
      </div>

      <p className="text-xs text-[#22161F] font-medium">
        Would you like me to populate your single-restaurant cart with these items?
      </p>

      {/* Interactive Yes / No Buttons fulfilling required spec */}
      <div className="grid grid-cols-2 gap-2 pt-1">
        <button
          type="button"
          onClick={() => onReject(confirmationId)}
          className="h-11 px-3 rounded-xl border border-[#EADFCF] bg-white text-[#574652] hover:text-[#22161F] hover:bg-[#FAF6EF] text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
        >
          <X className="w-4 h-4 text-[#877682]" aria-hidden="true" />
          <span>No, Tweak</span>
        </button>

        <button
          type="button"
          onClick={() => onConfirm(confirmationId)}
          className="h-11 px-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] text-xs font-semibold flex items-center justify-center gap-1.5 transition-all shadow-xs focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
        >
          <Check className="w-4 h-4 text-[#D8AE4A]" aria-hidden="true" />
          <span>Yes, Add to Cart</span>
        </button>
      </div>
    </div>
  );
}
