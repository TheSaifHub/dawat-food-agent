// OpenStreetMap tiles in the tracking map (D-076). The policy (operations.osmfoundation.org/policies/tiles): visible
// attribution, an identifying User-Agent (generic library defaults are blocked), a valid Referer for web pages, no
// bulk download, prefetch or offline saving, and access may be withdrawn at any time. Interactive use of the standard
// tile server by a small demo app is allowed; this is a demo and it falls back to a plain map if tiles are refused.

export const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const OSM_ATTRIBUTION_HTML = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
export const LEAFLET_VERSION = '1.9.4';
export const LEAFLET_CSS = `https://cdnjs.cloudflare.com/ajax/libs/leaflet/${LEAFLET_VERSION}/leaflet.css`;
export const LEAFLET_JS = `https://cdnjs.cloudflare.com/ajax/libs/leaflet/${LEAFLET_VERSION}/leaflet.js`;

/** The page's address for the WebView, so tile requests carry a Referer. Replace with the app's real address when deployed. */
export const MAP_BASE_URL = 'https://dawat-demo.example/';
/** Identifies this app to the tile server. Add a contact address when the app is deployed (the policy asks for one). */
export const MAP_USER_AGENT = 'DawatDemoApp/0.1 (demo project, not affiliated with any restaurant)';

export type MapPoints = { from: { lat: number; lon: number }; to: { lat: number; lon: number }; rider: { lat: number; lon: number } | null };

/** The page shown in the WebView: Leaflet with OSM tiles, the attribution, the restaurant, the delivery point and the rider. */
/** The same label rule as placeLabels in lib/orders.ts, as plain JavaScript for inside the map page. */
export const PLACE_LABELS_JS = `function placeLabels(points, texts) {
  var SIDES = ['top', 'bottom', 'right', 'left'], H = 16, R = 14, G = 4, o = R + G;
  function box(side, p, w) {
    if (side === 'top') return [p.x - w / 2, p.y - o - H, p.x + w / 2, p.y - o];
    if (side === 'bottom') return [p.x - w / 2, p.y + o, p.x + w / 2, p.y + o + H];
    if (side === 'right') return [p.x + o, p.y - H / 2, p.x + o + w, p.y + H / 2];
    return [p.x - o - w, p.y - H / 2, p.x - o, p.y + H / 2];
  }
  function hit(a, b) { return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]; }
  var dots = points.map(function (p) { return [p.x - R, p.y - R, p.x + R, p.y + R]; });
  var placed = [];
  return points.map(function (p, i) {
    var w = texts[i].length * 7 + 8, pick = SIDES[0], found = false;
    for (var k = 0; k < SIDES.length && !found; k++) {
      var b = box(SIDES[k], p, w);
      if (!placed.some(function (q) { return hit(b, q); }) && !dots.some(function (d, j) { return j !== i && hit(b, d); })) { pick = SIDES[k]; found = true; }
    }
    placed.push(box(pick, p, w));
    return pick;
  });
}`;

export function leafletHtml(p: MapPoints): string {
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="${LEAFLET_CSS}"/>
<style>html,body,#m{height:100%;margin:0}</style></head><body><div id="m"></div>
<script src="${LEAFLET_JS}"></script>
<script>
${PLACE_LABELS_JS}
const post = (o) => window.ReactNativeWebView.postMessage(JSON.stringify(o));
try {
  const from = [${p.from.lat}, ${p.from.lon}], to = [${p.to.lat}, ${p.to.lon}];
  const map = L.map('m', { zoomControl: false, attributionControl: true });
  let ok = 0, err = 0;
  const tiles = L.tileLayer('${OSM_TILE_URL}', { maxZoom: 19, attribution: '${OSM_ATTRIBUTION_HTML}' }).addTo(map);
  tiles.on('tileload', () => { ok++; post({ type: 'tiles', ok, err }); });
  tiles.on('tileerror', () => { err++; post({ type: 'tiles', ok, err }); });
  const marks = [];
  const mark = (ll, color, text, radius) => {
    const m = L.circleMarker(ll, { radius, color: '#21364B', weight: 3, fillColor: color, fillOpacity: 1 }).addTo(map);
    m._text = text; m._side = null;
    marks.push(m);
  };
  // Put each label on a side where it does not cover another label or dot (the points can be only ~100 m apart).
  const relabel = () => {
    const sides = placeLabels(marks.map((m) => map.latLngToContainerPoint(m.getLatLng())), marks.map((m) => m._text));
    marks.forEach((m, i) => {
      if (m._side === sides[i]) return;
      m._side = sides[i];
      m.unbindTooltip().bindTooltip(m._text, { permanent: true, direction: sides[i] });
    });
  };
  mark(from, '#F7D78C', 'Restaurant', 9);
  mark(to, '#A6D3F2', 'You', 9);
  L.polyline([from, to], { color: '#21364B', weight: 3, dashArray: '6 8' }).addTo(map);
  map.fitBounds([from, to], { padding: [50, 50], maxZoom: 17 });
  relabel();
  map.on('zoomend', relabel);
  let rider = null;
  window.setRider = (lat, lon) => {
    if (rider) rider.setLatLng([lat, lon]);
    else { mark([lat, lon], '#FF5844', 'Rider', 11); rider = marks[marks.length - 1]; }
    relabel();
  };
  ${p.rider ? `window.setRider(${p.rider.lat}, ${p.rider.lon});` : ''}
  post({ type: 'ready' });
} catch (e) { post({ type: 'fatal' }); }
</script></body></html>`;
}
