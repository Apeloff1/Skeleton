import { useMemo, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  TextInput, Platform, LayoutAnimation, UIManager,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import {
  useSettings, BATCH_LABELS, NARRATIVE_DNA_GROUPS, NARRATIVE_DNA_TOTAL,
  getPhaseWeightsPayload, getNarrativeDnaPayload, getNarrativeDnaDriftCount,
  DnaGroup,
} from '../../state/settingsStore';
import { Section, SliderRow, SwitchRow, ActionButton } from '../../features/Settings/components';
import { actionSheet } from '../../components/ActionSheet';
import { toast } from '../../components/Toast';

// Smooth height transitions for open/close (Android needs explicit enable).
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const C = {
  bg: '#141414', card: '#262626', border: '#404040',
  text: '#F8FAFC', muted: '#94A3B8', accent: '#3B82F6', danger: '#EF4444',
};

export default function GalaxyStudioSettings() {
  const router = useRouter();
  const g = useSettings(s => s.galaxyStudio);
  const set = useSettings(s => s.setGalaxyStudio);
  const setW = useSettings(s => s.setPhaseWeight);
  const setDna = useSettings(s => s.setNarrativeDna);
  const resetDnaGroup = useSettings(s => s.resetNarrativeDnaGroup);
  const resetDnaAll = useSettings(s => s.resetNarrativeDna);
  const reset = useSettings(s => s.resetGalaxyStudio);
  const [adminStatus, setAdminStatus] = useState<any>(null);
  const [adminLoading, setAdminLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());

  // Roughly estimated — ~800 files base per category × weight, plus floor pass
  const estimatedFileCount = Object.values(g.phaseWeights).reduce((sum, w) => sum + w * 800, 0) + 40000;

  // ── Search filters the visible sliders per group ──
  const trimmedSearch = search.trim().toLowerCase();
  const filteredGroups = useMemo(() => {
    if (!trimmedSearch) return NARRATIVE_DNA_GROUPS;
    return NARRATIVE_DNA_GROUPS.map(grp => ({
      ...grp,
      items: grp.items.filter(([key, label, hint]) =>
        key.toLowerCase().includes(trimmedSearch) ||
        label.toLowerCase().includes(trimmedSearch) ||
        hint.toLowerCase().includes(trimmedSearch)
      ),
    })).filter(grp => grp.items.length > 0);
  }, [trimmedSearch]);

  // When searching, auto-expand all matching groups for instant access.
  const effectiveOpenIds = useMemo(() => {
    if (!trimmedSearch) return openIds;
    return new Set(filteredGroups.map(g => g.id));
  }, [trimmedSearch, filteredGroups, openIds]);

  const toggleGroup = useCallback((id: string) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpenIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpenIds(new Set(NARRATIVE_DNA_GROUPS.map(g => g.id)));
  }, []);
  const collapseAll = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpenIds(new Set());
  }, []);

  const driftTotal = getNarrativeDnaDriftCount();

  function groupDrift(grp: DnaGroup): number {
    let n = 0;
    for (const [k] of grp.items) {
      const v = g.narrativeDNA[k];
      if (typeof v === 'number' && Math.abs(v - 1.0) > 0.001) n += 1;
    }
    return n;
  }

  async function clearZombies() {
    try {
      setAdminLoading(true);
      const res = await fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL || ''}/api/galaxy-studio/clear-zombies`, { method: 'POST' });
      const json = await res.json();
      toast.info(`Memory: ${json.summary.mem}\nMongo: ${json.summary.mongo}\nOrphan tasks: ${json.summary.orphan_tasks}`);
      await refreshAdmin();
    } catch (e: any) {
      toast.error(String(e?.message || e));
    } finally { setAdminLoading(false); }
  }

  async function refreshAdmin() {
    try {
      setAdminLoading(true);
      const res = await fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL || ''}/api/galaxy-studio/admin-status`);
      const json = await res.json();
      setAdminStatus(json);
    } catch (e: any) {
      toast.error(String(e?.message || e));
    } finally { setAdminLoading(false); }
  }

  function confirmReset() {
    actionSheet.show({
      title: 'Reset Galaxy Studio?',
      message: 'This wipes phase weights and all 500 Narrative DNA sliders back to defaults.',
      options: [
        { label: 'Cancel', kind: 'cancel' },
        { label: 'Reset everything', kind: 'destructive', onPress: () => { reset(); toast.warn('Galaxy Studio reset'); } },
      ],
    });
  }

  function confirmResetDnaAll() {
    actionSheet.show({
      title: 'Reset all 500 sliders?',
      message: `Currently ${driftTotal} slider${driftTotal === 1 ? '' : 's'} are non-default. Pull them all back to 1.0×.`,
      options: [
        { label: 'Cancel', kind: 'cancel' },
        { label: 'Reset Narrative DNA', kind: 'destructive', onPress: () => { resetDnaAll(); toast.warn('All 500 sliders reset to 1.0×'); } },
      ],
    });
  }

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.headerBtn}>
          <Ionicons name="arrow-back" size={24} color={C.text} />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Galaxy Studio</Text>
        <TouchableOpacity onPress={confirmReset} style={s.headerBtn}>
          <Ionicons name="refresh" size={22} color={C.danger} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 60 }} keyboardShouldPersistTaps="handled">

        {/* ── Build size estimate ─────────────────────────────────── */}
        <View style={s.estimateCard}>
          <Text style={s.estimateLabel}>ESTIMATED BUILD SIZE</Text>
          <Text style={s.estimateValue}>{Math.round(estimatedFileCount).toLocaleString()} files</Text>
          <Text style={s.estimateHint}>Based on phase weights + floor pass baseline</Text>
        </View>

        {/* ── Phase emphasis sliders ──────────────────────────────── */}
        <Section title="Phase emphasis sliders" hint="How much weight each batch category carries. 0× = skip entirely. 1× = default. 3× = triple the files. Settings are sent on every Start Build.">
          {Object.entries(BATCH_LABELS).map(([key, meta]) => {
            const k = key as keyof typeof g.phaseWeights;
            const v = g.phaseWeights[k];
            return (
              <View key={key} style={s.phaseRow}>
                <View style={[s.phaseIcon, { backgroundColor: meta.color + '22' }]}>
                  <Ionicons name={meta.icon as any} size={16} color={meta.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <SliderRow label={meta.label} hint={meta.hint} value={v} min={0} max={3} step={0.1}
                    valueLabel={v === 0 ? 'SKIP' : `${v.toFixed(1)}×`} color={meta.color}
                    onChange={(x) => setW(k, x)} />
                </View>
              </View>
            );
          })}
        </Section>

        {/* ── Narrative DNA Cockpit (500 sliders) ─────────────────── */}
        <View style={s.cockpitHeader}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="rocket" size={18} color="#8B5CF6" />
            <Text style={s.cockpitTitle}>NARRATIVE DNA COCKPIT</Text>
          </View>
          <View style={s.driftPillRow}>
            <View style={s.driftPill}>
              <Ionicons name="pulse" size={11} color="#8B5CF6" />
              <Text style={s.driftPillText}>{driftTotal} / {NARRATIVE_DNA_TOTAL} drifted</Text>
            </View>
          </View>
          <Text style={s.cockpitHint}>
            {NARRATIVE_DNA_TOTAL} sliders across {NARRATIVE_DNA_GROUPS.length} categories shape the story of every build.
            Push a slider to 0 to skip, 3× to saturate. Only non-default values are sent.
          </Text>

          {/* Search + controls */}
          <View style={s.searchRow}>
            <View style={s.searchBox}>
              <Ionicons name="search" size={16} color={C.muted} />
              <TextInput
                style={s.searchInput}
                placeholder="Search 500 sliders…"
                placeholderTextColor={C.muted}
                value={search}
                onChangeText={setSearch}
                autoCorrect={false}
                autoCapitalize="none"
              />
              {search ? (
                <TouchableOpacity onPress={() => setSearch('')} hitSlop={8}>
                  <Ionicons name="close-circle" size={18} color={C.muted} />
                </TouchableOpacity>
              ) : null}
            </View>
          </View>

          <View style={s.controlsRow}>
            <TouchableOpacity style={s.miniBtn} onPress={expandAll}>
              <Ionicons name="chevron-down" size={14} color={C.text} />
              <Text style={s.miniBtnText}>Expand all</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.miniBtn} onPress={collapseAll}>
              <Ionicons name="chevron-up" size={14} color={C.text} />
              <Text style={s.miniBtnText}>Collapse all</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[s.miniBtn, { backgroundColor: '#7F1D1D' }]}
              onPress={confirmResetDnaAll}
              disabled={driftTotal === 0}
            >
              <Ionicons name="refresh" size={14} color={C.text} />
              <Text style={s.miniBtnText}>Reset DNA ({driftTotal})</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Each group is collapsible. Sliders inside only mount when open. */}
        {filteredGroups.map(grp => {
          const isOpen = effectiveOpenIds.has(grp.id);
          const drift = groupDrift(grp);
          const showCount = grp.items.length;
          return (
            <View key={grp.id} style={s.groupCard}>
              <TouchableOpacity
                onPress={() => toggleGroup(grp.id)}
                style={s.groupHeader}
                activeOpacity={0.7}
              >
                <View style={[s.groupIcon, { backgroundColor: grp.color + '22' }]}>
                  <Ionicons name={grp.icon as any} size={18} color={grp.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.groupTitle}>{grp.title}</Text>
                  <Text style={s.groupSubtitle}>
                    {showCount} slider{showCount === 1 ? '' : 's'}
                    {drift > 0 ? ` · ${drift} drifted` : ''}
                  </Text>
                </View>
                {drift > 0 ? (
                  <View style={[s.groupDriftDot, { backgroundColor: grp.color }]}>
                    <Text style={s.groupDriftDotText}>{drift}</Text>
                  </View>
                ) : null}
                <Ionicons
                  name={isOpen ? 'chevron-up' : 'chevron-down'}
                  size={20}
                  color={C.muted}
                  style={{ marginLeft: 8 }}
                />
              </TouchableOpacity>

              {isOpen ? (
                <View style={s.groupBody}>
                  <Text style={s.groupHint}>{grp.hint}</Text>

                  {grp.items.map(([key, label, hint]) => {
                    const v = g.narrativeDNA[key] ?? 1.0;
                    const drifted = Math.abs(v - 1.0) > 0.001;
                    return (
                      <View key={key} style={[s.sliderItem, drifted && { borderLeftColor: grp.color, borderLeftWidth: 3 }]}>
                        <SliderRow
                          label={label}
                          hint={hint}
                          value={v}
                          min={0}
                          max={3}
                          step={0.1}
                          color={grp.color}
                          valueLabel={v === 0 ? 'SKIP' : `${v.toFixed(1)}×`}
                          onChange={(x) => setDna(key, x)}
                        />
                      </View>
                    );
                  })}

                  {drift > 0 ? (
                    <TouchableOpacity
                      style={[s.resetGroupBtn, { backgroundColor: grp.color + '22', borderColor: grp.color }]}
                      onPress={() => {
                        resetDnaGroup(grp.id);
                        toast.info(`${grp.title} reset to defaults`);
                      }}
                    >
                      <Ionicons name="refresh" size={14} color={grp.color} />
                      <Text style={[s.resetGroupBtnText, { color: grp.color }]}>
                        Reset {grp.title} ({drift})
                      </Text>
                    </TouchableOpacity>
                  ) : null}
                </View>
              ) : null}
            </View>
          );
        })}

        {trimmedSearch && filteredGroups.length === 0 ? (
          <View style={s.emptyState}>
            <Ionicons name="search-circle" size={48} color={C.muted} />
            <Text style={s.emptyStateText}>No sliders match &quot;{trimmedSearch}&quot;</Text>
            <TouchableOpacity onPress={() => setSearch('')} style={s.miniBtn}>
              <Text style={s.miniBtnText}>Clear search</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* ── Advanced ────────────────────────────────────────────── */}
        <Section title="Advanced">
          <SliderRow color="#3B82F6" label="Preferred file size" hint="Hard ceiling is 160 KB on backend. This is a UI preference."
            value={g.fileSizePreferenceKb} onChange={v => set({ fileSizePreferenceKb: Math.round(v) })} min={40} max={160} step={10} valueLabel={`${g.fileSizePreferenceKb} KB`} />
          <SliderRow color="#3B82F6" label="Auto-archive after" hint="Archive completed builds after N minutes"
            value={g.autoArchiveAfterMin} onChange={v => set({ autoArchiveAfterMin: Math.round(v) })} min={5} max={240} step={5} valueLabel={`${g.autoArchiveAfterMin}m`} />
          <SwitchRow icon="warning" color="#3B82F6" label="Confirm destructive actions" hint="Show sheet before cancel/delete/clear-zombies"
            value={g.confirmDestructive} onValueChange={v => set({ confirmDestructive: v })} />
        </Section>

        {/* ── Server admin ────────────────────────────────────────── */}
        <Section title="Server admin" hint="Clear orphaned 'zombie' builds left by pod restarts + inspect server state.">
          <View style={{ padding: 14, gap: 10 }}>
            <ActionButton icon="skull" label="Clear zombie builds" kind="danger" onPress={() => {
              if (!g.confirmDestructive) { clearZombies(); return; }
              actionSheet.show({
                title: 'Clear zombies?',
                message: 'Marks every "building" doc without a live runner as "lost" so they stop blocking new builds.',
                options: [
                  { label: 'Cancel', kind: 'cancel' },
                  { label: 'Clear zombies', kind: 'destructive', onPress: clearZombies },
                ],
              });
            }} />
            <ActionButton icon="pulse" label={adminLoading ? 'Loading…' : 'Refresh server status'} color="#3B82F6" onPress={refreshAdmin} />
            {adminStatus && (
              <View style={s.adminCard}>
                <Text style={s.adminRow}>RAM: {adminStatus.memory?.percent?.toFixed?.(0) ?? '?'}% ({adminStatus.memory?.available_gb ?? '?'} GB free)</Text>
                <Text style={s.adminRow}>Live runners: {adminStatus.live_runners?.length ?? 0}</Text>
                <Text style={s.adminRow}>Zombies: {adminStatus.zombie_builds?.length ?? 0}</Text>
                <Text style={s.adminRow}>Vault builds: {adminStatus.vault?.builds ?? 0} — {((adminStatus.vault?.disk_bytes ?? 0) / 1e9).toFixed(2)} GB on disk</Text>
              </View>
            )}
          </View>
        </Section>

        {/* ── Outbound payload preview ────────────────────────────── */}
        <View style={{ padding: 16, gap: 12 }}>
          <View style={s.payloadCard}>
            <Text style={s.payloadLabel}>phase_weights — sent every build</Text>
            <Text style={s.payloadText} selectable>{JSON.stringify(getPhaseWeightsPayload(), null, 2)}</Text>
          </View>
          <View style={s.payloadCard}>
            <Text style={s.payloadLabel}>narrative_dna — only drifted sliders ({driftTotal} keys)</Text>
            <Text style={s.payloadText} selectable>
              {driftTotal === 0
                ? '{}  // all sliders at default — server defaults will apply'
                : JSON.stringify(getNarrativeDnaPayload(), null, 2)}
            </Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: C.card, borderBottomWidth: 1, borderBottomColor: C.border },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 18, fontWeight: '700', color: C.text },
  estimateCard: { backgroundColor: C.card, margin: 16, padding: 16, borderRadius: 12, borderLeftWidth: 4, borderLeftColor: C.accent },
  estimateLabel: { color: C.muted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
  estimateValue: { color: C.text, fontSize: 28, fontWeight: '800', marginTop: 4 },
  estimateHint: { color: '#64748B', fontSize: 11, marginTop: 2 },
  phaseRow: { flexDirection: 'row', alignItems: 'flex-start', borderBottomWidth: 1, borderBottomColor: C.border },
  phaseIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', margin: 12 },

  // Cockpit
  cockpitHeader: { padding: 16, paddingTop: 12, gap: 8 },
  cockpitTitle: { color: C.text, fontSize: 13, fontWeight: '800', letterSpacing: 1.2 },
  cockpitHint: { color: C.muted, fontSize: 12, lineHeight: 17 },
  driftPillRow: { flexDirection: 'row', alignItems: 'center' },
  driftPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#8B5CF622', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: '#8B5CF644' },
  driftPillText: { color: '#8B5CF6', fontSize: 11, fontWeight: '700' },
  searchRow: { marginTop: 4 },
  searchBox: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#0B1222', borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: Platform.OS === 'ios' ? 10 : 4 },
  searchInput: { flex: 1, color: C.text, fontSize: 14, paddingVertical: Platform.OS === 'ios' ? 0 : 6 },
  controlsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  miniBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  miniBtnText: { color: C.text, fontSize: 12, fontWeight: '600' },

  // Group
  groupCard: { marginHorizontal: 16, marginBottom: 8, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' },
  groupHeader: { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 12 },
  groupIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  groupTitle: { color: C.text, fontSize: 15, fontWeight: '700' },
  groupSubtitle: { color: C.muted, fontSize: 11, marginTop: 2 },
  groupDriftDot: { minWidth: 22, height: 22, borderRadius: 11, paddingHorizontal: 6, justifyContent: 'center', alignItems: 'center' },
  groupDriftDotText: { color: '#0B1222', fontSize: 10, fontWeight: '800' },
  groupBody: { paddingHorizontal: 6, paddingBottom: 6, borderTopWidth: 1, borderTopColor: C.border, gap: 0 },
  groupHint: { color: C.muted, fontSize: 11, paddingHorizontal: 10, paddingTop: 10, fontStyle: 'italic' },
  sliderItem: { borderLeftWidth: 0, borderLeftColor: 'transparent' },
  resetGroupBtn: { marginHorizontal: 10, marginTop: 8, marginBottom: 6, paddingVertical: 10, borderRadius: 8, borderWidth: 1, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 6 },
  resetGroupBtnText: { fontSize: 12, fontWeight: '700' },

  // Empty state
  emptyState: { alignItems: 'center', padding: 40, gap: 12 },
  emptyStateText: { color: C.muted, fontSize: 14 },

  adminCard: { backgroundColor: '#0B1222', padding: 12, borderRadius: 8, borderWidth: 1, borderColor: C.border, marginTop: 4 },
  adminRow: { color: '#CBD5E1', fontSize: 12, paddingVertical: 2, fontFamily: 'Courier' },
  payloadCard: { backgroundColor: '#0B1222', padding: 12, borderRadius: 10, borderWidth: 1, borderColor: C.border },
  payloadLabel: { color: C.muted, fontSize: 11, fontWeight: '700', marginBottom: 6 },
  payloadText: { color: '#CBD5E1', fontSize: 11, fontFamily: 'Courier', lineHeight: 16 },
});
