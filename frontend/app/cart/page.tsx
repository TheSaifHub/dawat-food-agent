'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useDawat } from '@/context/DawatContext';
import { FoodIllustration } from '@/components/FoodIllustration';
import { CartBill } from '@/components/CartBill';
import {
  ShoppingBag,
  ArrowLeft,
  Trash2,
  Plus,
  Minus,
  MapPin,
  CreditCard,
  QrCode,
  Banknote,
  CheckCircle2,
  ShieldCheck,
  FileText,
  AlertCircle,
} from 'lucide-react';

export default function CartAndCheckoutPage() {
  const router = useRouter();
  const {
    cart,
    cartRestaurantId,
    cartRestaurantName,
    cartSubtotal,
    cartDeliveryFee,
    cartGst,
    cartGrandTotal,
    updateQuantity,
    removeFromCart,
    clearCart,
    activePersona,
    placeOrderFromCart,
  } = useDawat();

  const [selectedAddressId, setSelectedAddressId] = useState(
    activePersona.savedAddresses[0]?.id || 'addr-1'
  );
  const [deliveryNote, setDeliveryNote] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<'upi' | 'card' | 'cod'>('upi');
  const [isPlacingOrder, setIsPlacingOrder] = useState(false);

  const handlePlaceOrder = () => {
    if (cart.length === 0) return;
    setIsPlacingOrder(true);
    setTimeout(() => {
      placeOrderFromCart();
      router.push('/order-tracking');
    }, 600);
  };

  if (cart.length === 0) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center space-y-6 font-sans">
        <div className="w-20 h-20 rounded-full bg-[#FAF6EF] border-2 border-[#EADFCF] flex items-center justify-center mx-auto text-[#5B1E4E]">
          <ShoppingBag className="w-10 h-10" />
        </div>
        <div className="space-y-2">
          <h1 className="font-serif text-3xl font-bold text-[#22161F]">
            Your Dastarkhwan is empty
          </h1>
          <p className="text-sm text-[#574652] max-w-md mx-auto">
            You haven&apos;t added any delicacies to your cart yet. Explore our curated kitchens in Hyderabad to craft your feast.
          </p>
        </div>
        <div className="flex justify-center gap-3 pt-2">
          <Link
            href="/restaurants"
            className="px-6 py-3 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] font-semibold text-xs tracking-wider uppercase transition-all min-h-[44px] flex items-center"
          >
            Explore Restaurants
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 font-sans">
      {/* Top Breadcrumb & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#EADFCF]">
        <div>
          <Link
            href={cartRestaurantId ? `/restaurant/${cartRestaurantId}` : '/restaurants'}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#574652] hover:text-[#5B1E4E] transition-colors mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Continue adding dishes</span>
          </Link>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-[#22161F]">
            Cart &amp; Checkout
          </h1>
        </div>

        {/* Clear Cart button */}
        <button
          type="button"
          onClick={clearCart}
          className="flex items-center gap-1.5 text-xs text-[#877682] hover:text-[#C0392B] self-start sm:self-auto min-h-[44px] px-2"
        >
          <Trash2 className="w-4 h-4" />
          <span>Clear Cart</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column (Items + Address + Payment) */}
        <div className="lg:col-span-7 space-y-6">
          {/* 1. Items from Single Restaurant Card */}
          <section className="bg-white rounded-2xl border border-[#EADFCF] p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#FAF6EF]">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[#5B1E4E] block">
                  Kitchen Under Order
                </span>
                <h2 className="font-serif text-xl font-bold text-[#22161F]">
                  {cartRestaurantName}
                </h2>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-[#FAF6EF] text-[#574652] border border-[#EADFCF] font-medium">
                1 Bill Guarantee
              </span>
            </div>

            <div className="divide-y divide-[#FAF6EF]">
              {cart.map((ci) => (
                <div
                  key={ci.item.id}
                  className="py-3.5 flex items-center justify-between gap-3"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`w-3.5 h-3.5 rounded-xs border flex items-center justify-center shrink-0 ${
                        ci.item.isVeg ? 'border-[#2E7D32]' : 'border-[#7B241C]'
                      }`}
                    >
                      <div
                        className={`w-1.5 h-1.5 rounded-full ${
                          ci.item.isVeg ? 'bg-[#2E7D32]' : 'bg-[#7B241C]'
                        }`}
                      />
                    </div>
                    <div className="min-w-0">
                      <h4 className="font-medium text-sm text-[#22161F] truncate">
                        {ci.item.name}
                      </h4>
                      <span className="text-xs text-[#574652]">
                        ₹{ci.item.price} each &bull; {ci.item.spiceLevel}
                      </span>
                    </div>
                  </div>

                  {/* Quantity Control Buttons */}
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="w-24 h-9 px-2 rounded-lg bg-[#FAF6EF] border border-[#EADFCF] text-[#22161F] flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => updateQuantity(ci.item.id, -1)}
                        className="w-6 h-6 flex items-center justify-center text-[#574652] hover:text-[#22161F] min-h-[36px]"
                        aria-label={`Decrease ${ci.item.name}`}
                      >
                        <Minus className="w-3.5 h-3.5" />
                      </button>
                      <span className="font-bold text-xs">{ci.quantity}</span>
                      <button
                        type="button"
                        onClick={() => updateQuantity(ci.item.id, 1)}
                        className="w-6 h-6 flex items-center justify-center text-[#574652] hover:text-[#22161F] min-h-[36px]"
                        aria-label={`Increase ${ci.item.name}`}
                      >
                        <Plus className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <span className="font-semibold text-sm text-[#22161F] w-14 text-right">
                      ₹{ci.item.price * ci.quantity}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* 2. Delivery Address Selection */}
          <section className="bg-white rounded-2xl border border-[#EADFCF] p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-serif text-lg font-bold text-[#22161F] flex items-center gap-2">
                <MapPin className="w-4 h-4 text-[#5B1E4E]" />
                <span>Delivery Address in Hyderabad</span>
              </h2>
              <span className="text-xs text-[#574652]">
                Profile: {activePersona.name}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {activePersona.savedAddresses.map((addr) => (
                <button
                  key={addr.id}
                  type="button"
                  onClick={() => setSelectedAddressId(addr.id)}
                  className={`p-3.5 rounded-xl border text-left transition-all min-h-[44px] ${
                    selectedAddressId === addr.id
                      ? 'border-[#5B1E4E] bg-[#F5EDF3]'
                      : 'border-[#EADFCF] bg-[#FAF6EF]/40 hover:border-[#5B1E4E]'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-[#5B1E4E]">
                      {addr.label}
                    </span>
                    {selectedAddressId === addr.id && (
                      <CheckCircle2 className="w-4 h-4 text-[#5B1E4E]" />
                    )}
                  </div>
                  <p className="text-xs text-[#22161F] mt-1 font-medium">
                    {addr.line1}
                  </p>
                  <p className="text-[11px] text-[#574652]">
                    {addr.area}, {addr.city} - {addr.pincode}
                  </p>
                </button>
              ))}
            </div>

            {/* Delivery Instructions */}
            <div className="pt-2">
              <label
                htmlFor="delivery-instructions"
                className="block text-xs font-semibold text-[#574652] mb-1.5"
              >
                Delivery instructions / Flat landmark (Optional)
              </label>
              <input
                id="delivery-instructions"
                type="text"
                value={deliveryNote}
                onChange={(e) => setDeliveryNote(e.target.value)}
                placeholder="e.g. Ring bell, leave outside wooden door, call on arrival"
                className="w-full px-3.5 py-2.5 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/40 text-xs text-[#22161F] focus:outline-none focus:ring-2 focus:ring-[#5B1E4E] min-h-[44px]"
              />
            </div>
          </section>

          {/* 3. Simulated Payment Method Selection */}
          <section className="bg-white rounded-2xl border border-[#EADFCF] p-5 shadow-xs space-y-4">
            <h2 className="font-serif text-lg font-bold text-[#22161F] flex items-center gap-2">
              <CreditCard className="w-4 h-4 text-[#5B1E4E]" />
              <span>Select Payment Method (Simulated)</span>
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <button
                type="button"
                onClick={() => setPaymentMethod('upi')}
                className={`p-3 rounded-xl border flex flex-col items-center justify-center text-center gap-1.5 min-h-[44px] transition-all ${
                  paymentMethod === 'upi'
                    ? 'border-[#5B1E4E] bg-[#F5EDF3] text-[#5B1E4E]'
                    : 'border-[#EADFCF] bg-[#FAF6EF]/40 text-[#574652] hover:border-[#5B1E4E]'
                }`}
              >
                <QrCode className="w-5 h-5" />
                <span className="text-xs font-semibold">Instant UPI / QR</span>
                <span className="text-[10px] text-[#574652]">Google Pay, PhonePe</span>
              </button>

              <button
                type="button"
                onClick={() => setPaymentMethod('card')}
                className={`p-3 rounded-xl border flex flex-col items-center justify-center text-center gap-1.5 min-h-[44px] transition-all ${
                  paymentMethod === 'card'
                    ? 'border-[#5B1E4E] bg-[#F5EDF3] text-[#5B1E4E]'
                    : 'border-[#EADFCF] bg-[#FAF6EF]/40 text-[#574652] hover:border-[#5B1E4E]'
                }`}
              >
                <CreditCard className="w-5 h-5" />
                <span className="text-xs font-semibold">Credit / Debit Card</span>
                <span className="text-[10px] text-[#574652]">Visa, Mastercard, RuPay</span>
              </button>

              <button
                type="button"
                onClick={() => setPaymentMethod('cod')}
                className={`p-3 rounded-xl border flex flex-col items-center justify-center text-center gap-1.5 min-h-[44px] transition-all ${
                  paymentMethod === 'cod'
                    ? 'border-[#5B1E4E] bg-[#F5EDF3] text-[#5B1E4E]'
                    : 'border-[#EADFCF] bg-[#FAF6EF]/40 text-[#574652] hover:border-[#5B1E4E]'
                }`}
              >
                <Banknote className="w-5 h-5" />
                <span className="text-xs font-semibold">Cash on Delivery</span>
                <span className="text-[10px] text-[#574652]">Pay upon arrival</span>
              </button>
            </div>
          </section>
        </div>

        {/* Right Column: Single Restaurant Bill & Place Order CTA */}
        <div className="lg:col-span-5 sticky top-28 space-y-4">
          <CartBill
            onPlaceOrder={handlePlaceOrder}
            showCheckoutButton={true}
          />
        </div>
      </div>
    </div>
  );
}
