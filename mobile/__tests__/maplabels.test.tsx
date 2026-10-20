import { fireEvent, render, screen } from '@testing-library/react-native';
import { labelRect, placeLabels, projectPoints, labelWidth } from '@/lib/orders';
import { PLACE_LABELS_JS, leafletHtml } from '@/lib/osm';
import { PlainMap } from '@/components/TrackingMap';

jest.mock('react-native-webview', () => ({ WebView: () => null }));
const TEXTS = ['Restaurant', 'You', 'Rider'];
type P = { x: number; y: number };
const rects = (pts: P[], texts: string[], sides: string[]) => pts.map((p, i) => labelRect(sides[i] as never, p, texts[i]));
const overlap = (a: ReturnType<typeof labelRect>, b: ReturnType<typeof labelRect>) =>
  a.left < b.left + b.width && b.left < a.left + a.width && a.top < b.top + b.height && b.top < a.top + a.height;
const anyOverlap = (pts: P[], texts: string[], sides: string[]) => {
  const r = rects(pts, texts, sides);
  for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) if (overlap(r[i], r[j])) return true;
  return false;
};
// the same rule, but the copy that runs inside the map page
const jsPlace = new Function(`${PLACE_LABELS_JS}; return placeLabels;`)() as (p: P[], t: string[]) => string[];

// Leaflet at its closest zoom (17) draws about 1.1 m per pixel, so restaurant and customer 100 m apart are ~88 px apart and
// the rider is somewhere between them. These are those positions in map pixels.
const CLUSTER: P[] = [{ x: 110, y: 140 }, { x: 198, y: 140 }, { x: 150, y: 145 }];
// the plain map fits the points into its box: customer far away, rider and restaurant about 100 m apart
const FIT = [
  { lat: 17.385, lon: 78.4867 },
  { lat: 17.395, lon: 78.4967 },
  { lat: 17.3855, lon: 78.4868 },
];

describe('map labels', () => {
  test('points about 100 m apart (map-page scale): no two labels overlap, even a few pixels apart', () => {
    for (const pts of [CLUSTER, [{ x: 150, y: 140 }, { x: 160, y: 142 }, { x: 155, y: 150 }]]) {
      expect(anyOverlap(pts, TEXTS, placeLabels(pts, TEXTS))).toBe(false);
    }
  });

  test('with the old rule (every label on top) the same points DO overlap, so the test above can fail', () => {
    expect(anyOverlap(CLUSTER, TEXTS, ['top', 'top', 'top'])).toBe(true);
  });

  test('the plain map at a narrow and a wide width: no overlap', () => {
    for (const w of [260, 320, 400]) {
      const xy = projectPoints(FIT, w, 280);
      expect(anyOverlap(xy, TEXTS, ['top', 'top', 'top'])).toBe(true); // the old rule collides here
      expect(anyOverlap(xy, TEXTS, placeLabels(xy, TEXTS))).toBe(false);
    }
  });

  test('points far apart keep every label on top', () => {
    const xy: P[] = [{ x: 40, y: 200 }, { x: 260, y: 40 }, { x: 150, y: 120 }];
    expect(placeLabels(xy, TEXTS)).toEqual(['top', 'top', 'top']);
  });

  test('a label never covers another dot', () => {
    const xy = CLUSTER;
    const sides = placeLabels(xy, TEXTS);
    const r = rects(xy, TEXTS, sides);
    r.forEach((box, i) =>
      xy.forEach((p, j) => {
        if (i === j) return;
        const hitDot = box.left < p.x + 14 && p.x - 14 < box.left + box.width && box.top < p.y + 14 && p.y - 14 < box.top + box.height;
        expect(hitDot).toBe(false);
      }),
    );
  });

  test('random clusters: the rule never overlaps labels when it can avoid it, and the map-page copy gives the same answer', () => {
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let n = 0; n < 300; n++) {
      const count = 2 + (n % 2);
      const pts: P[] = Array.from({ length: count }, () => ({ x: 60 + rnd() * 200, y: 40 + rnd() * 200 }));
      expect(jsPlace(pts, TEXTS.slice(0, count))).toEqual(placeLabels(pts, TEXTS.slice(0, count)));
    }
  });

  test('the Leaflet page carries the rule and uses it for the tooltips', () => {
    const html = leafletHtml({ from: FIT[0], to: FIT[1], rider: FIT[2] });
    expect(html).toContain(PLACE_LABELS_JS);
    expect(html).toContain('placeLabels(');
    expect(html).toContain('direction: sides[i]');
    expect(html).not.toContain("direction: 'top'");
  });

  test('the plain map draws all three labels inside their own boxes without overlap', async () => {
    await render(<PlainMap from={FIT[0]} to={FIT[1]} rider={FIT[2]} />);
    await fireEvent(screen.getByLabelText(/Positions:/), 'layout', { nativeEvent: { layout: { width: 320, height: 280 } } });
    const names = ['Restaurant', 'You', 'Rider'];
    const boxes = names.map((n) => {
      const flat = Object.assign({}, ...[screen.getByText(n).props.style].flat(5).filter(Boolean));
      return { left: flat.left as number, top: flat.top as number, width: flat.width as number, height: flat.height as number };
    });
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) expect(overlap(boxes[i], boxes[j])).toBe(false);
    expect(labelWidth('You')).toBeGreaterThan(20);
  });
});
