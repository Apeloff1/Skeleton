/**
 * Galaxy Studio — Production Studio Panel
 * Renders the new 0-100 production sections (Asset Quality, Audio, Platform,
 * Monetization, Live-ops, Accessibility, Save System, Network, Localization)
 * plus the expanded Style pickers (Art Direction, Tone, Narrative, Perspective).
 *
 * This component is a self-contained collapsible block that lives at the bottom
 * of the questionnaire. It produces a ProductionState object that the parent
 * spreads into the build payload as `extra_params.production`.
 */
import React, { useCallback, useState, memo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DeepSlider } from '../../components/DeepSlider';
import {
  PRODUCTION_SECTIONS,
  ART_DIRECTION_STYLES,
  GAME_TONE_STYLES,
  NARRATIVE_STRUCTURES,
  PERSPECTIVES,
  ProductionState,
  ProductionSection,
} from './productionSections';

import GLOBAL_THEME from '../../theme/tokens';

interface Props {
  state: ProductionState;
  onChange: (next: ProductionState) => void;
}

// eslint-disable-next-line react/display-name
export const ProductionStudioPanel: React.FC<Props> = memo(({ state, onChange }) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ asset_quality: true });
  const [stylesOpen, setStylesOpen] = useState(true);

  const toggle = useCallback((id: string) => {
    setExpanded((p) => ({ ...p, [id]: !p[id] }));
  }, []);

  const setSlider = useCallback((key: string, v: number) => {
    onChange({ ...state, sliders: { ...state.sliders, [key]: v } });
  }, [state, onChange]);

  const toggleArr = useCallback((field: 'platforms' | 'languages', value: string) => {
    const cur = state[field];
    const exists = cur.includes(value);
    const next = exists ? cur.filter(v => v !== value) : [...cur, value];
    onChange({ ...state, [field]: next });
  }, [state, onChange]);

  const renderSection = (sec: ProductionSection) => {
    const isOpen = !!expanded[sec.id];
    return (
      <View key={sec.id} style={s.section}>
        <TouchableOpacity activeOpacity={0.7} style={s.sectionHead} onPress={() => toggle(sec.id)}>
          <View style={[s.iconCircle, { backgroundColor: sec.color + '22' }]}>
            <Ionicons name={sec.icon as any} size={16} color={sec.color} />
          </View>
          <Text style={s.sectionTitle}>{sec.title}</Text>
          <View style={s.spacer} />
          <Ionicons name={isOpen ? 'chevron-up' : 'chevron-down'} size={18} color="#94A3B8" />
        </TouchableOpacity>
        {isOpen && (
          <View style={s.sectionBody}>
            {sec.kind === 'slider' && sec.params?.map(p => (
              <DeepSlider
                key={p.key}
                label={p.label}
                help={p.help}
                value={state.sliders[p.key] ?? 0}
                onChange={v => setSlider(p.key, v)}
                max={p.max ?? 100}
                color={sec.color}
              />
            ))}
            {sec.kind === 'multiSelect' && (
              <View style={s.chipWrap}>
                {sec.options?.map(o => {
                  const arr = sec.id === 'platform_targets' ? state.platforms : state.languages;
                  const active = arr.includes(o.value);
                  return (
                    <TouchableOpacity
                      key={o.value}
                      onPress={() => toggleArr(sec.id === 'platform_targets' ? 'platforms' : 'languages', o.value)}
                      style={[s.chip, active && { backgroundColor: sec.color + '22', borderColor: sec.color }]}
                    >
                      <Text style={[s.chipText, active && { color: sec.color }]}>{o.label}</Text>
                      {active && <Ionicons name="checkmark" size={12} color={sec.color} style={{ marginLeft: 4 }} />}
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
            {sec.kind === 'select' && (
              <View style={s.chipWrap}>
                {sec.options?.map(o => {
                  const field = sec.id === 'monetization' ? 'monetization' : sec.id === 'save_system' ? 'saveSystem' : 'networkMode';
                  const active = (state as any)[field] === o.value;
                  return (
                    <TouchableOpacity
                      key={o.value}
                      onPress={() => onChange({ ...state, [field]: o.value })}
                      style={[s.selectChip, active && { backgroundColor: sec.color + '22', borderColor: sec.color }]}
                    >
                      <Text style={[s.selectChipText, active && { color: sec.color }]}>{o.label}</Text>
                      {o.sub ? <Text style={s.selectChipSub}>{o.sub}</Text> : null}
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
          </View>
        )}
      </View>
    );
  };

  return (
    <View style={s.container}>
      <View style={s.heroBanner}>
        <Ionicons name="construct" size={18} color="#A855F7" />
        <Text style={s.heroTitle}>Production Studio</Text>
        <Text style={s.heroSub}>Deep 0-100 controls • {PRODUCTION_SECTIONS.length} sections</Text>
      </View>

      {/* Style pickers — Art Direction, Tone, Narrative, Perspective */}
      <View style={s.section}>
        <TouchableOpacity activeOpacity={0.7} style={s.sectionHead} onPress={() => setStylesOpen(v => !v)}>
          <View style={[s.iconCircle, { backgroundColor: '#F472B622' }]}>
            <Ionicons name="color-palette" size={16} color="#F472B6" />
          </View>
          <Text style={s.sectionTitle}>Art Direction &amp; Storytelling</Text>
          <View style={s.spacer} />
          <Ionicons name={stylesOpen ? 'chevron-up' : 'chevron-down'} size={18} color="#94A3B8" />
        </TouchableOpacity>
        {stylesOpen && (
          <View style={s.sectionBody}>
            <StyleScroller
              label="Art Direction"
              options={ART_DIRECTION_STYLES}
              value={state.artDirection}
              onChange={(v) => onChange({ ...state, artDirection: v })}
              color="#F472B6"
            />
            <StyleScroller
              label="Tone"
              options={GAME_TONE_STYLES}
              value={state.gameTone}
              onChange={(v) => onChange({ ...state, gameTone: v })}
              color="#FBBF24"
            />
            <StyleScroller
              label="Narrative Structure"
              options={NARRATIVE_STRUCTURES}
              value={state.narrativeStructure}
              onChange={(v) => onChange({ ...state, narrativeStructure: v })}
              color="#60A5FA"
            />
            <StyleScroller
              label="Camera Perspective"
              options={PERSPECTIVES}
              value={state.perspective}
              onChange={(v) => onChange({ ...state, perspective: v })}
              color="#34D399"
            />
          </View>
        )}
      </View>

      {PRODUCTION_SECTIONS.map(renderSection)}
    </View>
  );
});

interface StyleOption { value: string; label: string; sub?: string }
const StyleScroller: React.FC<{
  label: string; options: StyleOption[]; value: string; onChange: (v: string) => void; color: string;
}> = ({ label, options, value, onChange, color }) => (
  <View style={{ marginBottom: 14 }}>
    <Text style={s.styleLabel}>{label} <Text style={{ color: '#64748B' }}>· {options.length}</Text></Text>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
      {options.map(o => (
        <TouchableOpacity
          key={o.value}
          onPress={() => onChange(o.value)}
          style={[s.styleChip, value === o.value && { backgroundColor: color + '22', borderColor: color }]}
        >
          <Text style={[s.styleChipText, value === o.value && { color }]}>{o.label}</Text>
          {o.sub ? <Text style={s.styleChipSub}>{o.sub}</Text> : null}
        </TouchableOpacity>
      ))}
    </ScrollView>
  </View>
);

const s = StyleSheet.create({
  container: { marginTop: 16, marginBottom: 12 },
  heroBanner: { flexDirection: 'row', alignItems: 'center', backgroundColor: GLOBAL_THEME.colors.bgSubtle, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: GLOBAL_THEME.colors.primary + '44', marginBottom: 12, gap: 8 },
  heroTitle: { color: GLOBAL_THEME.colors.text, fontSize: 15, fontWeight: '800' },
  heroSub: { color: GLOBAL_THEME.palette.brand[400], fontSize: 11, marginLeft: 'auto' },
  section: { backgroundColor: GLOBAL_THEME.colors.bgSubtle, borderRadius: 10, borderWidth: 1, borderColor: GLOBAL_THEME.colors.border, marginBottom: 10, overflow: 'hidden' },
  sectionHead: { flexDirection: 'row', alignItems: 'center', padding: 12 },
  iconCircle: { width: 32, height: 32, borderRadius: 10, justifyContent: 'center', alignItems: 'center', marginRight: 10 },
  sectionTitle: { color: GLOBAL_THEME.colors.text, fontSize: 14, fontWeight: '700' },
  spacer: { flex: 1 },
  sectionBody: { padding: 12, borderTopWidth: 1, borderTopColor: GLOBAL_THEME.colors.border },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { flexDirection: 'row', alignItems: 'center', backgroundColor: GLOBAL_THEME.colors.bg, borderWidth: 1, borderColor: GLOBAL_THEME.colors.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, marginBottom: 6 },
  chipText: { color: GLOBAL_THEME.colors.textMuted, fontSize: 12, fontWeight: '600' },
  selectChip: { backgroundColor: GLOBAL_THEME.colors.bg, borderWidth: 1, borderColor: GLOBAL_THEME.colors.border, borderRadius: 8, padding: 10, marginBottom: 6, width: '48%' },
  selectChipText: { color: GLOBAL_THEME.colors.text, fontSize: 13, fontWeight: '700' },
  selectChipSub: { color: GLOBAL_THEME.colors.textMuted, fontSize: 10, marginTop: 2 },
  styleLabel: { color: GLOBAL_THEME.colors.textMuted, fontSize: 12, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  styleChip: { backgroundColor: GLOBAL_THEME.colors.bg, borderWidth: 1, borderColor: GLOBAL_THEME.colors.border, borderRadius: 10, padding: 10, marginRight: 8, minWidth: 110, maxWidth: 220 },
  styleChipText: { color: GLOBAL_THEME.colors.text, fontSize: 12, fontWeight: '700' },
  styleChipSub: { color: GLOBAL_THEME.colors.textDim, fontSize: 10, marginTop: 2 },
});

export default ProductionStudioPanel;
