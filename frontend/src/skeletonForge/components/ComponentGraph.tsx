/**
 * Live component graph for a vision composition.
 *
 * Nodes are real Views (crisp text, focusable, screen-reader friendly) laid
 * over an SVG edge layer. Each node shows the vision words that triggered
 * it; a provenance list underneath carries the same facts as text so the
 * graph is never the only channel.
 */
import React from 'react';
import { Animated, Platform, Pressable, ScrollView, StyleSheet, Text, View, type LayoutChangeEvent } from 'react-native';
import Svg, { Defs, Marker, Path, Text as SvgText } from 'react-native-svg';
import { describeComposition, explainComposition, featureMeta, layoutGraph } from '../graph';
import type { ComposeResult } from '../types';
import { C, TOUCH } from './theme';

export interface ComponentGraphProps {
  result: ComposeResult | null | undefined;
  /** Initial width before layout measures the container (SSR/tests). */
  initialWidth?: number;
  selected?: string | null;
  onSelect?: (instanceId: string | null) => void;
  /** Hide the provenance list (e.g. in compact embeds). */
  showProvenance?: boolean;
  testID?: string;
}

export default function ComponentGraph({ result, initialWidth = 360, selected = null, onSelect, showProvenance = true, testID }: ComponentGraphProps) {
  const [width, setWidth] = React.useState(initialWidth);
  const fade = React.useRef(new Animated.Value(1)).current;
  const key = result?.blueprint_id ?? (result?.features ?? []).join('+');

  React.useEffect(() => {
    fade.setValue(0.25);
    Animated.timing(fade, { toValue: 1, duration: 260, useNativeDriver: Platform.OS !== 'web' }).start();
  }, [key, fade]);

  const onLayout = React.useCallback((e: LayoutChangeEvent) => {
    const w = Math.round(e.nativeEvent.layout.width);
    if (w > 0 && Math.abs(w - width) > 4) setWidth(w);
  }, [width]);

  const layout = React.useMemo(() => layoutGraph(result?.components, result?.wires, { width }), [result, width]);
  const rows = React.useMemo(() => explainComposition(result), [result]);
  const rowById = React.useMemo(() => new Map(rows.map((r) => [r.instanceId, r])), [rows]);
  const summary = describeComposition(result);

  if (!result || !layout.nodes.length) {
    return (
      <View style={st.empty} onLayout={onLayout} testID={testID} accessibilityLabel={summary}>
        <Text style={st.emptyGlyph} importantForAccessibility="no">◎</Text>
        <Text style={st.emptyTxt}>Type a vision to see which systems it composes.</Text>
      </View>
    );
  }

  const active = selected ? new Set([selected, ...(rowById.get(selected)?.feeds ?? []), ...(rowById.get(selected)?.fedBy ?? [])]) : null;

  return (
    <View onLayout={onLayout} testID={testID}>
      <Text style={st.srOnly} accessibilityLiveRegion="polite">{summary}</Text>
      <Animated.View
        style={[st.canvas, { height: layout.height, opacity: fade }]}
        accessibilityLabel={`Component graph. ${summary}`}
      >
        <ScrollableCanvas width={layout.width} height={layout.height} viewport={width}>
          <Svg width={layout.width} height={layout.height} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
            <Defs>
              <Marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                <Path d="M0,0 L10,5 L0,10 z" fill={C.mute} />
              </Marker>
            </Defs>
            {layout.edges.map((e) => {
              const lit = !active || (active.has(e.from) && active.has(e.to) && (e.from === selected || e.to === selected));
              const color = featureMeta(rowById.get(e.to)?.feature).color;
              return (
                <React.Fragment key={e.id}>
                  <Path d={e.d} stroke={lit ? color : C.border} strokeWidth={lit ? 2.5 : 1.5} fill="none" markerEnd="url(#arrow)" opacity={lit ? 0.95 : 0.5} />
                  <SvgText x={e.labelX} y={e.labelY} fill={lit ? C.mute : C.dim} fontSize={10} textAnchor="middle">
                    {`${e.fromPort} → ${e.toPort}`}
                  </SvgText>
                </React.Fragment>
              );
            })}
          </Svg>
          {layout.nodes.map((n) => {
            const row = rowById.get(n.id);
            const meta = featureMeta(n.feature);
            const isSel = selected === n.id;
            const dimmed = active && !active.has(n.id);
            const trig = row?.triggers ?? [];
            const label = `${meta.label} system, component ${n.id} of kind ${n.kind}. ${
              n.feature === 'player' ? 'Always present.' : trig.length ? `Triggered by ${trig.join(', ')}.` : 'Added by the fallback loop.'
            }${n.wired ? '' : ' Not wired to other systems.'}${isSel ? ' Selected.' : ''}`;
            return (
              <Pressable
                key={n.id}
                testID={`graph-node-${n.id}`}
                onPress={onSelect ? () => onSelect(isSel ? null : n.id) : undefined}
                accessibilityRole="button"
                accessibilityLabel={label}
                accessibilityState={{ selected: isSel }}
                style={({ pressed }) => [
                  st.node,
                  { left: n.x, top: n.y, width: n.w, height: n.h, borderColor: isSel ? meta.color : C.borderStrong },
                  !n.wired && n.feature !== 'player' && st.unwired,
                  isSel && { backgroundColor: meta.color + '22' },
                  dimmed && st.dimmed,
                  pressed && st.pressed,
                ]}
              >
                <View style={[st.stripe, { backgroundColor: meta.color }]} />
                <View style={st.nodeBody}>
                  <Text style={st.nodeTitle} numberOfLines={1}>
                    <Text style={{ color: meta.color }}>{meta.glyph} </Text>
                    {meta.label}
                  </Text>
                  <Text style={st.nodeSub} numberOfLines={1}>
                    {n.feature === 'player' ? 'operator' : trig.length ? `“${trig.slice(0, 2).join('”, “')}”${trig.length > 2 ? ` +${trig.length - 2}` : ''}` : result.fallback ? 'fallback' : n.kind}
                  </Text>
                </View>
              </Pressable>
            );
          })}
        </ScrollableCanvas>
      </Animated.View>
      {result.fallback ? (
        <Text style={st.fallback} accessibilityRole="alert">
          No recognised systems in the vision — showing the canonical fallback loop. Try words like “craft”, “boss”, “storm” or “stash”.
        </Text>
      ) : null}
      {showProvenance ? <Provenance result={result} selected={selected} onSelect={onSelect} /> : null}
    </View>
  );
}

/** Horizontal scroll only when the graph is wider than the viewport. */
function ScrollableCanvas({ children, width, height, viewport }: { children: React.ReactNode; width: number; height: number; viewport: number }) {
  const inner = <View style={{ width, height }}>{children}</View>;
  if (width <= viewport + 1) return inner;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator accessibilityLabel="Scroll the graph horizontally">
      {inner}
    </ScrollView>
  );
}

export function Provenance({ result, selected, onSelect }: { result: ComposeResult; selected?: string | null; onSelect?: (id: string | null) => void }) {
  const rows = explainComposition(result).filter((r) => r.feature !== 'player');
  return (
    <View style={st.prov} accessibilityRole="list" accessibilityLabel="Why each system is here">
      {rows.map((r) => (
        <Pressable
          key={r.instanceId}
          testID={`prov-${r.instanceId}`}
          onPress={onSelect ? () => onSelect(selected === r.instanceId ? null : r.instanceId) : undefined}
          accessibilityRole="button"
          accessibilityState={{ selected: selected === r.instanceId }}
          accessibilityLabel={`${r.meta.label}: ${r.triggers.length ? `triggered by ${r.triggers.join(', ')}` : 'fallback'}; ${r.meta.blurb}${r.fedBy.length ? `; fed by ${r.fedBy.join(', ')}` : ''}`}
          style={[st.provRow, selected === r.instanceId && { borderColor: r.meta.color }]}
        >
          <Text style={[st.provGlyph, { color: r.meta.color }]} importantForAccessibility="no">{r.meta.glyph}</Text>
          <View style={st.provBody}>
            <Text style={st.provTitle}>
              {r.meta.label} <Text style={st.provKind}>{r.kind}</Text>
            </Text>
            <Text style={st.provBlurb}>{r.meta.blurb}</Text>
            <View style={st.trigRow}>
              {r.triggers.length ? (
                r.triggers.map((t) => (
                  <Text key={t} style={[st.trig, { borderColor: r.meta.color, color: r.meta.color }]}>{t}</Text>
                ))
              ) : (
                <Text style={st.provKind}>fallback — not from your words</Text>
              )}
              {r.fedBy.length ? <Text style={st.provKind}>  ← {r.fedBy.join(', ')}</Text> : null}
            </View>
          </View>
        </Pressable>
      ))}
    </View>
  );
}

const st = StyleSheet.create({
  canvas: { backgroundColor: C.cardAlt, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 36, backgroundColor: C.cardAlt, borderRadius: 12, borderWidth: 1, borderColor: C.border, borderStyle: 'dashed' },
  emptyGlyph: { color: C.dim, fontSize: 28, marginBottom: 6 },
  emptyTxt: { color: C.mute, fontSize: 13 },
  node: {
    position: 'absolute', flexDirection: 'row', backgroundColor: C.card, borderWidth: 1, borderRadius: 10, overflow: 'hidden',
    minHeight: TOUCH,
  },
  unwired: { borderStyle: 'dashed' },
  dimmed: { opacity: 0.35 },
  pressed: { opacity: 0.8 },
  stripe: { width: 4 },
  nodeBody: { flex: 1, paddingHorizontal: 8, paddingVertical: 6, justifyContent: 'center' },
  nodeTitle: { color: C.textStrong, fontWeight: '800', fontSize: 13 },
  nodeSub: { color: C.mute, fontSize: 11, marginTop: 2 },
  fallback: { color: C.amber, fontSize: 12, marginTop: 8 },
  prov: { marginTop: 10 },
  provRow: { flexDirection: 'row', borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, marginBottom: 6, minHeight: TOUCH, backgroundColor: C.card },
  provGlyph: { fontSize: 18, width: 26, textAlign: 'center' },
  provBody: { flex: 1 },
  provTitle: { color: C.textStrong, fontWeight: '700', fontSize: 13 },
  provKind: { color: C.dim, fontSize: 11, fontWeight: '500' },
  provBlurb: { color: C.mute, fontSize: 12, marginTop: 2 },
  trigRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', marginTop: 6, gap: 4 },
  trig: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 1, fontSize: 11, fontWeight: '700' },
  srOnly: { position: 'absolute', width: 1, height: 1, overflow: 'hidden', opacity: 0 },
});
