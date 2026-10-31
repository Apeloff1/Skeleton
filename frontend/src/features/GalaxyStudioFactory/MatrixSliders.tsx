/**
 * MatrixSliders — 2026 SOTA generic matrix-of-phases component.
 *
 * One file → unlimited matrices. Drop in any MatrixConfig.
 *
 * 2026 spec:
 *   • All sliders start at 0
 *   • Standard scale 0..100
 *   • Output-impacting axes (impact='high'|'critical') scale 0..1000
 *   • "One at a time" focused editing — when a phase is opened, axes are
 *     navigated in a carousel (◀ / ▶) so the user concentrates on one dial
 *   • Quick presets: 0 · 25% · 50% · 75% · Max
 *   • Numeric input alongside slider for precise entry
 *   • Impact badge ("HIGH" / "CRITICAL") on output-affecting axes
 *   • Live percentage gauge + saturation-tinted thumb colour
 */
import React, { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, Platform,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { Ionicons } from '@expo/vector-icons';

export type AxisImpact = 'normal' | 'high' | 'critical';

export type Axis = {
  id: string;
  label: string;
  min?: number;
  max?: number;
  step?: number;
  default?: number;
  /** When set, displays an impact badge and applies the high-scale tint. */
  impact?: AxisImpact;
};

export type Phase = {
  id: string;
  label: string;
  emoji: string;
  group: string;
};

export type MatrixConfig = {
  id: string;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  accent: string;
  hint: string;
  axes: Axis[];
  phases: Phase[];
};

export type PhaseValues = Record<string, number>;
export type MatrixValues = Record<string, PhaseValues>;

const T = {
  bg: '#0A0F1F',
  card: '#101728',
  cardLift: '#162038',
  border: '#1F2A44',
  text: '#E5E7EB',
  dim: '#94A3B8',
  muted: '#64748B',
  hi: '#A78BFA',
  crit: '#F472B6',
};

export function defaultMatrixValues(cfg: MatrixConfig): MatrixValues {
  const out: MatrixValues = {};
  cfg.phases.forEach(p => {
    const inner: PhaseValues = {};
    cfg.axes.forEach(a => { inner[a.id] = a.default ?? 0; });
    out[p.id] = inner;
  });
  return out;
}

// ── Helpers ─────────────────────────────────────────────────────────
const clamp = (v: number, lo: number, hi: number) =>
  Math.max(lo, Math.min(hi, v));

const impactBadge = (impact: AxisImpact | undefined) => {
  if (impact === 'critical') return { label: 'CRITICAL', color: T.crit };
  if (impact === 'high')     return { label: 'HIGH',     color: T.hi };
  return null;
};

// ── One-at-a-time Axis Editor ────────────────────────────────────────
interface AxisEditorProps {
  axis: Axis;
  value: number;
  accent: string;
  onChange: (v: number) => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
  position?: { index: number; total: number };
}

// eslint-disable-next-line react/display-name
const AxisEditor: React.FC<AxisEditorProps> = React.memo(({
  axis, value, accent, onChange, onPrev, onNext, hasPrev, hasNext, position,
}) => {
  const min = axis.min ?? 0;
  const max = axis.max ?? 100;
  const step = axis.step ?? 1;
  const badge = impactBadge(axis.impact);
  const v = value ?? (axis.default ?? 0);
  const pct = max > min ? ((v - min) / (max - min)) * 100 : 0;
  const isMaxScale = max >= 1000;

  // Local text-input mirror for the numeric value (commit on blur/Enter)
  const [textVal, setTextVal] = useState(String(v));
  React.useEffect(() => { setTextVal(String(v)); }, [v]);

  const commitText = useCallback(() => {
    const n = parseInt(textVal, 10);
    if (Number.isFinite(n)) onChange(clamp(Math.round(n / step) * step, min, max));
    else setTextVal(String(v));
  }, [textVal, min, max, step, onChange, v]);

  const setPreset = (frac: number) =>
    onChange(Math.round((min + frac * (max - min)) / step) * step);

  return (
    <View style={[ed.root, { borderColor: accent + '55' }]}>
      {/* Header row with prev/next */}
      <View style={ed.headerRow}>
        <TouchableOpacity
          onPress={onPrev}
          disabled={!hasPrev}
          style={[ed.navBtn, !hasPrev && ed.navBtnDisabled]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Ionicons name="chevron-back" size={18} color={hasPrev ? accent : T.muted} />
        </TouchableOpacity>

        <View style={ed.labelWrap}>
          <Text style={[ed.axisLabel, { color: T.text }]} numberOfLines={1}>
            {axis.label}
          </Text>
          {position && (
            <Text style={ed.posText}>
              {position.index + 1} / {position.total}
            </Text>
          )}
        </View>

        <TouchableOpacity
          onPress={onNext}
          disabled={!hasNext}
          style={[ed.navBtn, !hasNext && ed.navBtnDisabled]}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Ionicons name="chevron-forward" size={18} color={hasNext ? accent : T.muted} />
        </TouchableOpacity>
      </View>

      {/* Value row: large number + impact badge */}
      <View style={ed.valueRow}>
        <TextInput
          value={textVal}
          onChangeText={setTextVal}
          onBlur={commitText}
          onSubmitEditing={commitText}
          keyboardType="numeric"
          selectTextOnFocus
          style={[ed.valueInput, { color: accent }]}
        />
        <View style={{ flex: 1 }}>
          <View style={ed.scaleRow}>
            <Text style={ed.scaleText}>0</Text>
            <Text style={[ed.scaleText, isMaxScale && { color: accent, fontWeight: '700' }]}>
              ⟶ {max}
            </Text>
          </View>
          <View style={ed.gaugeOuter}>
            <View style={[ed.gaugeFill, { width: `${pct}%`, backgroundColor: accent }]} />
          </View>
        </View>
        {badge && (
          <View style={[ed.badge, { backgroundColor: badge.color + '22', borderColor: badge.color }]}>
            <Ionicons
              name={axis.impact === 'critical' ? 'flame' : 'flash'}
              size={10}
              color={badge.color}
            />
            <Text style={[ed.badgeText, { color: badge.color }]}>{badge.label}</Text>
          </View>
        )}
      </View>

      {/* The big slider */}
      <Slider
        value={v}
        onValueChange={onChange}
        minimumValue={min}
        maximumValue={max}
        step={step}
        minimumTrackTintColor={accent}
        maximumTrackTintColor="#26334F"
        thumbTintColor={accent}
        style={ed.slider}
      />

      {/* Quick presets */}
      <View style={ed.presetRow}>
        {[
          { label: '0',   frac: 0     },
          { label: '25%', frac: 0.25  },
          { label: '50%', frac: 0.5   },
          { label: '75%', frac: 0.75  },
          { label: 'Max', frac: 1     },
        ].map(p => {
          const targetV = Math.round((min + p.frac * (max - min)) / step) * step;
          const active = Math.abs(v - targetV) < step / 2;
          return (
            <TouchableOpacity
              key={p.label}
              style={[ed.presetBtn, active && { backgroundColor: accent + '22', borderColor: accent }]}
              onPress={() => setPreset(p.frac)}
              activeOpacity={0.7}
            >
              <Text style={[ed.presetText, active && { color: accent, fontWeight: '700' }]}>
                {p.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
});

// ── Main Matrix Component ────────────────────────────────────────────
interface Props {
  config: MatrixConfig;
  values: MatrixValues;
  onChange: (next: MatrixValues) => void;
}

// eslint-disable-next-line react/display-name
export const MatrixSliders: React.FC<Props> = React.memo(({ config, values, onChange }) => {
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null);
  // Tracks which axis is currently focused inside an expanded phase
  const [axisIdxByPhase, setAxisIdxByPhase] = useState<Record<string, number>>({});

  const groups = useMemo(() => {
    const g: Record<string, Phase[]> = {};
    config.phases.forEach(p => {
      g[p.group] = g[p.group] || [];
      g[p.group].push(p);
    });
    return g;
  }, [config.phases]);

  const setAxis = useCallback((phaseId: string, axisId: string, v: number) => {
    onChange({
      ...values,
      [phaseId]: { ...(values[phaseId] || {}), [axisId]: Math.round(v) },
    });
  }, [values, onChange]);

  const totalCells = config.phases.length * config.axes.length;

  // Summary string for a phase (compact axis snapshot)
  const phaseSummary = useCallback((p: Phase) => {
    const vals = values[p.id] || {};
    return config.axes
      .map(a => `${a.label[0].toUpperCase()}${vals[a.id] ?? 0}`)
      .join(' · ');
  }, [config.axes, values]);

  return (
    <View style={[s.root, { borderColor: config.accent + '55' }]}>
      <View style={s.headerRow}>
        <Ionicons name={config.icon} size={14} color={config.accent} />
        <Text style={[s.headerText, { color: config.accent }]} numberOfLines={2}>
          {config.title} · {config.phases.length} phases × {config.axes.length} axes · {totalCells.toLocaleString()} dials
        </Text>
      </View>
      <Text style={s.hint}>{config.hint}</Text>

      {Object.entries(groups).map(([groupName, phases]) => {
        const open = expandedGroup === groupName;
        return (
          <View key={groupName} style={s.groupCard}>
            <TouchableOpacity
              style={s.groupHeader}
              onPress={() => setExpandedGroup(open ? null : groupName)}
              activeOpacity={0.7}
            >
              <Text style={s.groupTitle}>{groupName} · {phases.length}</Text>
              <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color={T.dim} />
            </TouchableOpacity>
            {open && (
              <View style={s.phasesList}>
                {phases.map(p => {
                  const exp = expandedPhase === p.id;
                  const axisIdx = clamp(axisIdxByPhase[p.id] ?? 0, 0, config.axes.length - 1);
                  const axis = config.axes[axisIdx];
                  const v = (values[p.id] || {})[axis.id] ?? (axis.default ?? 0);
                  return (
                    <View key={p.id} style={s.phaseRow}>
                      <TouchableOpacity
                        style={s.phaseHeader}
                        onPress={() => {
                          setExpandedPhase(exp ? null : p.id);
                          if (!exp) setAxisIdxByPhase(prev => ({ ...prev, [p.id]: 0 }));
                        }}
                        activeOpacity={0.7}
                      >
                        <Text style={s.phaseEmoji}>{p.emoji}</Text>
                        <Text style={s.phaseLabel}>{p.label}</Text>
                        <View style={{ flex: 1 }} />
                        <Text style={s.phaseSummary} numberOfLines={1}>
                          {phaseSummary(p)}
                        </Text>
                        <Ionicons name={exp ? 'chevron-up' : 'chevron-down'} size={12} color={T.muted} />
                      </TouchableOpacity>

                      {exp && (
                        <AxisEditor
                          axis={axis}
                          value={v}
                          accent={config.accent}
                          onChange={(nv) => setAxis(p.id, axis.id, nv)}
                          onPrev={() => setAxisIdxByPhase(prev => ({
                            ...prev,
                            [p.id]: clamp(axisIdx - 1, 0, config.axes.length - 1),
                          }))}
                          onNext={() => setAxisIdxByPhase(prev => ({
                            ...prev,
                            [p.id]: clamp(axisIdx + 1, 0, config.axes.length - 1),
                          }))}
                          hasPrev={axisIdx > 0}
                          hasNext={axisIdx < config.axes.length - 1}
                          position={{ index: axisIdx, total: config.axes.length }}
                        />
                      )}
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
});

const s = StyleSheet.create({
  root: { backgroundColor: T.card, borderRadius: 12, borderWidth: 1, padding: 12, marginTop: 8 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  headerText: { fontSize: 12, fontWeight: '700', flex: 1 },
  hint: { color: T.muted, fontSize: 11, lineHeight: 15, marginBottom: 8 },
  groupCard: { backgroundColor: T.bg, borderRadius: 10, borderWidth: 1, borderColor: T.border, marginBottom: 8, overflow: 'hidden' },
  groupHeader: { flexDirection: 'row', alignItems: 'center', padding: 10 },
  groupTitle: { color: T.text, fontSize: 12, fontWeight: '700', flex: 1 },
  phasesList: { borderTopWidth: 1, borderTopColor: T.border, paddingHorizontal: 6, paddingBottom: 6 },
  phaseRow: { backgroundColor: T.card, borderRadius: 8, padding: 6, marginTop: 6, borderWidth: 1, borderColor: T.border },
  phaseHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  phaseEmoji: { fontSize: 14 },
  phaseLabel: { color: T.text, fontSize: 12, fontWeight: '600' },
  phaseSummary: { color: T.muted, fontSize: 9, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', maxWidth: 180 },
});

const ed = StyleSheet.create({
  root: {
    marginTop: 8,
    paddingHorizontal: 8,
    paddingVertical: 10,
    backgroundColor: T.cardLift,
    borderRadius: 10,
    borderWidth: 1,
    gap: 8,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  navBtn: {
    width: 30, height: 30, borderRadius: 15,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#0c1426', borderWidth: 1, borderColor: T.border,
  },
  navBtnDisabled: { opacity: 0.3 },
  labelWrap: { flex: 1, alignItems: 'center', gap: 2 },
  axisLabel: { fontSize: 13, fontWeight: '700', textTransform: 'capitalize' },
  posText: { color: T.muted, fontSize: 9, letterSpacing: 1 },
  valueRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 4 },
  valueInput: {
    minWidth: 56, paddingVertical: 4, paddingHorizontal: 8,
    backgroundColor: '#0c1426', borderRadius: 8, borderWidth: 1, borderColor: T.border,
    fontSize: 18, fontWeight: '900', textAlign: 'center',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  scaleRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  scaleText: { color: T.muted, fontSize: 9, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  gaugeOuter: {
    height: 6, borderRadius: 3, backgroundColor: '#0c1426',
    borderWidth: 1, borderColor: T.border, overflow: 'hidden',
  },
  gaugeFill: { height: '100%', borderRadius: 3 },
  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    paddingHorizontal: 6, paddingVertical: 3, borderRadius: 8, borderWidth: 1,
  },
  badgeText: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  slider: { width: '100%', height: 38 },
  presetRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 4, paddingHorizontal: 2 },
  presetBtn: {
    flex: 1, paddingVertical: 5, paddingHorizontal: 2,
    borderRadius: 6, borderWidth: 1, borderColor: T.border,
    backgroundColor: '#0c1426', alignItems: 'center',
  },
  presetText: { color: T.dim, fontSize: 10, fontWeight: '600' },
});

export default MatrixSliders;
