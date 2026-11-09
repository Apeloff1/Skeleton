/**
 * /stages — THE STAGE PAGE (beginning of the build process).
 *
 * Lay out the game spine as an ordered list of STAGES picked from a large
 * hand-authored catalogue of distinct stage TYPES (boss, mini-boss, enhanced
 * mob, interlude, introduction, prelude, cutscene, theatric, drama scene, …).
 * Building a stage CREATES THE FIRST GAMEFILES for the build (quest / enemy /
 * cutscene / item / …) which are crosswired to the 14-gate refinement engine.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet,
  TextInput, RefreshControl, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/utils/apiClient';

const C = {
  bg: '#0b0f1a', card: '#141b2e', alt: '#1b2438', border: '#2a3550',
  text: '#eef2fb', muted: '#8a96b2', accent: '#3B82F6', accent2: '#A78BFA',
  green: '#34D399', amber: '#F59E0B', red: '#f87171',
};

const DIFF_COLOR: Record<string, string> = {
  trivial: '#64748b', easy: '#34D399', normal: '#3B82F6',
  hard: '#F59E0B', extreme: '#f87171',
};

type StageType = {
  key: string; label: string; icon: string; category: string; role: string;
  combat: boolean; intensity: number; difficulty: string; summary: string;
  gens: string[];
};
type Group = { category: string; label: string; icon: string; count: number; types: StageType[] };
type Stage = {
  id: string; seq: number; type: string; label: string; icon: string;
  category: string; difficulty: string; intensity: number; combat: boolean;
  title: string; note?: string; built: boolean; gamefile_count: number;
};

export default function Stages() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const [buildId, setBuildId] = React.useState(params?.game ? String(params.game) : 'demo_build');

  const [groups, setGroups] = React.useState<Group[]>([]);
  const [maxStages, setMaxStages] = React.useState(100000);
  const [totalTypes, setTotalTypes] = React.useState(0);
  const [stages, setStages] = React.useState<Stage[]>([]);
  const [sum, setSum] = React.useState<{ stage_count: number; built_count: number; gamefile_count: number }>(
    { stage_count: 0, built_count: 0, gamefile_count: 0 });

  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [q, setQ] = React.useState('');
  const [openCat, setOpenCat] = React.useState<string>('core');
  const [enrich, setEnrich] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [adding, setAdding] = React.useState<string | null>(null);
  const [editId, setEditId] = React.useState<string | null>(null);
  const [editTitle, setEditTitle] = React.useState('');
  const [editNote, setEditNote] = React.useState('');

  const loadCatalog = React.useCallback(async () => {
    const r = await api.get<any>('/api/galaxy-studio/stages/catalog', { timeoutMs: 12000 });
    if (r.ok && r.data) {
      setGroups(r.data.groups || []);
      setMaxStages(r.data.max_stages || 100000);
      setTotalTypes(r.data.total_types || 0);
    }
  }, []);

  const loadStages = React.useCallback(async (bid: string) => {
    const [lr, sr] = await Promise.all([
      api.get<any>(`/api/galaxy-studio/stages/${bid}/list`, { timeoutMs: 12000 }),
      api.get<any>(`/api/galaxy-studio/stages/${bid}/summary`, { timeoutMs: 12000 }),
    ]);
    if (lr.ok && lr.data) setStages(lr.data.stages || []);
    if (sr.ok && sr.data) setSum({
      stage_count: sr.data.stage_count || 0,
      built_count: sr.data.built_count || 0,
      gamefile_count: sr.data.gamefile_count || 0,
    });
  }, []);

  const beginEdit = React.useCallback((s: Stage) => {
    setEditId(s.id); setEditTitle(s.title || ''); setEditNote(s.note || '');
  }, []);

  const saveEdit = React.useCallback(async (id: string) => {
    await api.put<any>(`/api/galaxy-studio/stages/${buildId}/${id}`,
      { title: editTitle, note: editNote });
    setEditId(null);
    await loadStages(buildId);
  }, [buildId, editTitle, editNote, loadStages]);

  React.useEffect(() => {
    (async () => {
      setLoading(true);
      await Promise.all([loadCatalog(), loadStages(buildId)]);
      setLoading(false);
    })();
  }, [loadCatalog, loadStages, buildId]);

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await Promise.all([loadCatalog(), loadStages(buildId)]);
    setRefreshing(false);
  }, [loadCatalog, loadStages, buildId]);

  const addStage = React.useCallback(async (typeKey: string) => {
    setAdding(typeKey);
    const r = await api.post<any>(`/api/galaxy-studio/stages/${buildId}/add`, { type: typeKey });
    setAdding(null);
    if (r.ok && r.data && !r.data.error) {
      await loadStages(buildId);
    } else if (r.data?.error === 'max_stages_reached') {
      Alert.alert('Maximum stages reached', `This build is capped at ${maxStages.toLocaleString()} stages.`);
    }
  }, [buildId, loadStages, maxStages]);

  const buildStage = React.useCallback(async (id: string) => {
    setBusy(id);
    const r = await api.post<any>(`/api/galaxy-studio/stages/${buildId}/${id}/build`,
      { enrich }, { timeoutMs: enrich ? 60000 : 20000 });
    setBusy(null);
    if (r.ok && r.data && !r.data.error) await loadStages(buildId);
  }, [buildId, enrich, loadStages]);

  const buildAll = React.useCallback(async () => {
    const unbuilt = stages.filter(s => !s.built);
    if (!unbuilt.length) return;
    for (const s of unbuilt) {
      setBusy(s.id);
      const r = await api.post<any>(`/api/galaxy-studio/stages/${buildId}/${s.id}/build`,
        { enrich }, { timeoutMs: enrich ? 60000 : 20000 });
      if (!r.ok) break;
    }
    setBusy(null);
    await loadStages(buildId);
  }, [stages, buildId, enrich, loadStages]);

  const deleteStage = React.useCallback(async (id: string) => {
    await api.del<any>(`/api/galaxy-studio/stages/${buildId}/${id}`);
    await loadStages(buildId);
  }, [buildId, loadStages]);

  const filteredGroups = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return groups;
    return groups
      .map(g => ({ ...g, types: g.types.filter(t =>
        t.label.toLowerCase().includes(needle) || t.summary.toLowerCase().includes(needle) ||
        t.role.toLowerCase().includes(needle)) }))
      .filter(g => g.types.length > 0);
  }, [groups, q]);

  const pct = maxStages ? Math.min(100, (sum.stage_count / maxStages) * 100) : 0;
  const unbuilt = stages.filter(s => !s.built).length;

  if (loading) {
    return (
      <SafeAreaView style={styles.screen} testID="stages-screen">
        <View style={styles.center}><ActivityIndicator color={C.accent} size="large" /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen} testID="stages-screen" edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="stages-back">
          <Ionicons name="chevron-back" size={22} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>🎬 Stage Builder</Text>
          <Text style={styles.h2}>Lay out the game spine · building a stage mints its first gamefiles</Text>
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: 14, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.accent} />}
      >
        {/* Build id */}
        <View style={styles.row}>
          <Text style={styles.lbl}>Build ID</Text>
          <TextInput
            value={buildId}
            onChangeText={setBuildId}
            placeholder="build id"
            placeholderTextColor={C.muted}
            style={styles.input}
            testID="stages-buildid"
            autoCapitalize="none"
          />
        </View>

        {/* Meter */}
        <View style={styles.meter} testID="stage-meter">
          <View style={styles.meterRow}>
            <Text style={styles.meterBig}>{sum.stage_count.toLocaleString()}</Text>
            <Text style={styles.meterMuted}> / {maxStages.toLocaleString()} stages</Text>
          </View>
          <View style={styles.barTrack}><View style={[styles.barFill, { width: `${pct}%` }]} /></View>
          <View style={styles.meterStats}>
            <Text style={styles.stat}>🧱 {sum.stage_count} stages</Text>
            <Text style={styles.stat}>✅ {sum.built_count} built</Text>
            <Text style={styles.stat}>📦 {sum.gamefile_count} gamefiles</Text>
          </View>
        </View>

        {/* Build controls */}
        {stages.length > 0 && (
          <View style={styles.controls}>
            <TouchableOpacity
              style={[styles.toggle, enrich && styles.toggleOn]}
              onPress={() => setEnrich(e => !e)}
              testID="stages-enrich-toggle"
            >
              <Ionicons name={enrich ? 'sparkles' : 'sparkles-outline'} size={15} color={enrich ? '#0b0f1a' : C.muted} />
              <Text style={[styles.toggleTxt, enrich && styles.toggleTxtOn]}>AI enrich</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.buildAll, unbuilt === 0 && styles.disabled]}
              onPress={buildAll}
              disabled={unbuilt === 0 || !!busy}
              testID="stages-build-all"
            >
              <Ionicons name="construct" size={15} color="#0b0f1a" />
              <Text style={styles.buildAllTxt}>Build all unbuilt ({unbuilt})</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Your stages (the spine) */}
        <Text style={styles.section}>📋 Your Stages ({stages.length})</Text>
        {stages.length === 0 && (
          <Text style={styles.empty}>No stages yet. Tap a stage type below to begin the build.</Text>
        )}
        {stages.map((s) => (
          <View key={s.id} style={styles.stageCard} testID={`stage-card-${s.id}`}>
            <View style={styles.stageRow}>
              <View style={styles.seqBadge}><Text style={styles.seqTxt}>{s.seq}</Text></View>
              <View style={{ flex: 1 }}>
                <View style={styles.stageTop}>
                  <Text style={styles.stageIcon}>{s.icon}</Text>
                  <Text style={styles.stageTitle} numberOfLines={1}>{s.title}</Text>
                </View>
                {!!s.note && editId !== s.id && (
                  <Text style={styles.noteTxt} numberOfLines={2}>📝 {s.note}</Text>
                )}
                <View style={styles.tagRow}>
                  <View style={styles.tag}><Text style={styles.tagTxt}>{s.label}</Text></View>
                  <View style={[styles.tag, { borderColor: DIFF_COLOR[s.difficulty] || C.border }]}>
                    <Text style={[styles.tagTxt, { color: DIFF_COLOR[s.difficulty] || C.muted }]}>{s.difficulty}</Text>
                  </View>
                  {s.combat && <View style={styles.tag}><Text style={styles.tagTxt}>⚔️ combat</Text></View>}
                  {s.built
                    ? <View style={[styles.tag, { borderColor: C.green }]}><Text style={[styles.tagTxt, { color: C.green }]}>✅ {s.gamefile_count} gamefiles</Text></View>
                    : <View style={[styles.tag, { borderColor: C.amber }]}><Text style={[styles.tagTxt, { color: C.amber }]}>unbuilt</Text></View>}
                </View>
              </View>
              <View style={styles.stageActions}>
                <TouchableOpacity
                  style={[styles.iconBtn, { backgroundColor: C.alt }]}
                  onPress={() => (editId === s.id ? setEditId(null) : beginEdit(s))}
                  testID={`stage-edit-${s.id}`}
                >
                  <Ionicons name={editId === s.id ? 'close' : 'create-outline'} size={16} color={C.accent2} />
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.iconBtn, { backgroundColor: s.built ? C.alt : C.green }]}
                  onPress={() => buildStage(s.id)}
                  disabled={!!busy}
                  testID={`stage-build-${s.id}`}
                >
                  {busy === s.id
                    ? <ActivityIndicator color={s.built ? C.accent : '#0b0f1a'} size="small" />
                    : <Ionicons name={s.built ? 'refresh' : 'construct'} size={16} color={s.built ? C.accent : '#0b0f1a'} />}
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.iconBtn, { backgroundColor: C.alt }]}
                  onPress={() => deleteStage(s.id)}
                  testID={`stage-delete-${s.id}`}
                >
                  <Ionicons name="trash-outline" size={16} color={C.red} />
                </TouchableOpacity>
              </View>
            </View>

            {/* Inline editor — title + note seed the stage's gamefiles
                (richer text → richer build; AI enrich is the optional LLM pass). */}
            {editId === s.id && (
              <View style={styles.editBox}>
                <TextInput
                  value={editTitle}
                  onChangeText={setEditTitle}
                  placeholder="Stage title"
                  placeholderTextColor={C.muted}
                  style={styles.editInput}
                  testID={`stage-edit-title-${s.id}`}
                />
                <TextInput
                  value={editNote}
                  onChangeText={setEditNote}
                  placeholder="Creator note — describe this stage (seeds the gamefiles)…"
                  placeholderTextColor={C.muted}
                  style={[styles.editInput, styles.editNote]}
                  multiline
                  testID={`stage-edit-note-${s.id}`}
                />
                <View style={styles.editActions}>
                  <Text style={styles.editHint}>
                    {enrich ? '✨ AI enrich ON — Claude refines on Build' : 'Tip: turn on AI enrich for an LLM pass'}
                  </Text>
                  <TouchableOpacity style={styles.saveBtn} onPress={() => saveEdit(s.id)} testID={`stage-edit-save-${s.id}`}>
                    <Text style={styles.saveTxt}>Save</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </View>
        ))}

        {/* Palette */}
        <Text style={styles.section}>➕ Add a stage · {totalTypes} types</Text>
        <View style={styles.searchWrap}>
          <Ionicons name="search" size={16} color={C.muted} />
          <TextInput
            value={q}
            onChangeText={setQ}
            placeholder="Search stage types…"
            placeholderTextColor={C.muted}
            style={styles.search}
            testID="stages-search"
          />
        </View>

        {filteredGroups.map((g) => {
          const open = q.trim() ? true : openCat === g.category;
          return (
            <View key={g.category} style={styles.catBlock}>
              <TouchableOpacity
                style={styles.catHead}
                onPress={() => setOpenCat(openCat === g.category ? '' : g.category)}
                testID={`stage-cat-${g.category}`}
              >
                <Text style={styles.catLabel}>{g.icon} {g.label}</Text>
                <Text style={styles.catCount}>{g.types.length}</Text>
                <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color={C.muted} />
              </TouchableOpacity>
              {open && (
                <View style={styles.chipWrap}>
                  {g.types.map((t) => (
                    <TouchableOpacity
                      key={t.key}
                      style={styles.typeBtn}
                      onPress={() => addStage(t.key)}
                      disabled={!!adding}
                      testID={`stage-type-${t.key}`}
                    >
                      {adding === t.key
                        ? <ActivityIndicator color={C.accent} size="small" />
                        : <Text style={styles.typeIcon}>{t.icon}</Text>}
                      <Text style={styles.typeTxt} numberOfLines={1}>{t.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  backBtn: { padding: 6, marginRight: 4 },
  h1: { color: C.text, fontSize: 20, fontWeight: '800' },
  h2: { color: C.muted, fontSize: 12, marginTop: 2 },
  row: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  lbl: { color: C.muted, fontSize: 13, width: 70 },
  input: { flex: 1, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, color: C.text },
  meter: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14, marginBottom: 12 },
  meterRow: { flexDirection: 'row', alignItems: 'baseline' },
  meterBig: { color: C.accent, fontSize: 26, fontWeight: '900' },
  meterMuted: { color: C.muted, fontSize: 14 },
  barTrack: { height: 8, backgroundColor: C.alt, borderRadius: 4, marginTop: 10, overflow: 'hidden' },
  barFill: { height: 8, backgroundColor: C.accent, borderRadius: 4 },
  meterStats: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 },
  stat: { color: C.text, fontSize: 12, fontWeight: '600' },
  controls: { flexDirection: 'row', gap: 10, marginBottom: 14 },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 },
  toggleOn: { backgroundColor: C.accent2, borderColor: C.accent2 },
  toggleTxt: { color: C.muted, fontSize: 13, fontWeight: '700' },
  toggleTxtOn: { color: '#0b0f1a' },
  buildAll: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, backgroundColor: C.green, borderRadius: 10, paddingVertical: 11 },
  buildAllTxt: { color: '#0b0f1a', fontSize: 13, fontWeight: '800' },
  disabled: { opacity: 0.45 },
  section: { color: C.text, fontSize: 15, fontWeight: '800', marginTop: 6, marginBottom: 10 },
  empty: { color: C.muted, fontSize: 13, fontStyle: 'italic', marginBottom: 12 },
  stageCard: { backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 10 },
  stageRow: { flexDirection: 'row', alignItems: 'center' },
  noteTxt: { color: C.muted, fontSize: 11, marginTop: 5 },
  editBox: { marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border, gap: 8 },
  editInput: { backgroundColor: C.alt, borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 11, paddingVertical: 9, color: C.text, fontSize: 13 },
  editNote: { minHeight: 64, textAlignVertical: 'top' },
  editActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  editHint: { flex: 1, color: C.muted, fontSize: 11 },
  saveBtn: { backgroundColor: C.accent2, borderRadius: 9, paddingHorizontal: 18, paddingVertical: 9 },
  saveTxt: { color: '#0b0f1a', fontWeight: '800', fontSize: 13 },
  seqBadge: { width: 30, height: 30, borderRadius: 15, backgroundColor: C.alt, alignItems: 'center', justifyContent: 'center', marginRight: 10 },
  seqTxt: { color: C.accent, fontSize: 13, fontWeight: '800' },
  stageTop: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  stageIcon: { fontSize: 17 },
  stageTitle: { color: C.text, fontSize: 14, fontWeight: '700', flex: 1 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 7 },
  tag: { borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 7, paddingVertical: 2 },
  tagTxt: { color: C.muted, fontSize: 10, fontWeight: '700' },
  stageActions: { flexDirection: 'row', gap: 7, marginLeft: 8 },
  iconBtn: { width: 38, height: 38, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  searchWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, marginBottom: 12 },
  search: { flex: 1, color: C.text, paddingVertical: 9 },
  catBlock: { marginBottom: 10 },
  catHead: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.alt, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
  catLabel: { color: C.text, fontSize: 13, fontWeight: '800', flex: 1 },
  catCount: { color: C.muted, fontSize: 12, fontWeight: '700' },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  typeBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 11, paddingVertical: 9, minWidth: '47%' },
  typeIcon: { fontSize: 15 },
  typeTxt: { color: C.text, fontSize: 12, fontWeight: '600', flex: 1 },
});
