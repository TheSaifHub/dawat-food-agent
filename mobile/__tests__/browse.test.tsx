import { render, screen } from '@testing-library/react-native';
import { listPath, homePath, PAGE_SIZE, type RestaurantCardData } from '@/lib/browse';
import { parseArea } from '@/lib/area';
import { RestaurantCard, cardSummary } from '@/components/RestaurantCard';
import { Chip } from '@/components/Chip';
import { MIN_TARGET } from '@/theme/tokens';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const fs = require('fs');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const path = require('path');
declare const __dirname: string;

const R: RestaurantCardData = {
  restaurant_id: 'r1',
  name: 'Udupi Vihar',
  cuisines: ['South Indian'],
  veg_only: true,
  is_chain: false,
  branch: { branch_id: 'b1', label: 'Madhapur', area: 'Madhapur', street: null, distance_km: 0.1 },
  more_branches_in_range: 0,
  delivery_fee: 25,
  price_for_one: 100,
  mild_mains: 12,
  mild_friendly: true,
};

describe('browse URLs', () => {
  test('the list path carries only filters the user chose', () => {
    expect(listPath('madhapur', { cuisine: null, vegOnly: false, mild: false, sort: 'distance' }, 0)).toBe(
      `/areas/madhapur/restaurants?limit=${PAGE_SIZE}&offset=0&sort=distance`,
    );
    expect(listPath('madhapur', { cuisine: 'South Indian', vegOnly: true, mild: true, sort: 'price' }, 20)).toBe(
      `/areas/madhapur/restaurants?limit=${PAGE_SIZE}&offset=20&sort=price&cuisine=South%20Indian&veg_only=true&mild=true`,
    );
  });
  test('an area id is encoded, so it cannot add query parts', () => {
    expect(homePath('a/b?x=1')).toBe('/areas/a%2Fb%3Fx%3D1/home');
  });
});

describe('remembered area', () => {
  test.each([null, '', 'not json', '{}', '{"area_id":"x"}', '{"area_id":1,"name":"y"}', '[]'])('%p is not an area', (raw) => {
    expect(parseArea(raw)).toBeNull();
  });
  test('a good value is read back', () => {
    expect(parseArea('{"area_id":"madhapur","name":"Madhapur","extra":1}')).toEqual({ area_id: 'madhapur', name: 'Madhapur' });
  });
});

describe('restaurant card shows the backend values as they are', () => {
  test('summary uses the given distance, fee and typical price', () => {
    expect(cardSummary(R)).toBe('0.1 km · Delivery ₹25 · Typical main ₹100');
  });
  test('a distance the backend rounds to 0 reads "Under 0.1 km", not "0 km"', () => {
    expect(cardSummary({ ...R, branch: { ...R.branch, distance_km: 0 } })).toMatch(/^Under 0\.1 km · /);
  });
  test('a fee the backend sends as 0 reads as free; a missing price is left out, never guessed', () => {
    expect(cardSummary({ ...R, delivery_fee: 0, price_for_one: null })).toBe('0.1 km · Free delivery');
  });
  test('veg badge, mild badge and branches are shown; there is no rating or delivery time', async () => {
    await render(<RestaurantCard r={{ ...R, more_branches_in_range: 3 }} />);
    expect(screen.getByText('Veg only')).toBeTruthy();
    expect(screen.getByText('Mild options')).toBeTruthy();
    expect(screen.getByText('3 more branches nearby')).toBeTruthy();
    expect(screen.queryByText(/★|rating|min\b|mins|ETA/i)).toBeNull();
  });
});

describe('chips', () => {
  test('44pt tall and report selected state', async () => {
    await render(<Chip label="Veg only" selected onPress={() => {}} />);
    const chip = screen.getByRole('button', { name: 'Veg only' });
    expect(chip.props.accessibilityState).toMatchObject({ selected: true });
    expect(JSON.stringify(chip.props.style)).toContain(`"minHeight":${MIN_TARGET}`);
  });
});

describe('rules for browse screens (source scan)', () => {
  const dir = path.join(__dirname, '..', 'src');
  const browseFiles = [
    'app/(tabs)/index.tsx',
    'app/restaurants.tsx',
    'components/RestaurantCard.tsx',
    'components/AreaPicker.tsx',
    'lib/browse.ts',
  ].map((f) => fs.readFileSync(path.join(dir, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, ''));

  test('no price or total is computed on the device', () => {
    for (const src of browseFiles) expect(src).not.toMatch(/(delivery_fee|price_for_one)\s*[-+*/]|[-+*/]\s*(delivery_fee|price_for_one)/);
  });
  test('restaurant screens show the OpenStreetMap credit', () => {
    expect(browseFiles[0]).toContain('<OsmCredit />');
    expect(browseFiles[1]).toContain('<OsmCredit />');
  });
  test('no ratings or delivery-time estimates', () => {
    for (const src of browseFiles) expect(src).not.toMatch(/rating|★|\bETA\b|mins\b/i);
  });
});
