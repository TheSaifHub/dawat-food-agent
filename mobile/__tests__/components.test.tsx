import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Button } from '@/components/Button';
import { Tile } from '@/components/Tile';
import { Pill } from '@/components/Pill';
import { DEMO_BANNER_TEXT, DemoBanner } from '@/components/DemoBanner';
import { AppText } from '@/components/AppText';
import { TabBar, tabLabel, type TabBarProps } from '@/components/TabBar';
import { colors, fontFamilies } from '@/theme/tokens';

// RNTL 14: render and fireEvent are async and must be awaited; screen queries are synchronous.
const flat = (node: { props: { style?: unknown } }) => StyleSheet.flatten(node.props.style as never) as Record<string, unknown>;

describe('Button', () => {
  test('primary is navy with white text, never coral', async () => {
    await render(<Button label="Pay" onPress={() => {}} />);
    const btn = screen.getByRole('button', { name: 'Pay' });
    expect(flat(btn).backgroundColor).toBe(colors.navy);
    expect(flat(screen.getByText('Pay')).color).toBe(colors.white);
    expect(flat(btn).backgroundColor).not.toBe(colors.accent);
  });

  test('is at least 44pt tall and calls onPress', async () => {
    const onPress = jest.fn();
    await render(<Button label="Go" onPress={onPress} />);
    const btn = screen.getByRole('button', { name: 'Go' });
    expect(flat(btn).minHeight as number).toBeGreaterThanOrEqual(44);
    await fireEvent.press(btn);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  test('a disabled or loading button does not fire', async () => {
    const onPress = jest.fn();
    await render(<Button label="Busy" onPress={onPress} loading />);
    await fireEvent.press(screen.getByRole('button', { name: 'Busy' }));
    expect(onPress).not.toHaveBeenCalled();
  });

  test('the label can differ from the accessibility label (card buttons send "Yes" however the label reads)', async () => {
    await render(<Button label="Yes, place this order" accessibilityLabel="Yes, place this order" onPress={() => {}} />);
    expect(screen.getByRole('button', { name: 'Yes, place this order' })).toBeTruthy();
  });
});

describe('Tile', () => {
  test.each([
    ['sky', colors.ink],
    ['butter', colors.ink],
    ['sage', colors.ink],
    ['navy', colors.white],
  ] as const)('%s tile text colour', async (fill, expected) => {
    await render(<Tile fill={fill} title="Title" subtitle="Sub" />);
    expect(flat(screen.getByText('Title')).color).toBe(expected);
  });

  test('subtitle on sage is ink, not muted', async () => {
    await render(<Tile fill="sage" title="T" subtitle="Healthy" />);
    expect(flat(screen.getByText('Healthy')).color).toBe(colors.ink);
  });

  test('is a button only when it has onPress', async () => {
    const onPress = jest.fn();
    await render(<Tile fill="sky" title="Ask" subtitle="x" onPress={onPress} />);
    await fireEvent.press(screen.getByRole('button'));
    expect(onPress).toHaveBeenCalled();
  });
});

describe('Pill', () => {
  test('is navy with white text', async () => {
    await render(<Pill label="Best match" dot="butter" />);
    expect(flat(screen.getByText('Best match')).color).toBe(colors.white);
    expect(flat(screen.getByLabelText('Best match')).backgroundColor).toBe(colors.navy);
  });
});

describe('DemoBanner', () => {
  test('shows the exact demo notice', async () => {
    await render(<DemoBanner />);
    expect(screen.getByText(DEMO_BANNER_TEXT)).toBeTruthy();
    expect(DEMO_BANNER_TEXT).toBe('Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant.');
  });
});

describe('AppText', () => {
  test('uses the UI font for English and Noto Sans Telugu for Telugu script', async () => {
    await render(
      <>
        <AppText>Hello</AppText>
        <AppText>మీరు చెప్పే వరకు</AppText>
      </>,
    );
    expect(flat(screen.getByText('Hello')).fontFamily).toBe(fontFamilies.ui[400]);
    expect(flat(screen.getByText('మీరు చెప్పే వరకు')).fontFamily).toBe(fontFamilies.telugu[400]);
  });
});

describe('TabBar', () => {
  const routes = ['index', 'chat', 'cart', 'orders', 'profile'].map((name) => ({ key: `${name}-k`, name }));
  async function setup(index: number, cartBadge?: number) {
    const navigate = jest.fn();
    const emit = jest.fn(() => ({ defaultPrevented: false }));
    const props: TabBarProps = {
      state: { index, routes },
      descriptors: Object.fromEntries(routes.map((r) => [r.key, { options: { tabBarBadge: r.name === 'cart' ? cartBadge : undefined } }])),
      navigation: { emit, navigate },
    };
    await render(
      <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 360, height: 800 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
        <TabBar {...props} />
      </SafeAreaProvider>,
    );
    return { navigate, emit };
  }

  test('shows the five tabs in order, the active one selected', async () => {
    await setup(0);
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.props.accessibilityLabel)).toEqual(['Home', 'Dawat AI', 'Cart', 'Orders', 'Profile']);
    expect(tabs[0].props.accessibilityState.selected).toBe(true);
    expect(tabs[1].props.accessibilityState.selected).toBe(false);
  });

  test('pressing a tab navigates; pressing the active tab does not', async () => {
    const { navigate } = await setup(0);
    await fireEvent.press(screen.getByRole('tab', { name: 'Orders' }));
    expect(navigate).toHaveBeenCalledWith('orders');
    navigate.mockClear();
    await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
    expect(navigate).not.toHaveBeenCalled();
  });

  test('the cart badge is read aloud and uses dark text on coral', async () => {
    await setup(2, 2);
    expect(screen.getByRole('tab', { name: 'Cart, 2 items' })).toBeTruthy();
    const badge = screen.getByTestId('tab-badge');
    expect(flat(badge).backgroundColor).toBe(colors.accent);
    expect(flat(screen.getByText('2')).color).toBe(colors.ink);
  });

  test('only the active tab has the raised circle, and it is sky (not coral)', async () => {
    await setup(1);
    const circles = screen.getAllByTestId('tab-active-circle');
    expect(circles).toHaveLength(1);
    expect(circles[0].props.color ?? flat(circles[0]).color).toBe(colors.sky);
  });

  test('no badge when the cart is empty', async () => {
    await setup(0);
    expect(screen.queryByTestId('tab-badge')).toBeNull();
  });

  test('tabLabel wording', () => {
    expect(tabLabel('Cart')).toBe('Cart');
    expect(tabLabel('Cart', 0)).toBe('Cart');
    expect(tabLabel('Cart', 1)).toBe('Cart, 1 item');
    expect(tabLabel('Cart', 3)).toBe('Cart, 3 items');
  });
});
