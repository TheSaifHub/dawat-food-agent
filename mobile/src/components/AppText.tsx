import { Text, type TextProps, type TextStyle } from 'react-native';
import { colors, fontFamilies, type Weight } from '@/theme/tokens';
import { hasTelugu, plainText } from '@/lib/script';

const SIZES = { display: 30, title: 20, body: 15, caption: 12 } as const;
export type TextVariant = keyof typeof SIZES;

type Props = TextProps & {
  variant?: TextVariant;
  weight?: Weight;
  color?: string;
};

/** Text that picks Noto Sans Telugu for Telugu script and the UI font otherwise. Scales with the user's text size. */
export function AppText({ variant = 'body', weight = 400, color = colors.ink, style, children, ...rest }: Props) {
  const family = hasTelugu(plainText(children)) ? fontFamilies.telugu[weight] : fontFamilies.ui[weight];
  const size = SIZES[variant];
  const base: TextStyle = { fontFamily: family, fontSize: size, lineHeight: Math.round(size * 1.4), color };
  return (
    <Text {...rest} style={[base, style]}>
      {children}
    </Text>
  );
}
