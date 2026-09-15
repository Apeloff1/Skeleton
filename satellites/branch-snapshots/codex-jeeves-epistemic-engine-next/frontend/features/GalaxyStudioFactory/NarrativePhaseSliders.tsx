/**
 * NarrativePhaseSliders — generic component that renders an arbitrary list
 * of "narrative phases" (Prelude, Tutorial, Climax, Coda …) each with the
 * same 5 sub-axes: count · complexity · intricacy · secrets · diversity.
 *
 * Used inside the Galaxy Studio Build questionnaire so the agent receives
 * a tightly-shaped tensor of narrative dials instead of bespoke state for
 * every phase. Keeps the questionnaire scalable from 5 → 40 → 100 phases
 * without exploding the component file.
 */
import React, { useState, useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import Slider from '@react-native-community/slider';
import { Ionicons } from '@expo/vector-icons';

export type NarrativeAxis = 'count' | 'complexity' | 'intricacy' | 'secrets' | 'diversity';
export const AXES: NarrativeAxis[] = ['count','complexity','intricacy','secrets','diversity'];

export type PhaseValues = Partial<Record<NarrativeAxis, number>>;
export type AllPhaseValues = Record<string, PhaseValues>;

export const NARRATIVE_PHASES: { id: string; label: string; emoji: string; group: string }[] = [
  // ─── On-ramp ───────────────────────────────────────────────
  { id: 'foreword',          label: 'Foreword',          emoji: '📜', group: 'On-Ramp' },
  { id: 'proem',             label: 'Proem',             emoji: '🌅', group: 'On-Ramp' },
  { id: 'preamble',          label: 'Preamble',          emoji: '📖', group: 'On-Ramp' },
  { id: 'prelude',           label: 'Prelude',           emoji: '🎼', group: 'On-Ramp' },
  { id: 'prologue',          label: 'Prologue',          emoji: '🔱', group: 'On-Ramp' },
  { id: 'introduction',      label: 'Introduction',      emoji: '🚪', group: 'On-Ramp' },
  { id: 'overview',          label: 'Overview',          emoji: '🗺️', group: 'On-Ramp' },
  { id: 'contextualization', label: 'Contextualization', emoji: '🧭', group: 'On-Ramp' },
  { id: 'framework',         label: 'Framework',         emoji: '🏗️', group: 'On-Ramp' },
  { id: 'orientation',       label: 'Orientation',       emoji: '🧠', group: 'On-Ramp' },
  { id: 'onboarding',        label: 'Onboarding',        emoji: '🎒', group: 'On-Ramp' },
  { id: 'tutorial',          label: 'Tutorial',          emoji: '🎓', group: 'On-Ramp' },
  { id: 'familiarization',   label: 'Familiarization',   emoji: '🤝', group: 'On-Ramp' },
  { id: 'acclimation',       label: 'Acclimation',       emoji: '🌡️', group: 'On-Ramp' },
  { id: 'incubation',        label: 'Incubation',        emoji: '🥚', group: 'On-Ramp' },
  { id: 'calibration',       label: 'Calibration',       emoji: '🎚️', group: 'On-Ramp' },
  { id: 'induction',         label: 'Induction',         emoji: '⚡', group: 'On-Ramp' },
  { id: 'threshold',         label: 'Threshold',         emoji: '🚧', group: 'On-Ramp' },
  { id: 'initiation',        label: 'Initiation',        emoji: '🔥', group: 'On-Ramp' },
  { id: 'backstory',         label: 'Backstory',         emoji: '🌌', group: 'On-Ramp' },
  { id: 'premise',           label: 'Premise',           emoji: '🎯', group: 'On-Ramp' },
  { id: 'exposition',        label: 'Exposition',        emoji: '🪧', group: 'On-Ramp' },
  { id: 'genesis',           label: 'Genesis',           emoji: '🌱', group: 'On-Ramp' },
  // ─── Mid-arc ───────────────────────────────────────────────
  { id: 'development',       label: 'Development',       emoji: '📈', group: 'Mid-Arc' },
  { id: 'interlude',         label: 'Interlude',         emoji: '☕', group: 'Mid-Arc' },
  { id: 'transition',        label: 'Transition',        emoji: '🔄', group: 'Mid-Arc' },
  { id: 'act',               label: 'Act',               emoji: '🎭', group: 'Mid-Arc' },
  { id: 'climax',            label: 'Climax',            emoji: '💥', group: 'Mid-Arc' },
  // ─── Off-ramp ──────────────────────────────────────────────
  { id: 'denouement',        label: 'Denouement',        emoji: '🪡', group: 'Off-Ramp' },
  { id: 'epilogue',          label: 'Epilogue',          emoji: '📕', group: 'Off-Ramp' },
  { id: 'coda',              label: 'Coda',              emoji: '🎶', group: 'Off-Ramp' },
  { id: 'valediction',       label: 'Valediction',       emoji: '👋', group: 'Off-Ramp' },
  { id: 'aftermath',         label: 'Aftermath',         emoji: '🌫️', group: 'Off-Ramp' },
];

export const STRUCTURE_PHASES: { id: string; label: string; emoji: string }[] = [
  { id: 'chapter',     label: 'Chapter',      emoji: '📑' },
  { id: 'stage',       label: 'Stage',        emoji: '🎬' },
  { id: 'world_stage', label: 'World Stage',  emoji: '🌍' },
];

const T = {
  bg: '#0A0F1F', card: '#101728', border: '#1F2A44',
  text: '#E5E7EB', dim: '#94A3B8', muted: '#64748B',
  accent: '#7C9CFF',
};

export function defaultPhaseValues(): AllPhaseValues {
  const out: AllPhaseValues = {};
  [...NARRATIVE_PHASES, ...STRUCTURE_PHASES].forEach(p => {
    out[p.id] = { count: 1, complexity: 7, intricacy: 7, secrets: 5, diversity: 7 };
  });
  return out;
}

interface Props {
  values: AllPhaseValues;
  onChange: (next: AllPhaseValues) => void;
}

// eslint-disable-next-line react/display-name
export const NarrativePhaseSliders: React.FC<Props> = React.memo(({ values, onChange }) => {
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null);

  const groups = useMemo(() => {
    const g: Record<string, typeof NARRATIVE_PHASES> = { 'Structure': STRUCTURE_PHASES as any };
    NARRATIVE_PHASES.forEach(p => {
      g[p.group] = g[p.group] || [];
      g[p.group].push(p);
    });
    return g;
  }, []);

  const setAxis = useCallback((phaseId: string, axis: NarrativeAxis, v: number) => {
    onChange({ ...values, [phaseId]: { ...(values[phaseId] || {}), [axis]: Math.round(v) } });
  }, [values, onChange]);

  return (
    <View style={s.root}>
      <View style={s.headerRow}>
        <Ionicons name="layers" size={14} color={T.accent} />
        <Text style={s.headerText}>Narrative Phase Matrix · {NARRATIVE_PHASES.length + STRUCTURE_PHASES.length} phases × {AXES.length} axes</Text>
      </View>
      <Text style={s.hint}>Tap a group → tap a phase → tune its 5 axes. Defaults are SOTA-balanced.</Text>

      {Object.entries(groups).map(([groupName, phases]) => {
        const open = expandedGroup === groupName;
        return (
          <View key={groupName} style={s.groupCard}>
            <TouchableOpacity style={s.groupHeader} onPress={() => setExpandedGroup(open ? null : groupName)} activeOpacity={0.7}>
              <Text style={s.groupTitle}>{groupName} · {phases.length}</Text>
              <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color={T.dim} />
            </TouchableOpacity>
            {open && (
              <View style={s.phasesList}>
                {phases.map(p => {
                  const exp = expandedPhase === p.id;
                  const vals = values[p.id] || {};
                  return (
                    <View key={p.id} style={s.phaseRow}>
                      <TouchableOpacity style={s.phaseHeader} onPress={() => setExpandedPhase(exp ? null : p.id)} activeOpacity={0.7}>
                        <Text style={s.phaseEmoji}>{p.emoji}</Text>
                        <Text style={s.phaseLabel}>{p.label}</Text>
                        <View style={{ flex: 1 }} />
                        <Text style={s.phaseSummary}>
                          {AXES.map(a => `${a[0].toUpperCase()}${vals[a] ?? '-'}`).join(' ')}
                        </Text>
                        <Ionicons name={exp ? 'chevron-up' : 'chevron-down'} size={12} color={T.muted} />
                      </TouchableOpacity>
                      {exp && (
                        <View style={s.axesBox}>
                          {AXES.map(axis => (
                            <View key={axis} style={s.axisRow}>
                              <Text style={s.axisLabel}>{axis}</Text>
                              <Slider
                                value={vals[axis] ?? 7}
                                onValueChange={v => setAxis(p.id, axis, v)}
                                minimumValue={0}
                                maximumValue={axis === 'count' ? 50 : 10}
                                step={1}
                                minimumTrackTintColor={T.accent}
                                maximumTrackTintColor="#334155"
                                thumbTintColor={T.accent}
                                style={{ flex: 1, height: 28 }}
                              />
                              <Text style={s.axisValue}>{vals[axis] ?? 0}</Text>
                            </View>
                          ))}
                        </View>
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
  root: { backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 12, marginTop: 8 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  headerText: { color: T.accent, fontSize: 13, fontWeight: '700' },
  hint: { color: T.muted, fontSize: 11, lineHeight: 15, marginBottom: 8 },
  groupCard: { backgroundColor: T.bg, borderRadius: 10, borderWidth: 1, borderColor: T.border, marginBottom: 8, overflow: 'hidden' },
  groupHeader: { flexDirection: 'row', alignItems: 'center', padding: 10 },
  groupTitle: { color: T.text, fontSize: 12, fontWeight: '700', flex: 1 },
  phasesList: { borderTopWidth: 1, borderTopColor: T.border, paddingHorizontal: 6, paddingBottom: 6 },
  phaseRow: { backgroundColor: T.card, borderRadius: 8, padding: 6, marginTop: 6, borderWidth: 1, borderColor: T.border },
  phaseHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  phaseEmoji: { fontSize: 14 },
  phaseLabel: { color: T.text, fontSize: 12, fontWeight: '600' },
  phaseSummary: { color: T.muted, fontSize: 9, fontFamily: 'Menlo' },
  axesBox: { marginTop: 6, gap: 2, paddingHorizontal: 4 },
  axisRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  axisLabel: { color: T.dim, fontSize: 10, width: 70, textTransform: 'capitalize' },
  axisValue: { color: T.accent, fontSize: 10, width: 24, textAlign: 'right' },
});

export default NarrativePhaseSliders;
