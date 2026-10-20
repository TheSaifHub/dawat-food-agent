'use client';

import React, { useState } from 'react';
import {
  CheckCircle2,
  ChefHat,
  Bike,
  Home,
  Clock,
  Sparkles,
  MapPin,
  Phone,
  ChevronRight,
} from 'lucide-react';

export type OrderStage = 'placed' | 'kitchen' | 'rider_assigned' | 'in_transit' | 'delivered';

interface TimelineStep {
  id: OrderStage;
  title: string;
  subtitle: string;
  detail: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TIMELINE_STEPS: TimelineStep[] = [
  {
    id: 'placed',
    title: 'Order Placed & Confirmed',
    subtitle: 'Nawab’s Dastarkhwan accepted your feast',
    detail: 'Simulated payment verified. Ticket sent to head khansama.',
    icon: CheckCircle2,
  },
  {
    id: 'kitchen',
    title: 'Degh Dum Simmering in Kitchen',
    subtitle: 'Slow-charcoal sealed handi preparation',
    detail: 'Basmati layered with saffron and marinated cuts over charcoal embers.',
    icon: ChefHat,
  },
  {
    id: 'rider_assigned',
    title: 'Rider Mohammed Farhan Assigned',
    subtitle: 'Insulated thermal casserole bag verified',
    detail: 'Electric 2-wheeler. Contactless protocol enabled.',
    icon: Bike,
  },
  {
    id: 'in_transit',
    title: 'On the Way (1.2 km away)',
    subtitle: 'Navigating Road No. 10 to Jubilee Hills',
    detail: 'Approaching main avenue. Real-time GPS coordinates active.',
    icon: MapPin,
  },
  {
    id: 'delivered',
    title: 'Delivered at Your Doorstep',
    subtitle: 'Feast handed over with warm regards',
    detail: 'Bismillah! Enjoy your Nizami Dawat.',
    icon: Home,
  },
];

interface StatusTimelineProps {
  initialStage?: OrderStage;
}

export function StatusTimeline({ initialStage = 'kitchen' }: StatusTimelineProps) {
  const [currentStage, setCurrentStage] = useState<OrderStage>(initialStage);

  const stageOrder: OrderStage[] = ['placed', 'kitchen', 'rider_assigned', 'in_transit', 'delivered'];
  const currentIndex = stageOrder.indexOf(currentStage);

  return (
    <div className="bg-white rounded-2xl border border-[#EADFCF] p-6 shadow-xs font-sans space-y-6">
      {/* Timeline Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#EADFCF]">
        <div>
          <span className="text-xs font-semibold text-[#5B1E4E] uppercase tracking-wider block">
            Live Order Progress
          </span>
          <h3 className="font-serif text-xl font-bold text-[#22161F]">
            Status: {TIMELINE_STEPS[currentIndex].title}
          </h3>
        </div>

        {/* Interactive Demo Stage Stepper */}
        <div className="flex items-center gap-1.5 bg-[#FAF6EF] p-1.5 rounded-xl border border-[#EADFCF] self-start sm:self-auto">
          <span className="text-[11px] text-[#574652] px-2 font-medium">Demo Step:</span>
          {stageOrder.map((stg, i) => (
            <button
              key={stg}
              type="button"
              onClick={() => setCurrentStage(stg)}
              className={`w-7 h-7 rounded-lg text-xs font-bold transition-all flex items-center justify-center min-h-[28px] ${
                i === currentIndex
                  ? 'bg-[#5B1E4E] text-[#FAF6EF] shadow-xs'
                  : i < currentIndex
                  ? 'bg-[#2E7D32]/20 text-[#2E7D32]'
                  : 'bg-white text-[#877682] border border-[#EADFCF]'
              }`}
              title={`Simulate step ${i + 1}: ${stg}`}
              aria-label={`Advance tracking to step ${i + 1}`}
            >
              {i + 1}
            </button>
          ))}
        </div>
      </div>

      {/* Vertical Timeline Steps */}
      <div className="relative pl-6 space-y-8 before:absolute before:left-3 before:top-3 before:bottom-3 before:w-0.5 before:bg-[#EADFCF]">
        {TIMELINE_STEPS.map((step, idx) => {
          const isDone = idx < currentIndex;
          const isCurrent = idx === currentIndex;
          const isUpcoming = idx > currentIndex;
          const Icon = step.icon;

          return (
            <div key={step.id} className="relative flex items-start gap-4">
              {/* Node indicator */}
              <div
                className={`absolute -left-6 mt-0.5 w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                  isDone
                    ? 'bg-[#2E7D32] text-white shadow-xs'
                    : isCurrent
                    ? 'bg-[#5B1E4E] text-[#D8AE4A] ring-4 ring-[#F5EDF3] shadow-md animate-pulse'
                    : 'bg-[#FAF6EF] border-2 border-[#EADFCF] text-[#877682]'
                }`}
                aria-hidden="true"
              >
                <Icon className="w-3.5 h-3.5" />
              </div>

              {/* Step Content */}
              <div
                className={`flex-1 transition-all ${
                  isCurrent ? 'bg-[#FAF6EF]/60 p-4 rounded-xl border border-[#EADFCF]' : ''
                }`}
              >
                <div className="flex items-center justify-between">
                  <h4
                    className={`font-serif text-base font-bold ${
                      isCurrent
                        ? 'text-[#5B1E4E]'
                        : isDone
                        ? 'text-[#22161F]'
                        : 'text-[#877682]'
                    }`}
                  >
                    {step.title}
                  </h4>
                  {isCurrent && (
                    <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#5B1E4E] text-[#FAF6EF]">
                      Current
                    </span>
                  )}
                  {isDone && (
                    <span className="text-[11px] font-medium text-[#2E7D32]">
                      Completed
                    </span>
                  )}
                </div>

                <p
                  className={`text-xs mt-0.5 ${
                    isCurrent ? 'text-[#22161F] font-medium' : 'text-[#574652]'
                  }`}
                >
                  {step.subtitle}
                </p>

                {isCurrent && (
                  <p className="text-xs text-[#574652] mt-2 pt-2 border-t border-[#EADFCF]/60">
                    {step.detail}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Delivery Partner Card (when assigned or in transit) */}
      {(currentIndex >= 2) && (
        <div className="p-4 rounded-xl bg-[#FAF6EF] border border-[#EADFCF] flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-[#5B1E4E] text-[#FAF6EF] flex items-center justify-center font-bold text-sm shrink-0">
              MF
            </div>
            <div>
              <div className="font-semibold text-sm text-[#22161F]">
                Mohammed Farhan
              </div>
              <div className="text-xs text-[#574652] flex items-center gap-1.5">
                <Bike className="w-3.5 h-3.5 text-[#5B1E4E]" />
                <span>Delivery Partner &bull; Insulated Degh Carrier</span>
              </div>
            </div>
          </div>

          <button
            type="button"
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-[#EADFCF] text-xs font-semibold text-[#5B1E4E] hover:bg-[#F5EDF3] transition-colors min-h-[44px] focus-visible:ring-2 focus-visible:ring-[#5B1E4E]"
            aria-label="Call simulated delivery partner"
          >
            <Phone className="w-3.5 h-3.5 text-[#5B1E4E]" aria-hidden="true" />
            <span>Call Partner</span>
          </button>
        </div>
      )}
    </div>
  );
}
