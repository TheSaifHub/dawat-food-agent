import React from 'react';

export type FoodType = 'biryani' | 'haleem' | 'kebab' | 'curry' | 'bread' | 'chai' | 'sweet' | 'thali';

interface FoodIllustrationProps {
  type: FoodType;
  className?: string;
  size?: number;
}

export function FoodIllustration({ type, className = '', size = 80 }: FoodIllustrationProps) {
  // Bespoke neutral vector illustrations in refined Nizami palette
  // (Plum #5B1E4E, Warm Terracotta #8C3A36, Sand #D9C3A5, Deep Night #22161F, Soft Gold #D8AE4A)
  switch (type) {
    case 'biryani':
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Hyderabadi Dum Biryani Pot"
        >
          {/* Background disc */}
          <circle cx="50" cy="50" r="46" fill="#F4ECE0" stroke="#E5D6C0" strokeWidth="1.5" />
          {/* Steam curls */}
          <path d="M42 22 C40 17, 44 14, 43 10" stroke="#877682" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M50 20 C48 15, 52 12, 51 8" stroke="#877682" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M58 22 C56 17, 60 14, 59 10" stroke="#877682" strokeWidth="1.8" strokeLinecap="round" />
          {/* Handi Pot Rim & Sealed Dough */}
          <ellipse cx="50" cy="38" rx="30" ry="7" fill="#EAD7B8" stroke="#5B1E4E" strokeWidth="2.5" />
          {/* Pot Body */}
          <path
            d="M 22 40
               C 20 62, 30 76, 50 76
               C 70 76, 80 62, 78 40
               Z"
            fill="#8A3828"
            stroke="#5B1E4E"
            strokeWidth="2.5"
          />
          {/* Handi Handles */}
          <path d="M 20 46 C 14 46, 14 54, 20 54" stroke="#5B1E4E" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M 80 46 C 86 46, 86 54, 80 54" stroke="#5B1E4E" strokeWidth="2.5" strokeLinecap="round" />
          {/* Rice Mound inside Handi */}
          <ellipse cx="50" cy="37" rx="26" ry="6" fill="#F7DC98" />
          {/* Saffron & Fried Onion flecks */}
          <circle cx="44" cy="36" r="1.5" fill="#D9531E" />
          <circle cx="52" cy="35" r="1.5" fill="#5B1E4E" />
          <circle cx="58" cy="37" r="1.5" fill="#D9531E" />
          <circle cx="48" cy="38" r="1.5" fill="#3D5A20" />
        </svg>
      );

    case 'haleem':
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Deccani Shahi Haleem Bowl"
        >
          <circle cx="50" cy="50" r="46" fill="#F4ECE0" stroke="#E5D6C0" strokeWidth="1.5" />
          {/* Deep earthenware bowl */}
          <ellipse cx="50" cy="74" rx="20" ry="4" fill="#C9B498" />
          <path
            d="M 20 44
               C 20 68, 30 74, 50 74
               C 70 74, 80 68, 80 44
               Z"
            fill="#5B1E4E"
            stroke="#3F1436"
            strokeWidth="2"
          />
          {/* Bowl Rim */}
          <ellipse cx="50" cy="44" rx="30" ry="9" fill="#99582A" stroke="#3F1436" strokeWidth="2" />
          {/* Haleem surface with pure ghee swirl */}
          <ellipse cx="50" cy="44" rx="27" ry="7" fill="#80471C" />
          <path
            d="M 38 43 C 44 41, 52 46, 62 43"
            stroke="#E0AC38"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          {/* Fried Birista & Mint Leaves Garnish */}
          <line x1="45" y1="41" x2="49" y2="45" stroke="#3F1436" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="53" y1="42" x2="57" y2="46" stroke="#3F1436" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="50" cy="45" r="2" fill="#2E7D32" />
          {/* Lemon Wedge */}
          <path d="M 66 38 C 72 38, 74 42, 68 44 Z" fill="#F4D03F" stroke="#B7950B" strokeWidth="1" />
        </svg>
      );

    case 'kebab':
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Charcoal Seekh Kebab Skewer"
        >
          <circle cx="50" cy="50" r="46" fill="#F4ECE0" stroke="#E5D6C0" strokeWidth="1.5" />
          {/* Skewer Metal Needle */}
          <line x1="16" y1="84" x2="84" y2="16" stroke="#877682" strokeWidth="3" strokeLinecap="round" />
          {/* Kebab Cylinders */}
          <rect
            x="24"
            y="54"
            width="20"
            height="14"
            rx="5"
            transform="rotate(-45 24 54)"
            fill="#7B241C"
            stroke="#511410"
            strokeWidth="1.5"
          />
          <rect
            x="39"
            y="39"
            width="20"
            height="14"
            rx="5"
            transform="rotate(-45 39 39)"
            fill="#922B21"
            stroke="#511410"
            strokeWidth="1.5"
          />
          <rect
            x="54"
            y="24"
            width="20"
            height="14"
            rx="5"
            transform="rotate(-45 54 24)"
            fill="#7B241C"
            stroke="#511410"
            strokeWidth="1.5"
          />
          {/* Char marks */}
          <line x1="36" y1="58" x2="40" y2="54" stroke="#22161F" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="51" y1="43" x2="55" y2="39" stroke="#22161F" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="66" y1="28" x2="70" y2="24" stroke="#22161F" strokeWidth="1.5" strokeLinecap="round" />
          {/* Onion Rings & Green Chilli on the side */}
          <circle cx="72" cy="70" r="8" stroke="#C39BD3" strokeWidth="2" fill="none" />
          <circle cx="72" cy="70" r="4" stroke="#C39BD3" strokeWidth="1" fill="none" />
          <path d="M 30 76 C 36 78, 40 73, 44 75" stroke="#27AE60" strokeWidth="3" strokeLinecap="round" />
        </svg>
      );

    case 'curry':
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Shahi Gravy & Salan Karahi"
        >
          <circle cx="50" cy="50" r="46" fill="#F4ECE0" stroke="#E5D6C0" strokeWidth="1.5" />
          {/* Karahi Round Pot */}
          <path
            d="M 22 46
               C 22 72, 34 78, 50 78
               C 66 78, 78 72, 78 46
               Z"
            fill="#5B1E4E"
            stroke="#3F1436"
            strokeWidth="2"
          />
          {/* Brass Handles */}
          <circle cx="17" cy="46" r="5" stroke="#B78A28" strokeWidth="2.5" fill="none" />
          <circle cx="83" cy="46" r="5" stroke="#B78A28" strokeWidth="2.5" fill="none" />
          {/* Curry Surface */}
          <ellipse cx="50" cy="46" rx="27" ry="8" fill="#C0392B" stroke="#922B21" strokeWidth="1.5" />
          {/* Cream Swirl */}
          <path
            d="M 40 45
               C 46 41, 54 50, 60 46"
            stroke="#FAF6EF"
            strokeWidth="2"
            strokeLinecap="round"
          />
          {/* Bhavnagri Mirchi Silhouette for Salan */}
          <path
            d="M 46 43 C 50 42, 54 44, 56 47 C 54 48, 48 46, 46 43 Z"
            fill="#27AE60"
          />
        </svg>
      );

    case 'bread':
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Saffron Sheermal & Roti"
        >
          <circle cx="50" cy="50" r="46" fill="#F4ECE0" stroke="#E5D6C0" strokeWidth="1.5" />
          {/* Folded Roomali underneath */}
          <path
            d="M 25 55 L 75 45 L 65 75 Z"
            fill="#EADBC8"
            stroke="#D3BEA2"
            strokeWidth="1.5"
          />
          {/* Golden Saffron Sheermal disc */}
          <ellipse cx="48" cy="48" rx="26" ry="20" fill="#E59866" stroke="#BA4A00" strokeWidth="2" />
          {/* Prick pattern of royal sheermal */}
          <circle cx="40" cy="42" r="1.5" fill="#935116" />
          <circle cx="48" cy="40" r="1.5" fill="#935116" />
          <circle cx="56" cy="42" r="1.5" fill="#935116" />
          <circle cx="44" cy="48" r="1.5" fill="#935116" />
          <circle cx="52" cy="48" r="1.5" fill="#935116" />
          <circle cx="48" cy="54" r="1.5" fill="#935116" />
        </svg>
      );

    case 'chai':
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Irani Chai Glass and Osmania Biscuit"
        >
          <circle cx="50" cy="50" r="46" fill="#F4ECE0" stroke="#E5D6C0" strokeWidth="1.5" />
          {/* Steam */}
          <path d="M42 22 C40 18, 44 14, 42 10" stroke="#877682" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M48 20 C46 16, 50 12, 48 8" stroke="#877682" strokeWidth="1.5" strokeLinecap="round" />
          {/* Saucer */}
          <ellipse cx="45" cy="74" rx="28" ry="6" fill="#FAF6EF" stroke="#5B1E4E" strokeWidth="1.8" />
          {/* Chai Cup */}
          <path
            d="M 26 40 L 32 68 C 34 72, 56 72, 58 68 L 64 40 Z"
            fill="#FAF6EF"
            stroke="#5B1E4E"
            strokeWidth="2"
          />
          {/* Cup Handle */}
          <path d="M 63 45 C 72 45, 72 60, 60 62" stroke="#5B1E4E" strokeWidth="2" fill="none" strokeLinecap="round" />
          {/* Creamy golden Irani Chai brew */}
          <ellipse cx="45" cy="42" rx="17" ry="4" fill="#C07D38" />
          {/* Osmania Biscuit beside saucer */}
          <ellipse cx="74" cy="66" rx="10" ry="7" fill="#E0A96D" stroke="#A0693B" strokeWidth="1.5" />
          <circle cx="72" cy="65" r="1" fill="#784212" />
          <circle cx="76" cy="67" r="1" fill="#784212" />
        </svg>
      );

    case 'sweet':
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Shahi Double Ka Meetha Bowl"
        >
          <circle cx="50" cy="50" r="46" fill="#F4ECE0" stroke="#E5D6C0" strokeWidth="1.5" />
          {/* Pedestal Bowl */}
          <ellipse cx="50" cy="76" rx="18" ry="4" fill="#C9B498" />
          <path
            d="M 24 46
               C 24 68, 36 74, 50 74
               C 64 74, 76 68, 76 46
               Z"
            fill="#FAF6EF"
            stroke="#5B1E4E"
            strokeWidth="2"
          />
          {/* Golden syrup dessert base */}
          <ellipse cx="50" cy="46" rx="24" ry="7" fill="#D4AC0D" stroke="#9A7D0A" strokeWidth="1" />
          {/* Bread triangles soaked in rabri */}
          <polygon points="40,43 52,38 48,48" fill="#B9770E" />
          <polygon points="50,44 62,40 58,49" fill="#935116" />
          {/* Edible Silver Leaf (Varq) & Pistachio slivers */}
          <rect x="44" y="42" width="6" height="4" fill="#F2F4F4" stroke="#BDC3C7" strokeWidth="0.8" />
          <circle cx="42" cy="46" r="1.5" fill="#27AE60" />
          <circle cx="56" cy="45" r="1.5" fill="#27AE60" />
        </svg>
      );

    case 'thali':
    default:
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`shrink-0 ${className}`}
          aria-label="Illustration: Deccani Royal Thali Platter"
        >
          {/* Thali Brass Platter */}
          <circle cx="50" cy="50" r="44" fill="#F4ECE0" stroke="#5B1E4E" strokeWidth="2.5" />
          <circle cx="50" cy="50" r="40" stroke="#D8AE4A" strokeWidth="1.5" strokeDasharray="3 3" fill="none" />
          {/* Center Rice / Biryani mound */}
          <circle cx="50" cy="50" r="16" fill="#F9E79F" stroke="#D4AC0D" strokeWidth="1.5" />
          <circle cx="48" cy="49" r="1" fill="#784212" />
          <circle cx="52" cy="51" r="1" fill="#27AE60" />
          {/* Surrounding Katoris */}
          {/* Dal */}
          <circle cx="30" cy="30" r="10" fill="#F7DC6F" stroke="#5B1E4E" strokeWidth="1.5" />
          {/* Baingan */}
          <circle cx="70" cy="30" r="10" fill="#6C3483" stroke="#5B1E4E" strokeWidth="1.5" />
          {/* Paneer / Subz */}
          <circle cx="74" cy="56" r="9" fill="#E67E22" stroke="#5B1E4E" strokeWidth="1.5" />
          {/* Sweet (Qubani) */}
          <circle cx="50" cy="74" r="9" fill="#BA4A00" stroke="#5B1E4E" strokeWidth="1.5" />
          {/* Roti / Puri */}
          <circle cx="26" cy="56" r="9" fill="#EDBB99" stroke="#5B1E4E" strokeWidth="1.5" />
        </svg>
      );
  }
}
