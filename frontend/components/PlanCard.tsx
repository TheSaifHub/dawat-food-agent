'use client';

import React from 'react';
import { AIPlanOption } from '@/data/mockData';
import { Sparkles, Users, ArrowRight, ShieldCheck } from 'lucide-react';

interface PlanCardProps {
  plan: AIPlanOption;
  onSelect: (plan: AIPlanOption) => void;
}

export function PlanCard({ plan, onSelect }: PlanCardProps) {
  // Badge styling
  const badgeConfig = {
    'Best value': {
      bg: 'bg-[#2E7D32]/10',
      text: 'text-[#2E7D32]',
      border: 'border-[#2E7D32]/30',
    },
    'Best match': {
      bg: 'bg-[#5B1E4E]/10',
      text: 'text-[#5B1E4E]',
      border: 'border-[#5B1E4E]/30',
    },
    'Variety': {
      bg: 'bg-[#B7950B]/10',
      text: 'text-[#9A7D0A]',
      border: 'border-[#B7950B]/30',
    },
  }[plan.badge];

  return (
    <div className="bg-white rounded-2xl border border-[#EADFCF] hover:border-[#5B1E4E] p-4 shadow-xs transition-all space-y-3 font-sans">
      {/* Header: Badge & Restaurant */}
      <div className="flex items-center justify-between gap-2">
        <span
          className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${badgeConfig.bg} ${badgeConfig.text} ${badgeConfig.border}`}
        >
          {plan.badge}
        </span>
        <span className="text-xs font-medium text-[#574652] truncate">
          {plan.restaurantName}
        </span>
      </div>

      {/* Plan Title & Serves Count */}
      <div>
        <h4 className="font-serif text-lg font-bold text-[#22161F] leading-tight">
          {plan.title}
        </h4>
        <div className="flex items-center gap-2 text-xs text-[#574652] mt-1">
          <span className="flex items-center gap-1">
            <Users className="w-3.5 h-3.5 text-[#5B1E4E]" aria-hidden="true" />
            Serves {plan.servesCount}
          </span>
          <span>&bull;</span>
          <span>{plan.distanceKm} km away</span>
          <span>&bull;</span>
          <span>{plan.deliveryFee === 0 ? 'Free Delivery' : `₹${plan.deliveryFee} fee`}</span>
        </div>
      </div>

      <p className="text-xs text-[#574652] leading-relaxed">
        {plan.description}
      </p>

      {/* Itemized List */}
      <div className="bg-[#FAF6EF] p-2.5 rounded-xl border border-[#EADFCF] space-y-1.5 text-xs">
        {plan.items.map((item) => (
          <div key={item.id} className="flex justify-between items-center text-[#22161F]">
            <span className="truncate pr-2">
              <span className="font-semibold text-[#5B1E4E]">{item.quantity}x</span> {item.name}
            </span>
            <span className="font-medium shrink-0">₹{item.price * item.quantity}</span>
          </div>
        ))}
      </div>

      {/* Footer: Price & Select CTA */}
      <div className="pt-1 flex items-center justify-between gap-3">
        <div>
          <span className="text-[11px] text-[#574652] block">Complete Feast</span>
          <span className="font-serif text-lg font-bold text-[#5B1E4E]">₹{plan.totalPrice}</span>
        </div>

        <button
          type="button"
          onClick={() => onSelect(plan)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] shadow-xs transition-all flex items-center gap-1.5 min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
          aria-label={`Select ${plan.title} for ₹${plan.totalPrice}`}
        >
          <span>Select Plan</span>
          <ArrowRight className="w-3.5 h-3.5 text-[#FAF6EF]" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
