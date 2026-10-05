/**
 * DeepSlider — Continuous 0..max horizontal slider with snap chips, a value pill,
 * and a human-readable label tier (Low/Med/High/Ultra/Max).
 *
 * Used by the new Galaxy Studio production sections (Asset Quality, Monetization,
 * Audio Production, etc.) where the user expects FINE-grained 0-100 control
 * instead of a chip row.
 */
import React, { useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, GestureResponderEvent, LayoutChangeEvent } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface Props {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  color?: string;
  icon?: any;
  help?: string;
  tierLabels?: string[]; // e.g. ['Off','Low','Med','High','Ultra','Max']
  unit?: string; // e.g. '%', 'fps'
}

const TIER_DEFAULT = ['Off', 'Minimal', 'Low', 'Medium', 'High', 'Very High', 'Ultra', 'Max'];

function tierFor(value: number, max: number, tiers: string[]): string {
  if (value <= 0) return tiers[0] || 'Off';
  const buckets = tiers.length - 1;
  const idx = Math.min(buckets, Math.max(1, Math.ceil((value / max) * buckets)));
  return tiers[idx];
}

// eslint-disable-next-line react/display-name
export const DeepSlider: React.FC<Props> = React.memo(({
  label, value, onChange,
  min = 0, max = 100, step = 1,
  color = '#3B82F6', icon, help, tierLabels = TIER_DEFAULT, unit = '',
}) => {
  const [trackWidth, setTrackWidth] = React.useState(0);
  const onLayout = useCallback((e: LayoutChangeEvent) => {
    setTrackWidth(e.nativeEvent.layout.width);
  }, []);

  const pct = useMemo(() => {
    if (max === min) return 0;
    return Math.max(0, Math.min(1, (value - min) / (max - min)));
  }, [value, min, max]);

  const handleTouch = useCallback((e: GestureResponderEvent) => {
    if (trackWidth <= 0) return;
    const x = e.nativeEvent.locationX;
    const ratio = Math.max(0, Math.min(1, x / trackWidth));
    let v = min + ratio * (max - min);
    v = Math.round(v / step) * step;
    onChange(v);
  }, [trackWidth, min, max, step, onChange]);

  const bump = useCallback((dir: 1 | -1) => {
    onChange(Math.max(min, Math.min(max, value + dir * (step * 5))));
  }, [value, min, max, step, onChange]);

  const tier = tierFor(value, max, tierLabels);

  return (
    <View style={styles.row}>
      <View style={styles.head}>
        {icon ? <Ionicons name={icon} size={14} color={color} style={{ marginRight: 6 }} /> : null}
        <Text style={styles.label}>{label}</Text>
        <View style={styles.spacer} />
        <View style={[styles.pill, { borderColor: color }]}>
          <Text style={[styles.pillText, { color }]}>{value}{unit}</Text>
        </View>
        <View style={[styles.tierPill, { backgroundColor: color + '20' }]}>
          <Text style={[styles.tierText, { color }]}>{tier}</Text>
        </View>
      </View>
      <View style={styles.trackRow}>
        <TouchableOpacity onPress={() => bump(-1)} style={styles.bumpBtn} hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}>
          <Ionicons name="remove" size={14} color="#94A3B8" />
        </TouchableOpacity>
        <View
          style={styles.track}
          onLayout={onLayout}
          onStartShouldSetResponder={() => true}
          onMoveShouldSetResponder={() => true}
          onResponderGrant={handleTouch}
          onResponderMove={handleTouch}
        >
          <View style={[styles.trackFill, { width: `${pct * 100}%`, backgroundColor: color }]} />
          <View style={[styles.thumb, { left: `${pct * 100}%`, borderColor: color, transform: [{ translateX: -10 }] }]} />
          {/* tick markers at 0, 25, 50, 75, 100 */}
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <View key={t} style={[styles.tick, { left: `${t * 100}%` }]} />
          ))}
        </View>
        <TouchableOpacity onPress={() => bump(1)} style={styles.bumpBtn} hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}>
          <Ionicons name="add" size={14} color="#94A3B8" />
        </TouchableOpacity>
      </View>
      {help ? <Text style={styles.help}>{help}</Text> : null}
    </View>
  );
});

const styles = StyleSheet.create({
  row: { marginBottom: 16 },
  head: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  label: { color: '#CBD5E1', fontSize: 13, fontWeight: '600' },
  spacer: { flex: 1 },
  pill: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, marginRight: 6 },
  pillText: { fontSize: 11, fontWeight: '800' },
  tierPill: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  tierText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.3, textTransform: 'uppercase' },
  trackRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  bumpBtn: { width: 26, height: 26, borderRadius: 6, backgroundColor: '#0F172A', borderWidth: 1, borderColor: '#334155', justifyContent: 'center', alignItems: 'center' },
  track: { flex: 1, height: 24, backgroundColor: '#0F172A', borderRadius: 12, borderWidth: 1, borderColor: '#334155', justifyContent: 'center', position: 'relative', overflow: 'hidden' },
  trackFill: { position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 12 },
  thumb: { position: 'absolute', width: 20, height: 20, top: 1, borderRadius: 10, borderWidth: 2, backgroundColor: '#F8FAFC' },
  tick: { position: 'absolute', top: 0, bottom: 0, width: 1, backgroundColor: '#1E293B' },
  help: { color: '#64748B', fontSize: 11, fontStyle: 'italic', marginTop: 4 },
});

export default DeepSlider;
