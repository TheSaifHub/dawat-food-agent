// Design tokens from docs/design/mobile_flow_v2.png (see docs/MOBILE_PLAN.md section 1).
// Legend colours are exact; page, navy, ink, muted and coralTint were sampled from the image.
// __tests__/contrast.test.ts recomputes every contrast ratio the plan quotes.

export const colors = {
  accent: '#FF5844', // coral: icons, badges (with dark text), active states, large text. NEVER white text on it.
  sky: '#A6D3F2',
  butter: '#F7D78C',
  sage: '#AFC3A8',
  surface: '#DBDBE5',
  page: '#E8F6FD',
  card: '#FFFFFF',
  navy: '#21364B', // primary buttons, Total tile, active segment, tracking card
  ink: '#050D1A', // body text and headings
  muted: '#325574', // secondary text (never on sage or coral)
  coralTint: '#FBE8EA',
  white: '#FFFFFF', // text colour only, and only on navy
} as const;

export type ColorName = keyof typeof colors;

/** Fills a tile or card may use. */
export type FillName = 'sky' | 'butter' | 'sage' | 'surface' | 'page' | 'card' | 'coralTint' | 'navy' | 'accent';

/** The one text colour that is allowed on each fill (all >= 4.5:1; checked by the contrast test). */
export function textOn(fill: FillName): string {
  return fill === 'navy' ? colors.white : colors.ink;
}

/** Fills where the secondary (muted) text colour keeps >= 4.5:1. Not sage, not coral, not navy. */
const MUTED_OK: readonly FillName[] = ['page', 'card', 'surface', 'butter', 'sky', 'coralTint'];

export function subtleTextOn(fill: FillName): string {
  return MUTED_OK.includes(fill) ? colors.muted : textOn(fill);
}

export const radii = { sm: 12, md: 20, lg: 28, pill: 999 } as const;
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const MIN_TARGET = 44; // points; touch targets are never smaller

export const fontFamilies = {
  ui: {
    400: 'PlusJakartaSans_400Regular',
    500: 'PlusJakartaSans_500Medium',
    600: 'PlusJakartaSans_600SemiBold',
    700: 'PlusJakartaSans_700Bold',
    800: 'PlusJakartaSans_800ExtraBold',
  },
  telugu: {
    400: 'NotoSansTelugu_400Regular',
    500: 'NotoSansTelugu_500Medium',
    600: 'NotoSansTelugu_600SemiBold',
    700: 'NotoSansTelugu_700Bold',
    800: 'NotoSansTelugu_700Bold',
  },
  wordmark: 'Outfit_700Bold',
} as const;

export type Weight = keyof typeof fontFamilies.ui;
