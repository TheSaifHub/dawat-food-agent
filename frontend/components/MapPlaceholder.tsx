import React from 'react';
import { MapPin, Navigation, Compass } from 'lucide-react';

interface MapPlaceholderProps {
  restaurantName: string;
  distanceKm: number;
  locality: string;
  isTracking?: boolean;
}

export function MapPlaceholder({
  restaurantName,
  distanceKm,
  locality,
  isTracking = false,
}: MapPlaceholderProps) {
  return (
    <div className="relative w-full h-56 sm:h-64 rounded-2xl overflow-hidden border border-[#EADFCF] bg-[#F4ECE0] shadow-xs font-sans">
      {/* Stylized Hyderabad Vector Map Schematic */}
      <svg
        viewBox="0 0 500 240"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full object-cover select-none"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        {/* Background land texture */}
        <rect width="500" height="240" fill="#F4ECE0" />

        {/* Hussain Sagar / Water body stylized contour */}
        <path
          d="M 330 40 C 370 30, 420 50, 430 90 C 440 130, 390 145, 350 140 C 320 135, 305 100, 320 60 Z"
          fill="#D6E4E5"
          stroke="#B4CDE6"
          strokeWidth="1.5"
        />
        <text x="350" y="90" fill="#75939E" fontSize="9" fontFamily="sans-serif" textAnchor="middle">
          Hussain Sagar
        </text>

        {/* Major Road Arteries (PVNR Expressway, Outer Ring Road, Banjara Road 10/12) */}
        <path
          d="M 20 220 C 140 180, 240 120, 480 80"
          stroke="#E0D2BF"
          strokeWidth="12"
          strokeLinecap="round"
        />
        <path
          d="M 20 220 C 140 180, 240 120, 480 80"
          stroke="#FFFFFF"
          strokeWidth="7"
          strokeLinecap="round"
        />

        {/* Secondary cross-streets */}
        <path d="M 120 20 L 140 230" stroke="#FFFFFF" strokeWidth="4" />
        <path d="M 240 10 L 260 220" stroke="#FFFFFF" strokeWidth="4" />
        <path d="M 60 80 L 460 170" stroke="#FFFFFF" strokeWidth="5" />
        <path d="M 200 150 L 380 230" stroke="#FFFFFF" strokeWidth="3" />

        {/* Route Line if Tracking */}
        {isTracking ? (
          <>
            <path
              d="M 140 130 Q 200 120 260 140 T 360 110"
              stroke="#5B1E4E"
              strokeWidth="4"
              strokeDasharray="6 4"
              strokeLinecap="round"
            />
            {/* Delivery Rider Pin */}
            <circle cx="260" cy="140" r="14" fill="#5B1E4E" />
            <circle cx="260" cy="140" r="6" fill="#D8AE4A" />
          </>
        ) : (
          /* Distance Radius circle */
          <circle
            cx="220"
            cy="110"
            r="45"
            stroke="#5B1E4E"
            strokeWidth="1.5"
            strokeDasharray="4 3"
            fill="#5B1E4E"
            fillOpacity="0.05"
          />
        )}

        {/* Restaurant Pin */}
        <g transform="translate(205, 75)">
          <path
            d="M 15 0 C 6.7 0, 0 6.7, 0 15 C 0 25, 15 40, 15 40 C 15 40, 30 25, 30 15 C 30 6.7, 23.3 0, 15 0 Z"
            fill="#5B1E4E"
            stroke="#D8AE4A"
            strokeWidth="2"
          />
          <circle cx="15" cy="14" r="5" fill="#FAF6EF" />
        </g>
      </svg>

      {/* Floating Map Overlay Info Tag */}
      <div className="absolute bottom-3 left-3 right-3 sm:right-auto bg-white/95 backdrop-blur-md px-3.5 py-2 rounded-xl border border-[#EADFCF] shadow-sm flex items-center justify-between sm:justify-start gap-3 text-xs">
        <div className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-[#5B1E4E]" aria-hidden="true" />
          <div>
            <div className="font-semibold text-[#22161F]">{restaurantName}</div>
            <div className="text-[11px] text-[#574652]">{locality}, Hyderabad</div>
          </div>
        </div>

        <div className="px-2.5 py-1 rounded-md bg-[#FAF6EF] text-[#5B1E4E] font-bold text-xs border border-[#EADFCF]">
          {distanceKm} km away
        </div>
      </div>

      <div className="absolute top-3 right-3 bg-white/90 backdrop-blur-md px-2 py-1 rounded-lg border border-[#EADFCF] text-[10px] text-[#574652] flex items-center gap-1">
        <Compass className="w-3 h-3 text-[#5B1E4E]" />
        <span>Hyderabad Schematic Map</span>
      </div>
    </div>
  );
}
