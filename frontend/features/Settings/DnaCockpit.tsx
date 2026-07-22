/**
 * DnaCockpit — collapsible "100-slider" cockpit reusable across Jeeves /
 * Academy / Builder settings.
 *
 *   <DnaCockpit
 *     title="Jeeves Mastery"
 *     groups={JEEVES_DNA_GROUPS}
 *     dna={jeeves.masteryDna}
 *     onChange={(key, v) => setJeevesDna(key, v)}
 *     onResetGroup={resetJeevesDnaGroup}
 *     onResetAll={resetJeevesDna}
 *     accent="#a78bfa"
 *     // optional — when set, surfaces a "Preview prompt" button that
 *     // posts the current cockpit to the backend /dna/preview endpoint.
 *     previewEndpoint="/api/code-to-app/dna/preview"
 *     // optional — preset chips that bulk-apply named slider profiles.
 *     presets={{ 'Security-first': v => ({ ...v, bdr_web_security_authn: 2.5 }) }}
 *   />
 *
 *   • Renders nothing inside a group until the user expands it → cheap mount.
 *   • Long-press on a slider row resets just that slider to its 1.0 default.
 *   • "In prompt" pill appears on sliders that deviate from default so
 *     users can see which knobs will actually reach the LLM.
 */
import React, { useMemo, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  Platform, LayoutAnimation, UIManager, ScrollView, Modal,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DnaGroup } from '../../state/narrativeDnaData';
import { SliderRow } from '../Settings/components';
import { actionSheet } from '../../components/ActionSheet';
import { toast } from '../../components/Toast';
import { isReduceMotionOn } from '../../utils/haptics';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

/** Threshold below which a slider is "at default" (matches backend EPSILON). */
const DRIFT_EPS = 0.05;
const DEFAULT_VALUE = 1.0;

type PresetFn = (current: Record<string, number>) => Record<string, number>;

interface Props {
  title: string;
  groups: DnaGroup[];
  dna: Record<string, number>;
  onChange: (key: string, value: number) => void;
  onResetGroup: (groupId: string) => void;
  onResetAll: () => void;
  accent?: string;
  /** When set, enables the "Preview prompt" button — POST current dna here. */
  previewEndpoint?: string;
  /** Named preset chips. Each fn receives the current map and returns a new one. */
  presets?: Record<string, PresetFn>;
}

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function DnaCockpit({
  title, groups, dna, onChange, onResetGroup, onResetAll, accent = '#a78bfa',
  previewEndpoint, presets,
}: Props) {
  const [search, setSearch] = useState('');
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<{
    directives: string;
    stats: { received_keys: number; dropped_keys: number; drift: number; at_default: number };
    limits: { max_keys: number; value_range: [number, number]; default_value: number; max_prompt_chars: number };
  } | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  const total = useMemo(() => groups.reduce((n, g) => n + g.items.length, 0), [groups]);
  const drift = useMemo(() => {
    let n = 0;
    for (const g of groups) for (const it of g.items) {
      const v = dna[it[0]];
      if (typeof v === 'number' && Math.abs(v - DEFAULT_VALUE) >= DRIFT_EPS) n += 1;
    }
    return n;
  }, [groups, dna]);

  const q = search.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!q) return groups;
    return groups
      .map(grp => ({
        ...grp,
        items: grp.items.filter(([key, label, hint]) =>
          key.toLowerCase().includes(q) ||
          label.toLowerCase().includes(q) ||
          (hint || '').toLowerCase().includes(q)
        ),
      }))
      .filter(grp => grp.items.length > 0);
  }, [groups, q]);

  /** Auto-expand groups whose contents match the active search. */
  const effectiveOpenIds = useMemo(() => {
    if (!q) return openIds;
    return new Set(filtered.map(g => g.id));
  }, [q, openIds, filtered]);

  const toggle = useCallback((id: string) => {
    if (!isReduceMotionOn()) {
      LayoutAnimation.configureNext(
        LayoutAnimation.create(180, LayoutAnimation.Types.easeInEaseOut, LayoutAnimation.Properties.opacity),
      );
    }
    setOpenIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const onResetAllPress = () => {
    if (drift === 0) { toast.info('All sliders are at defaults'); return; }
    actionSheet.show({
      title: `Reset ${title}?`,
      message: `${drift} slider${drift === 1 ? '' : 's'} will revert to 1.0.`,
      options: [
        { label: `Reset ${drift}`, kind: 'destructive', onPress: () => { onResetAll(); toast.success(`${title} reset`); } },
        { label: 'Cancel', kind: 'cancel' },
      ],
    });
  };
  const onResetGroupPress = (g: DnaGroup) => {
    const groupDrift = g.items.filter(([k]) => Math.abs((dna[k] ?? 1) - 1) >= DRIFT_EPS).length;
    if (groupDrift === 0) { toast.info(`${g.title} at defaults`); return; }
    actionSheet.show({
      title: `Reset ${g.title}?`,
      message: `${groupDrift} slider${groupDrift === 1 ? '' : 's'} in this group will revert to 1.0.`,
      options: [
        { label: 'Reset group', kind: 'destructive', onPress: () => { onResetGroup(g.id); toast.success(`${g.title} reset`); } },
        { label: 'Cancel', kind: 'cancel' },
      ],
    });
  };

  /** Long-press a row → reset that single slider to default. */
  const onSliderLongPress = useCallback((key: string, label: string) => {
    if (Math.abs((dna[key] ?? DEFAULT_VALUE) - DEFAULT_VALUE) < DRIFT_EPS) {
      toast.info(`${label} already at default`);
      return;
    }
    actionSheet.show({
      title: label,
      message: `Reset to ${DEFAULT_VALUE.toFixed(1)}× (default)?`,
      options: [
        { label: 'Reset', kind: 'primary', onPress: () => { onChange(key, DEFAULT_VALUE); toast.success(`${label} reset`); } },
        { label: 'Cancel', kind: 'cancel' },
      ],
    });
  }, [dna, onChange]);

  const applyPreset = useCallback((name: string, fn: PresetFn) => {
    actionSheet.show({
      title: `Apply preset "${name}"?`,
      message: 'This overwrites slider values that the preset touches. Other sliders keep their current value.',
      options: [
        {
          label: 'Apply',
          kind: 'primary',
          onPress: () => {
            const next = fn({ ...dna });
            let changed = 0;
            for (const k of Object.keys(next)) {
              if (next[k] !== dna[k]) {
                onChange(k, next[k]);
                changed += 1;
              }
            }
            toast.success(`Preset "${name}" — ${changed} slider${changed === 1 ? '' : 's'} updated`);
          },
        },
        { label: 'Cancel', kind: 'cancel' },
      ],
    });
  }, [dna, onChange]);

  /** Fetch the LLM-bound directive block from the backend. */
  const openPreview = useCallback(async () => {
    if (!previewEndpoint) return;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewErr(null);
    setPreviewData(null);
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 8000);
      const res = await fetch(`${BACKEND}${previewEndpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ builder_dna: dna }),
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      setPreviewData(j);
    } catch (e: any) {
      setPreviewErr(e?.name === 'AbortError' ? 'Preview timed out' : (e?.message || String(e)));
    } finally {
      setPreviewLoading(false);
    }
  }, [previewEndpoint, dna]);

  return (
    <View style={s.wrap}>
      <View style={s.headerRow}>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { color: accent }]}>{title} Cockpit</Text>
          <Text style={s.sub}>
            {total} sliders · {drift > 0 ? `${drift} modified` : 'all at defaults'}
          </Text>
        </View>
        {previewEndpoint ? (
          <TouchableOpacity onPress={openPreview} style={[s.previewBtn, { borderColor: accent + '55', backgroundColor: accent + '22' }]} hitSlop={10}>
            <Ionicons name="eye" size={12} color={accent} />
            <Text style={[s.previewTxt, { color: accent }]}>Preview</Text>
          </TouchableOpacity>
        ) : null}
        <TouchableOpacity onPress={onResetAllPress} style={[s.resetBtn, drift === 0 && { opacity: 0.4 }]} hitSlop={10}>
          <Ionicons name="refresh" size={12} color="#fbbf24" />
          <Text style={s.resetTxt}>Reset</Text>
        </TouchableOpacity>
      </View>

      {presets && Object.keys(presets).length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.presetsBar} contentContainerStyle={{ gap: 6, paddingHorizontal: 4 }}>
          {Object.entries(presets).map(([name, fn]) => (
            <TouchableOpacity key={name} onPress={() => applyPreset(name, fn)} style={[s.presetChip, { borderColor: accent + '55' }]} hitSlop={8}>
              <Ionicons name="sparkles" size={10} color={accent} />
              <Text style={[s.presetTxt, { color: accent }]}>{name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}

      <View style={s.searchWrap}>
        <Ionicons name="search" size={14} color="#64748b" />
        <TextInput
          style={s.searchInput}
          value={search}
          onChangeText={setSearch}
          placeholder="Search sliders…"
          placeholderTextColor="#475569"
          autoCorrect={false}
          autoCapitalize="none"
        />
        {search ? (
          <TouchableOpacity onPress={() => setSearch('')}><Ionicons name="close-circle" size={14} color="#475569" /></TouchableOpacity>
        ) : null}
      </View>

      {filtered.map(g => {
        const open = effectiveOpenIds.has(g.id);
        const groupDrift = g.items.filter(([k]) => Math.abs((dna[k] ?? 1) - 1) >= DRIFT_EPS).length;
        return (
          <View key={g.id} style={s.group}>
            <TouchableOpacity style={s.groupHead} onPress={() => toggle(g.id)} onLongPress={() => onResetGroupPress(g)} delayLongPress={400}>
              <View style={[s.gIcon, { backgroundColor: g.color + '22', borderColor: g.color }]}>
                <Ionicons name={g.icon as any} size={14} color={g.color} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.gTitle}>{g.title}</Text>
                <Text style={s.gHint} numberOfLines={1}>
                  {g.items.length} sliders{groupDrift > 0 ? ` · ${groupDrift} modified` : ''} · {g.hint}
                </Text>
              </View>
              <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color="#64748b" />
            </TouchableOpacity>
            {open && (
              <View style={s.groupBody}>
                {g.items.map(([key, label, hint]) => {
                  const v = dna[key] ?? DEFAULT_VALUE;
                  const inPrompt = Math.abs(v - DEFAULT_VALUE) >= DRIFT_EPS;
                  return (
                    <TouchableOpacity
                      key={key}
                      activeOpacity={1}
                      onLongPress={() => onSliderLongPress(key, label)}
                      delayLongPress={400}
                      style={[s.sliderWrap, inPrompt && { borderLeftWidth: 2, borderLeftColor: g.color }]}
                    >
                      <SliderRow
                        color={g.color}
                        label={inPrompt ? `${label}  ✦` : label}
                        hint={hint}
                        value={v}
                        onChange={(nv) => onChange(key, nv)}
                        min={0} max={3} step={0.1}
                        valueLabel={`${v.toFixed(2)}×${inPrompt ? '  · in prompt' : ''}`}
                      />
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
          </View>
        );
      })}

      {q && filtered.length === 0 && (
        <Text style={s.empty}>No sliders match &quot;{search}&quot;</Text>
      )}

      {/* ── Live prompt-directive preview ─────────────────────────────── */}
      <Modal visible={previewOpen} transparent animationType="slide" onRequestClose={() => setPreviewOpen(false)}>
        <View style={s.modalBackdrop}>
          <View style={s.modalCard}>
            <View style={s.modalHeader}>
              <Ionicons name="eye" size={16} color={accent} />
              <Text style={[s.modalTitle, { color: accent }]}>Prompt preview</Text>
              <TouchableOpacity onPress={() => setPreviewOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={20} color="#94a3b8" />
              </TouchableOpacity>
            </View>
            {previewLoading ? (
              <View style={{ padding: 22, alignItems: 'center' }}>
                <ActivityIndicator size="small" color={accent} />
                <Text style={s.dim}>Asking backend what the LLM would see…</Text>
              </View>
            ) : previewErr ? (
              <View style={{ padding: 16 }}>
                <Text style={s.err}>⚠ {previewErr}</Text>
                <TouchableOpacity onPress={openPreview} style={[s.retryBtn, { borderColor: accent + '55' }]}>
                  <Ionicons name="refresh" size={12} color={accent} />
                  <Text style={[s.retryTxt, { color: accent }]}>Retry</Text>
                </TouchableOpacity>
              </View>
            ) : previewData ? (
              <ScrollView style={{ maxHeight: 480 }} contentContainerStyle={{ padding: 14 }}>
                <View style={s.statRow}>
                  <View style={s.statPill}><Text style={s.statN}>{previewData.stats.received_keys}</Text><Text style={s.statL}>received</Text></View>
                  <View style={s.statPill}><Text style={s.statN}>{previewData.stats.drift}</Text><Text style={s.statL}>drift</Text></View>
                  <View style={s.statPill}><Text style={s.statN}>{previewData.stats.at_default}</Text><Text style={s.statL}>at default</Text></View>
                  <View style={s.statPill}><Text style={s.statN}>{previewData.stats.dropped_keys}</Text><Text style={s.statL}>dropped</Text></View>
                </View>
                {previewData.directives ? (
                  <View style={s.codeBlock}>
                    <Text style={s.codeTxt} selectable>{previewData.directives}</Text>
                  </View>
                ) : (
                  <Text style={s.dim}>No directives — all sliders at default, so the LLM gets no extra prompt section.</Text>
                )}
                <Text style={s.limits} numberOfLines={2}>
                  Limits — max {previewData.limits.max_keys} keys · value ∈ [{previewData.limits.value_range.join(', ')}] · prompt cap {previewData.limits.max_prompt_chars} chars
                </Text>
              </ScrollView>
            ) : null}
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  wrap:      { backgroundColor: '#0F172A', borderRadius: 12, padding: 12, marginHorizontal: 12, marginTop: 12, borderWidth: 1, borderColor: '#1e293b' },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  title:     { fontSize: 14, fontWeight: '900', letterSpacing: 0.4 },
  sub:       { color: '#64748b', fontSize: 11, marginTop: 2 },
  previewBtn:{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1 },
  previewTxt:{ fontSize: 10, fontWeight: '800' },
  resetBtn:  { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#fbbf2422', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: '#fbbf2444' },
  resetTxt:  { color: '#fbbf24', fontSize: 10, fontWeight: '800' },

  presetsBar:{ marginBottom: 8 },
  presetChip:{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1, backgroundColor: '#020617' },
  presetTxt: { fontSize: 10, fontWeight: '700' },

  searchWrap:{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, height: 34, borderRadius: 8, backgroundColor: '#020617', borderWidth: 1, borderColor: '#1e293b', marginBottom: 10 },
  searchInput:{ flex: 1, color: '#e2e8f0', fontSize: 12 },

  group:     { backgroundColor: '#020617', borderRadius: 10, marginBottom: 8, borderWidth: 1, borderColor: '#1e293b', overflow: 'hidden' },
  groupHead: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10 },
  gIcon:     { width: 24, height: 24, borderRadius: 6, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  gTitle:    { color: '#e2e8f0', fontSize: 13, fontWeight: '700' },
  gHint:     { color: '#64748b', fontSize: 10, marginTop: 1 },
  groupBody: { padding: 6 },
  sliderWrap:{ borderLeftWidth: 0, borderLeftColor: 'transparent', paddingLeft: 0 },

  empty:     { color: '#64748b', fontSize: 12, textAlign: 'center', padding: 16, fontStyle: 'italic' },

  modalBackdrop:{ flex: 1, backgroundColor: '#00000099', justifyContent: 'flex-end' },
  modalCard:    { backgroundColor: '#0a0f1f', borderTopLeftRadius: 16, borderTopRightRadius: 16, borderWidth: 1, borderColor: '#1e293b', maxHeight: '85%' },
  modalHeader:  { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  modalTitle:   { fontSize: 14, fontWeight: '800', flex: 1, letterSpacing: 0.4 },

  statRow:   { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  statPill:  { backgroundColor: '#0f172a', borderRadius: 10, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: '#1e293b', alignItems: 'center' },
  statN:     { color: '#e2e8f0', fontSize: 16, fontWeight: '800' },
  statL:     { color: '#64748b', fontSize: 9, marginTop: 1, letterSpacing: 0.6, textTransform: 'uppercase' },

  codeBlock: { backgroundColor: '#020617', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#1e293b' },
  codeTxt:   { color: '#cbd5e1', fontSize: 12, lineHeight: 18, fontFamily: 'monospace' },
  dim:       { color: '#64748b', fontSize: 12, marginTop: 8, textAlign: 'center', lineHeight: 17 },
  limits:    { color: '#475569', fontSize: 10, marginTop: 10, fontStyle: 'italic', textAlign: 'center' },
  err:       { color: '#f87171', fontSize: 12, marginBottom: 8 },
  retryBtn:  { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  retryTxt:  { fontSize: 11, fontWeight: '800' },
});
