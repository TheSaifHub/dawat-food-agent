'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Cpu, CheckCircle2 } from 'lucide-react';

interface ThinkingStepsProps {
  steps: string[];
}

export function ThinkingSteps({ steps }: ThinkingStepsProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="my-2 rounded-xl border border-[#EADFCF] bg-[#FAF6EF]/70 overflow-hidden font-sans text-xs">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full px-3 py-2 flex items-center justify-between text-[#574652] hover:text-[#22161F] hover:bg-[#FAF6EF] transition-colors focus-visible:ring-1 focus-visible:ring-[#5B1E4E]"
        aria-expanded={isOpen}
        aria-label="Toggle AI culinary reasoning steps"
      >
        <div className="flex items-center gap-1.5 font-medium">
          <Cpu className="w-3.5 h-3.5 text-[#5B1E4E]" aria-hidden="true" />
          <span>Dawat AI Reasoning ({steps.length} steps)</span>
        </div>
        {isOpen ? (
          <ChevronUp className="w-3.5 h-3.5 text-[#574652]" aria-hidden="true" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-[#574652]" aria-hidden="true" />
        )}
      </button>

      {isOpen && (
        <div className="p-3 pt-1 border-t border-[#EADFCF]/60 space-y-2 bg-white/40">
          {steps.map((step, idx) => (
            <div key={idx} className="flex items-start gap-2 text-[#574652]">
              <CheckCircle2 className="w-3.5 h-3.5 text-[#2E7D32] shrink-0 mt-0.5" aria-hidden="true" />
              <span className="leading-tight">{step}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
