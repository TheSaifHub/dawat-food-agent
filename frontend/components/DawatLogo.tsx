import React from 'react';

interface DawatLogoProps {
  variant?: 'full' | 'emblem-only' | 'horizontal';
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function DawatLogo({ variant = 'full', className = '', size = 'md' }: DawatLogoProps) {
  const sizeMap = {
    sm: { emblem: 36, textTitle: 'text-xl', textSub: 'text-[10px]' },
    md: { emblem: 48, textTitle: 'text-2xl', textSub: 'text-xs' },
    lg: { emblem: 64, textTitle: 'text-3xl', textSub: 'text-sm' },
  };

  const current = sizeMap[size];

  // Inline SVG Logo strictly implementing:
  // "a gold Mughal arch with a covered serving dish inside, on plum"
  const EmblemSvg = (
    <div
      className="relative flex items-center justify-center shrink-0 rounded-2xl bg-[#5B1E4E] shadow-sm border border-[#D8AE4A]/30 overflow-hidden"
      style={{ width: current.emblem, height: current.emblem }}
      role="img"
      aria-label="Dawat Brand Logo: Gold Mughal arch with a covered serving dish on plum"
    >
      <svg
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full p-1"
      >
        {/* Background Plum Base */}
        <rect width="100" height="100" rx="14" fill="#5B1E4E" />

        {/* Decorative inner gold border accent */}
        <rect
          x="4"
          y="4"
          width="92"
          height="92"
          rx="11"
          stroke="#D8AE4A"
          strokeWidth="1"
          strokeOpacity="0.4"
          strokeDasharray="3 3"
        />

        {/* Mughal Ogee Arch Outline (Gold) */}
        {/* Arch profile: base pillars rising to cusped shoulders meeting at a pointed apex */}
        <path
          d="M 22 84
             L 22 46
             C 22 38, 27 31, 35 27
             C 42 23, 47 21, 50 14
             C 53 21, 58 23, 65 27
             C 73 31, 78 38, 78 46
             L 78 84
             Z"
          stroke="#D8AE4A"
          strokeWidth="3.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />

        {/* Inner cusped foil arch detail */}
        <path
          d="M 28 84
             L 28 50
             C 28 42, 33 36, 40 33
             C 45 31, 48 29, 50 24
             C 52 29, 55 31, 60 33
             C 67 36, 72 42, 72 50
             L 72 84"
          stroke="#D8AE4A"
          strokeWidth="1.2"
          strokeOpacity="0.5"
          fill="none"
        />

        {/* Steaming fragrance curls over the dish */}
        <path
          d="M 46 44 C 44 40, 48 37, 47 34"
          stroke="#D8AE4A"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeOpacity="0.85"
        />
        <path
          d="M 54 44 C 52 40, 56 37, 55 34"
          stroke="#D8AE4A"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeOpacity="0.85"
        />

        {/* Covered Serving Dish (Cloche / Degh) inside the Arch (Gold) */}
        {/* Handle Knob */}
        <ellipse cx="50" cy="48" rx="3.5" ry="2.5" fill="#D8AE4A" />

        {/* Domed Cloche Cover */}
        <path
          d="M 33 66
             C 33 53, 41 49, 50 49
             C 59 49, 67 53, 67 66
             Z"
          fill="#D8AE4A"
          fillOpacity="0.25"
          stroke="#D8AE4A"
          strokeWidth="2.8"
          strokeLinejoin="round"
        />

        {/* Serving Dish Rim / Platter Tray */}
        <path
          d="M 27 68
             C 27 66.5, 30 65.5, 34 65.5
             L 66 65.5
             C 70 65.5, 73 66.5, 73 68
             C 73 69.5, 70 70.5, 66 70.5
             L 34 70.5
             C 30 70.5, 27 69.5, 27 68
             Z"
          fill="#D8AE4A"
          stroke="#D8AE4A"
          strokeWidth="1.5"
        />

        {/* Pedestal Foot Base */}
        <path
          d="M 41 71 L 38 76 L 62 76 L 59 71 Z"
          fill="#D8AE4A"
          fillOpacity="0.6"
        />

        {/* Baseline Floor Accent */}
        <line
          x1="22"
          y1="84"
          x2="78"
          y2="84"
          stroke="#D8AE4A"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );

  if (variant === 'emblem-only') {
    return <div className={`inline-flex items-center ${className}`}>{EmblemSvg}</div>;
  }

  return (
    <div className={`inline-flex items-center gap-3 ${className}`}>
      {EmblemSvg}
      <div className="flex flex-col justify-center leading-none">
        <span
          className={`font-serif tracking-wide text-[#22161F] font-semibold ${current.textTitle}`}
          style={{ letterSpacing: '0.04em' }}
        >
          Dawat
        </span>
        <span
          className={`font-sans tracking-wider text-[#574652] uppercase font-medium ${current.textSub}`}
          style={{ letterSpacing: '0.12em' }}
        >
          Every order, a feast.
        </span>
      </div>
    </div>
  );
}
