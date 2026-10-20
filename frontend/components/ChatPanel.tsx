'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useDawat } from '@/context/DawatContext';
import { ThinkingSteps } from './ThinkingSteps';
import { PlanCard } from './PlanCard';
import { ConfirmCard } from './ConfirmCard';
import { DawatLogo } from './DawatLogo';
import {
  Sparkles,
  X,
  Send,
  Minimize2,
  Maximize2,
  Bot,
  User,
  Flame,
  Leaf,
  Users,
} from 'lucide-react';

export function ChatPanel() {
  const {
    isChatOpen,
    setIsChatOpen,
    chatMessages,
    sendChatMessage,
    handleSelectPlan,
    handleConfirmOrder,
    handleRejectOrder,
    activePersona,
    selectedArea,
  } = useDawat();

  const [inputMessage, setInputMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto scroll to latest message
  useEffect(() => {
    if (isChatOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      inputRef.current?.focus();
    }
  }, [chatMessages, isChatOpen]);

  // Listen for custom global event to open AI
  useEffect(() => {
    const handleOpen = () => setIsChatOpen(true);
    window.addEventListener('open-dawat-ai', handleOpen);
    return () => window.removeEventListener('open-dawat-ai', handleOpen);
  }, [setIsChatOpen]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim()) return;
    sendChatMessage(inputMessage.trim());
    setInputMessage('');
  };

  const samplePrompts = [
    { label: 'Dinner for 4 under ₹1,200', text: 'Plan a 4-person family dinner under ₹1,200 with biryani and starters' },
    { label: 'Spicy Mutton Dum Biryani', text: 'Recommend the spiciest authentic Kacchi Gosht Biryani near me' },
    { label: 'Pure Veg Nizami Spread', text: 'Curate a 100% vegetarian Nizami feast with Bagara Baingan' },
    { label: 'Irani Chai & Osmania Snacks', text: 'Order afternoon samovar Irani chai with Osmania biscuits and lukhmi' },
  ];

  return (
    <>
      {/* Floating Launcher Button at Bottom Right */}
      {!isChatOpen && (
        <div className="fixed bottom-5 right-5 z-40">
          <button
            type="button"
            onClick={() => setIsChatOpen(true)}
            className="group flex items-center gap-2.5 px-4 py-3 rounded-full bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] shadow-xl hover:shadow-2xl border-2 border-[#D8AE4A] transition-all transform hover:-translate-y-0.5 min-h-[50px] focus-visible:ring-4 focus-visible:ring-[#D8AE4A]"
            aria-label="Open Dawat AI Dining Concierge"
          >
            <div className="relative">
              <Sparkles className="w-5 h-5 text-[#D8AE4A] animate-pulse" aria-hidden="true" />
              <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-[#D8AE4A]" />
            </div>
            <div className="text-left font-sans leading-tight">
              <span className="text-xs font-semibold block tracking-wide">
                Dawat AI
              </span>
              <span className="text-[10px] text-[#FAF6EF]/80 font-normal">
                Ask Concierge
              </span>
            </div>
          </button>
        </div>
      )}

      {/* Slide-in Panel / Fullscreen Mobile Dialog */}
      {isChatOpen && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs transition-opacity duration-300"
          role="dialog"
          aria-modal="true"
          aria-labelledby="dawat-ai-title"
        >
          {/* Backdrop click to close on desktop */}
          <div
            className="hidden md:block flex-1"
            onClick={() => setIsChatOpen(false)}
            aria-hidden="true"
          />

          {/* Panel Container: Fullscreen on mobile (360px+), 440px wide sidebar on desktop */}
          <aside className="w-full h-full md:w-[440px] md:max-w-md bg-[#FAF6EF] shadow-2xl flex flex-col font-sans border-l border-[#EADFCF] animate-in slide-in-from-right duration-300 overflow-hidden">
            {/* Header: Brand, Concierge Title & Close buttons */}
            <div className="bg-[#5B1E4E] text-[#FAF6EF] p-4 border-b border-[#D8AE4A]/30 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <DawatLogo variant="emblem-only" size="sm" />
                <div>
                  <h3
                    id="dawat-ai-title"
                    className="font-serif text-lg font-bold text-white leading-tight flex items-center gap-1.5"
                  >
                    <span>Dawat AI</span>
                    <span className="text-[10px] font-sans font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#D8AE4A] text-[#22161F]">
                      Concierge
                    </span>
                  </h3>
                  <p className="text-[11px] text-[#FAF6EF]/80">
                    Active for {activePersona.name} &bull; {selectedArea}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setIsChatOpen(false)}
                  className="w-10 h-10 rounded-full text-[#FAF6EF] hover:bg-[#49173E] flex items-center justify-center transition-colors focus-visible:ring-2 focus-visible:ring-[#D8AE4A]"
                  aria-label="Close Dawat AI Panel"
                >
                  <X className="w-5 h-5 text-white" aria-hidden="true" />
                </button>
              </div>
            </div>

            {/* Persona and Area Context Bar */}
            <div className="bg-[#F5EDF3] px-4 py-2 border-b border-[#EADFCF] flex items-center justify-between text-xs text-[#574652]">
              <span className="flex items-center gap-1">
                {activePersona.dietaryPreference === 'Vegetarian' ? (
                  <Leaf className="w-3.5 h-3.5 text-[#2E7D32]" />
                ) : (
                  <Flame className="w-3.5 h-3.5 text-[#7B241C]" />
                )}
                <span>Profile: {activePersona.roleBadge}</span>
              </span>
              <span className="font-medium text-[#5B1E4E]">
                {selectedArea}
              </span>
            </div>

            {/* Chat Message Scrollable History */}
            <div
              className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth"
              tabIndex={0}
              aria-label="Conversation with Dawat AI"
            >
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${
                    msg.sender === 'user' ? 'items-end' : 'items-start'
                  } space-y-2`}
                >
                  <div className="flex items-center gap-1.5 text-[10px] text-[#574652] px-1">
                    {msg.sender === 'user' ? (
                      <>
                        <span>{msg.timestamp}</span>
                        <span className="font-semibold text-[#22161F]">You</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3 h-3 text-[#5B1E4E]" aria-hidden="true" />
                        <span className="font-semibold text-[#5B1E4E]">Dawat AI</span>
                        <span>{msg.timestamp}</span>
                      </>
                    )}
                  </div>

                  {/* Message Bubble */}
                  <div
                    className={`max-w-[90%] rounded-2xl p-3.5 text-xs leading-relaxed ${
                      msg.sender === 'user'
                        ? 'bg-[#5B1E4E] text-[#FAF6EF] rounded-br-xs'
                        : 'bg-white text-[#22161F] border border-[#EADFCF] shadow-xs rounded-bl-xs'
                    }`}
                  >
                    <p>{msg.text}</p>
                  </div>

                  {/* Collapsible Thinking Steps Panel */}
                  {msg.thinkingSteps && msg.thinkingSteps.length > 0 && (
                    <div className="w-full max-w-[92%]">
                      <ThinkingSteps steps={msg.thinkingSteps} />
                    </div>
                  )}

                  {/* AI Plan Cards (Best value / Best match / Variety) */}
                  {msg.plans && msg.plans.length > 0 && (
                    <div className="w-full space-y-3 pt-1">
                      <div className="text-[11px] font-semibold text-[#574652] uppercase tracking-wider">
                        Curated Feasts ({msg.plans.length} options)
                      </div>
                      {msg.plans.map((plan) => (
                        <PlanCard
                          key={plan.id}
                          plan={plan}
                          onSelect={handleSelectPlan}
                        />
                      ))}
                    </div>
                  )}

                  {/* Order Confirmation Card with Yes / No Buttons */}
                  {msg.confirmation && (
                    <div className="w-full max-w-[95%] pt-1">
                      <ConfirmCard
                        confirmationId={msg.confirmation.id}
                        title={msg.confirmation.title}
                        restaurantName={msg.confirmation.restaurantName}
                        itemsSummary={msg.confirmation.itemsSummary}
                        totalAmount={msg.confirmation.totalAmount}
                        onConfirm={handleConfirmOrder}
                        onReject={handleRejectOrder}
                      />
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Quick Suggestion Chips */}
            <div className="px-3 py-2 bg-[#FAF6EF] border-t border-[#EADFCF] overflow-x-auto no-scrollbar flex items-center gap-1.5 shrink-0">
              {samplePrompts.map((p, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => sendChatMessage(p.text)}
                  className="shrink-0 px-2.5 py-1.5 rounded-full bg-white border border-[#EADFCF] text-[11px] font-medium text-[#22161F] hover:border-[#5B1E4E] hover:text-[#5B1E4E] transition-colors min-h-[36px] focus-visible:ring-1 focus-visible:ring-[#5B1E4E]"
                >
                  {p.label}
                </button>
              ))}
            </div>

            {/* Input Box Footer */}
            <form
              onSubmit={handleSend}
              className="p-3 bg-white border-t border-[#EADFCF] flex items-center gap-2 shrink-0"
            >
              <input
                ref={inputRef}
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                placeholder="Ask Dawat AI: spice, budget, dishes..."
                className="flex-1 px-4 py-2.5 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/50 text-xs sm:text-sm text-[#22161F] placeholder-[#877682] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#5B1E4E] transition-all min-h-[44px]"
                aria-label="Message Dawat AI Concierge"
              />
              <button
                type="submit"
                disabled={!inputMessage.trim()}
                className="w-11 h-11 rounded-xl bg-[#5B1E4E] text-[#FAF6EF] hover:bg-[#49173E] disabled:opacity-40 disabled:hover:bg-[#5B1E4E] flex items-center justify-center transition-all shrink-0 focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
                aria-label="Send message"
              >
                <Send className="w-4 h-4 text-white" aria-hidden="true" />
              </button>
            </form>
          </aside>
        </div>
      )}
    </>
  );
}
