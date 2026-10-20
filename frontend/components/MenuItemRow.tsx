'use client';

import React from 'react';
import { MenuItem, Restaurant } from '@/data/mockData';
import { FoodIllustration } from './FoodIllustration';
import { useDawat } from '@/context/DawatContext';
import { Plus, Minus, Flame } from 'lucide-react';

interface MenuItemRowProps {
  restaurant: Pick<Restaurant, 'id' | 'name' | 'deliveryFee'>;
  item: MenuItem;
}

export function MenuItemRow({ restaurant, item }: MenuItemRowProps) {
  const { cart, addToCart, updateQuantity } = useDawat();

  const cartItem = cart.find((ci) => ci.item.id === item.id);
  const currentQty = cartItem ? cartItem.quantity : 0;

  // Spice level styling tokens
  const spiceBadgeConfig = {
    'Not spicy': {
      bg: 'bg-[#2E7D32]/10',
      text: 'text-[#2E7D32]',
      border: 'border-[#2E7D32]/30',
      flames: 0,
    },
    'Mild': {
      bg: 'bg-[#B7950B]/10',
      text: 'text-[#9A7D0A]',
      border: 'border-[#B7950B]/30',
      flames: 1,
    },
    'Medium': {
      bg: 'bg-[#D35400]/10',
      text: 'text-[#D35400]',
      border: 'border-[#D35400]/30',
      flames: 2,
    },
    'Hot': {
      bg: 'bg-[#C0392B]/10',
      text: 'text-[#C0392B]',
      border: 'border-[#C0392B]/30',
      flames: 3,
    },
  }[item.spiceLevel];

  return (
    <div className="py-5 border-b border-[#EADFCF] flex flex-col sm:flex-row sm:items-center justify-between gap-4 font-sans bg-white/50 px-4 rounded-xl hover:bg-white transition-colors">
      {/* Left Details: Veg/Non-veg icon, Title, Spice Label, Price, Description */}
      <div className="space-y-2 flex-1 min-w-0 pr-2">
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Standard Indian Food Safety Dietary Mark (Veg / Non-veg) */}
          <div
            className={`w-4 h-4 rounded-xs border-2 flex items-center justify-center shrink-0 ${
              item.isVeg ? 'border-[#2E7D32]' : 'border-[#7B241C]'
            }`}
            title={item.isVeg ? 'Vegetarian' : 'Non-Vegetarian'}
            role="img"
            aria-label={item.isVeg ? 'Vegetarian mark' : 'Non-vegetarian mark'}
          >
            <div
              className={`w-2 h-2 rounded-full ${
                item.isVeg ? 'bg-[#2E7D32]' : 'bg-[#7B241C]'
              }`}
            />
          </div>

          <h4 className="font-serif text-lg font-bold text-[#22161F] leading-snug">
            {item.name}
          </h4>

          {/* Mandatory Spice Label */}
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${spiceBadgeConfig.bg} ${spiceBadgeConfig.text} ${spiceBadgeConfig.border}`}
          >
            {item.spiceLevel !== 'Not spicy' && (
              <Flame className="w-3 h-3 fill-current shrink-0" aria-hidden="true" />
            )}
            <span>{item.spiceLevel}</span>
          </span>
        </div>

        <div className="text-base font-semibold text-[#5B1E4E]">
          ₹{item.price}
        </div>

        <p className="text-xs text-[#574652] leading-relaxed max-w-xl">
          {item.description}
        </p>
      </div>

      {/* Right Controls: Dish Illustration & Add / - / + Controls */}
      <div className="flex items-center justify-between sm:flex-col sm:items-end gap-3 shrink-0">
        <FoodIllustration type={item.illustrationType} size={64} className="hidden sm:block" />

        {currentQty === 0 ? (
          <button
            type="button"
            onClick={() => addToCart(restaurant, item)}
            className="w-28 h-11 px-4 rounded-xl font-semibold text-xs tracking-wider uppercase bg-white border-2 border-[#5B1E4E] text-[#5B1E4E] hover:bg-[#5B1E4E] hover:text-[#FAF6EF] shadow-xs hover:shadow transition-all flex items-center justify-center gap-1.5 focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
            aria-label={`Add ${item.name} for ₹${item.price} to cart`}
          >
            <Plus className="w-4 h-4" aria-hidden="true" />
            <span>Add</span>
          </button>
        ) : (
          <div
            className="w-28 h-11 px-2 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] flex items-center justify-between shadow-xs"
            role="group"
            aria-label={`Quantity selector for ${item.name}`}
          >
            <button
              type="button"
              onClick={() => updateQuantity(item.id, -1)}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-[#FAF6EF] hover:bg-[#49173E] transition-colors focus-visible:ring-1 focus-visible:ring-[#D8AE4A]"
              aria-label={`Decrease quantity of ${item.name}`}
            >
              <Minus className="w-4 h-4" aria-hidden="true" />
            </button>
            <span
              className="font-bold text-sm text-white px-2 select-none"
              aria-live="polite"
            >
              {currentQty}
            </span>
            <button
              type="button"
              onClick={() => updateQuantity(item.id, 1)}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-[#FAF6EF] hover:bg-[#49173E] transition-colors focus-visible:ring-1 focus-visible:ring-[#D8AE4A]"
              aria-label={`Increase quantity of ${item.name}`}
            >
              <Plus className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
