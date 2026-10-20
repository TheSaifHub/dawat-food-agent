import { contrast } from '@/theme/contrast';
import { colors, subtleTextOn, textOn, type FillName } from '@/theme/tokens';

type C = keyof typeof colors;

// Every row of the contrast table in docs/MOBILE_PLAN.md section 1: [text, fill, expected ratio, minimum, why].
// If a token changes, the ratio moves and this fails, and the doc must be updated too.
const ROWS: [C, C, number, number, string][] = [
  ['white', 'navy', 12.4, 4.5, 'CTA text'],
  ['ink', 'accent', 6.24, 4.5, 'coral badge text'],
  ['navy', 'accent', 3.97, 3, 'large text / UI only'],
  ['accent', 'card', 3.12, 3, 'coral icon on white card'],
  ['accent', 'navy', 3.97, 3, 'coral icon on navy'],
  ['ink', 'page', 17.64, 4.5, ''],
  ['ink', 'card', 19.46, 4.5, ''],
  ['ink', 'surface', 14.16, 4.5, ''],
  ['ink', 'sky', 12.25, 4.5, ''],
  ['ink', 'butter', 13.95, 4.5, ''],
  ['ink', 'sage', 10.38, 4.5, ''],
  ['ink', 'coralTint', 16.53, 4.5, ''],
  ['navy', 'page', 11.24, 4.5, ''],
  ['navy', 'card', 12.4, 4.5, ''],
  ['navy', 'surface', 9.02, 4.5, ''],
  ['navy', 'sky', 7.81, 4.5, ''],
  ['navy', 'butter', 8.89, 4.5, ''],
  ['navy', 'sage', 6.61, 4.5, ''],
  ['muted', 'page', 7.08, 4.5, ''],
  ['muted', 'card', 7.81, 4.5, ''],
  ['muted', 'surface', 5.68, 4.5, ''],
  ['muted', 'coralTint', 6.64, 4.5, ''],
  ['muted', 'butter', 5.6, 4.5, ''],
  ['muted', 'sky', 4.92, 4.5, ''],
  // Documented failures: they must stay failures, so nobody "fixes" them by using the pair in a component.
  ['white', 'accent', 3.12, 4.5, 'FAIL for text: never white on coral'],
  ['muted', 'sage', 4.17, 4.5, 'FAIL for small text: ink on sage'],
  ['accent', 'page', 2.83, 3, 'FAIL even 3:1: coral never stands alone on page'],
  ['accent', 'surface', 2.27, 3, 'FAIL 3:1: coral never stands alone on surface'],
];

describe('contrast table in docs/MOBILE_PLAN.md', () => {
  test.each(ROWS)('%s on %s is %f', (text, fill, expected) => {
    expect(contrast(colors[text], colors[fill])).toBeCloseTo(expected, 1);
  });

  test.each(ROWS.filter(([, , , , why]) => !why.startsWith('FAIL')))('%s on %s meets its minimum', (text, fill, _e, min) => {
    expect(contrast(colors[text], colors[fill])).toBeGreaterThanOrEqual(min);
  });

  test.each(ROWS.filter(([, , , , why]) => why.startsWith('FAIL')))('%s on %s stays below its minimum (documented failure)', (text, fill, _e, min) => {
    expect(contrast(colors[text], colors[fill])).toBeLessThan(min);
  });
});

describe('text colour rules used by components', () => {
  const fills: FillName[] = ['sky', 'butter', 'sage', 'surface', 'page', 'card', 'coralTint', 'navy', 'accent'];

  test.each(fills)('textOn(%s) is at least 4.5:1', (fill) => {
    expect(contrast(textOn(fill), colors[fill])).toBeGreaterThanOrEqual(4.5);
  });

  test.each(fills)('subtleTextOn(%s) is at least 4.5:1', (fill) => {
    expect(contrast(subtleTextOn(fill), colors[fill])).toBeGreaterThanOrEqual(4.5);
  });

  test('white text is only ever chosen on navy', () => {
    for (const f of fills) expect(textOn(f) === colors.white).toBe(f === 'navy');
  });

  test('muted text is never chosen on sage', () => {
    expect(subtleTextOn('sage')).not.toBe(colors.muted);
  });

  test('legend colours are exact', () => {
    expect(colors.accent).toBe('#FF5844');
    expect(colors.sky).toBe('#A6D3F2');
    expect(colors.butter).toBe('#F7D78C');
    expect(colors.sage).toBe('#AFC3A8');
    expect(colors.surface).toBe('#DBDBE5');
    expect(colors.navy).toBe('#21364B');
  });
});
