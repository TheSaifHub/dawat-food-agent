import { useEffect, useMemo, useRef, useState } from 'react';
import { View } from 'react-native';
import { WebView } from 'react-native-webview';
import { AppText } from './AppText';
import { OsmCredit } from './OsmCredit';
import { MAP_BASE_URL, MAP_USER_AGENT, leafletHtml } from '@/lib/osm';
import { labelRect, placeLabels, projectPoints, type LatLon } from '@/lib/orders';
import { colors, radii } from '@/theme/tokens';

const HEIGHT = 280;
const GIVE_UP_MS = 10_000; // no tile by then: show the plain map instead

type Props = { from: LatLon; to: LatLon; rider: LatLon | null };

/**
 * The tracking map: Leaflet with OpenStreetMap tiles inside a WebView, the rider moved by the server's position. If the
 * tiles are refused or never arrive, a plain map (positions only, no tiles) takes its place. Either way the OSM credit
 * stays under it. Positions are the server's; nothing is estimated here.
 */
export function TrackingMap({ from, to, rider }: Props) {
  const [mode, setMode] = useState<'try' | 'tiles' | 'plain'>('try');
  const web = useRef<WebView>(null);
  const html = useMemo(() => leafletHtml({ from, to, rider: null }), [from.lat, from.lon, to.lat, to.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (mode !== 'try') return;
    const t = setTimeout(() => setMode((m) => (m === 'try' ? 'plain' : m)), GIVE_UP_MS);
    return () => clearTimeout(t);
  }, [mode]);

  useEffect(() => {
    if (mode === 'plain' || !rider) return;
    web.current?.injectJavaScript(`window.setRider && window.setRider(${rider.lat}, ${rider.lon}); true;`);
  }, [rider?.lat, rider?.lon, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <View style={{ gap: 6 }}>
      <View style={{ height: HEIGHT, borderRadius: radii.md, overflow: 'hidden', backgroundColor: colors.surface }}>
        {mode === 'plain' ? (
          <PlainMap from={from} to={to} rider={rider} />
        ) : (
          <WebView
            ref={web}
            originWhitelist={['*']}
            source={{ html, baseUrl: MAP_BASE_URL }}
            userAgent={MAP_USER_AGENT}
            javaScriptEnabled
            onLoadEnd={() => rider && web.current?.injectJavaScript(`window.setRider && window.setRider(${rider.lat}, ${rider.lon}); true;`)}
            onError={() => setMode('plain')}
            onHttpError={() => setMode('plain')}
            onMessage={(e) => {
              try {
                const m = JSON.parse(e.nativeEvent.data) as { type: string; ok?: number; err?: number };
                if (m.type === 'fatal') setMode('plain');
                else if (m.type === 'tiles') {
                  if ((m.ok ?? 0) > 0) setMode('tiles');
                  else if ((m.err ?? 0) >= 4) setMode('plain');
                }
              } catch {
                // not ours
              }
            }}
          />
        )}
      </View>
      {mode === 'plain' ? (
        <AppText variant="caption" color={colors.muted}>
          Map tiles are not available right now, so this shows positions only.
        </AppText>
      ) : null}
      <OsmCredit />
    </View>
  );
}

/** Positions only: the restaurant, the delivery point and the rider as labelled dots on a plain background. */
export function PlainMap({ from, to, rider }: Props) {
  const [size, setSize] = useState({ w: 0, h: HEIGHT });
  const pts = [from, to, ...(rider ? [rider] : [])];
  const xy = size.w > 0 ? projectPoints(pts, size.w, size.h) : [];
  const dots = [
    { label: 'Restaurant', color: colors.butter },
    { label: 'You', color: colors.sky },
    ...(rider ? [{ label: 'Rider', color: colors.accent }] : []),
  ];
  const sides = xy.length ? placeLabels(xy, dots.map((d) => d.label)) : [];
  return (
    <View style={{ flex: 1 }} onLayout={(e) => setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })} accessible accessibilityLabel={`Positions: ${dots.map((d) => d.label).join(', ')}`}>
      {sides.map((side, i) => {
        const r = labelRect(side, xy[i], dots[i].label);
        return (
          <View key={dots[i].label} pointerEvents="none" style={{ position: 'absolute', left: 0, top: 0, right: 0, bottom: 0 }}>
            <View style={{ position: 'absolute', left: xy[i].x - 11, top: xy[i].y - 11, width: 22, height: 22, borderRadius: 11, backgroundColor: dots[i].color, borderWidth: 3, borderColor: colors.navy }} />
            <AppText variant="caption" weight={700} maxFontSizeMultiplier={1.3} style={{ position: 'absolute', left: r.left, top: r.top, width: r.width, height: r.height, textAlign: 'center' }} numberOfLines={1}>
              {dots[i].label}
            </AppText>
          </View>
        );
      })}
    </View>
  );
}
