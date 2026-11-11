/**
 * /create-mode — Stage 1 of the AI Game-Builder pipeline: MODE SELECTION.
 *
 * From a parent game (?parent=<playable_id>), the creator picks one of the 12 creation
 * modes (Sequel, Prequel, Expansion, …). We assemble an inheritance-aware brief via
 * /api/modes/forge-brief, then spin off a NEW game via /api/playable/generate/async
 * (forged_from = parent) with live progress, and route to the new /playable on success.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet,
  SafeAreaView, TextInput,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';

interface Mode {
  id: string; label: string; emoji: string; inherit: string; directive: string;
}

export default function CreateMode() {
  const router = useRouter();
  const params = useLocalSearchParams<{ parent?: string }>();
  const parentId = params?.parent ? String(params.parent) : '';

  const [modes, setModes] = React.useState<Mode[]>([]);
  const [parentTitle, setParentTitle] = React.useState('');
  const [picked, setPicked] = React.useState<string | null>(null);
  const [note, setNote] = React.useState('');
  const [preview, setPreview] = React.useState<any>(null);
  const [busy, setBusy] = React.useState(false);
  const [status, setStatus] = React.useState('');
  const [depth, setDepth] = React.useState<'fast' | 'studio'>('studio');
  const [loadError, setLoadError] = React.useState('');
  const [previewBusy, setPreviewBusy] = React.useState(false);
  const [activeJob, setActiveJob] = React.useState('');

  const load = React.useCallback(async () => {
      setLoadError('');
      const r = await api.get<any>('/api/modes/options', { timeoutMs: 12000 });
      if (!r.ok || !Array.isArray(r.data?.modes) || r.data.modes.length === 0 || r.data.modes.length > 32) {
        setModes([]); setLoadError(r.error || 'Creation modes could not be loaded.'); return;
      }
      setModes(r.data.modes);
      if (parentId) {
        const g = await api.get<any>(`/api/playable/${encodeURIComponent(parentId)}`, { timeoutMs: 12000 });
        if (!g.ok || typeof g.data?.title !== 'string') setLoadError('The source game could not be verified.');
        else setParentTitle(g.data.title);
      }
  }, [parentId]);
  React.useEffect(() => { void load(); }, [load]);

  // forge the inheritance brief whenever the picked mode (or note) changes
  const pick = React.useCallback(async (id: string) => {
    if (!modes.some(mode => mode.id === id)) return;
    setPicked(id); setPreview(null); setStatus(''); setPreviewBusy(true);
    if (!parentId) { setPreviewBusy(false); return; }
    try {
      const r = await api.post<any>('/api/modes/forge-brief',
        { parent_id: parentId, mode: id, extra: note.trim() }, { timeoutMs: 12000 });
      if (!r.ok || typeof r.data?.brief !== 'string' || !r.data.brief.trim() || typeof r.data?.title !== 'string') {
        setStatus(`❌ ${r.error || r.data?.error || 'The inheritance brief was not confirmed.'}`); return;
      }
      setPreview(r.data);
    } finally { setPreviewBusy(false); }
  }, [parentId, note, modes]);

  const pollJob = React.useCallback(async (jid: string) => {
    const t0 = Date.now();
    for (let i = 0; i < 90; i++) {
      await new Promise(res => setTimeout(res, 4000));
      const jr = await api.get<any>(`/api/playable/job/${encodeURIComponent(jid)}`, { timeoutMs: 12000 });
      if (!jr.ok || !jr.data || typeof jr.data.job_status !== 'string') {
        setStatus('⚠ Build status is temporarily unavailable. Resume status checking without starting a duplicate build.');
        return;
      }
      const d = jr.data;
      if (d.job_status === 'error') { setStatus(`❌ ${d.error || 'generation failed'}`); setActiveJob(''); return; }
      if (d.job_status === 'done') {
        const newId = d.playable_id || d.id;
        if (typeof newId !== 'string' || !newId.trim()) { setStatus('❌ Build completed without a playable identity.'); return; }
        setStatus('✅ Created!'); setActiveJob('');
        router.replace(`/playable?id=${encodeURIComponent(newId)}` as any);
        return;
      }
      if (!['queued', 'running', 'building', 'pending'].includes(d.job_status)) {
        setStatus(`❌ Unsupported build state: ${d.job_status}`); return;
      }
      setStatus(`🚀 Building (${Math.round((Date.now() - t0) / 1000)}s)… inheriting canon & applying the mode`);
    }
    setStatus('⚠ Build is still running. Resume status checking without starting a duplicate build.');
  }, [router]);

  const create = React.useCallback(async () => {
    if (busy) return;
    setBusy(true); setStatus('🚀 Forging your new game…');
    if (activeJob) {
      await pollJob(activeJob); setBusy(false); return;
    }
    if (!preview?.brief) { setBusy(false); return; }
    const r = await api.post<any>('/api/playable/generate/async',
      { brief: preview.brief, title: preview.title, depth, forged_from: parentId, derive_mode: picked },
      { timeoutMs: 15000 });
    if (!r.ok || typeof r.data?.job_id !== 'string' || !r.data.job_id.trim()) { setStatus(`❌ ${r.data?.error || r.error || 'could not start'}`); setBusy(false); return; }
    const jid = r.data.job_id; setActiveJob(jid);
    await pollJob(jid);
    setBusy(false);
  }, [preview, busy, parentId, picked, depth, activeJob, pollJob]);

  if (!parentId) {
    return (
      <SafeAreaView style={s.root}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
          <Text style={s.title}>Mode Selection</Text>
        </View>
        <Text style={s.empty}>Open this from a game to spin off a sequel, prequel, expansion and more.</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={s.title}>🎬 Mode Selection</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
        <Text style={s.sub}>Spin off a new game from{parentTitle ? ` “${parentTitle}”` : ' this game'} — pick how it relates to the original. Stage 1 of the pipeline sets the inheritance contract.</Text>

        {!!loadError && <View style={s.errorCard}><Text accessibilityRole="alert" style={s.errorText}>{loadError}</Text><TouchableOpacity onPress={() => { void load(); }} style={s.retry}><Text style={s.retryText}>Retry source and modes</Text></TouchableOpacity></View>}

        <View style={s.grid}>
          {modes.map(m => {
            const on = picked === m.id;
            return (
              <TouchableOpacity key={m.id} testID={`mode-${m.id}`} onPress={() => pick(m.id)} activeOpacity={0.85}
                style={[s.card, on && s.cardOn]}>
                <Text style={s.cardEmoji}>{m.emoji}</Text>
                <Text style={[s.cardLabel, on && s.cardLabelOn]}>{m.label}</Text>
                <Text style={s.cardInherit} numberOfLines={1}>↳ {m.inherit.replace(/\+/g, ', ')}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {picked && (
          <View style={s.detail}>
            <Text style={s.detailDirective}>{modes.find(m => m.id === picked)?.directive}</Text>
            <Text style={s.noteLabel}>Optional creative nudge</Text>
            <TextInput testID="mode-note" value={note} onChangeText={setNote}
              onBlur={() => picked && pick(picked)}
              placeholder="e.g. set it on a frozen moon; add a rival crew"
              placeholderTextColor="#475569" style={s.noteInput} multiline />
            {previewBusy && <View style={s.previewBusy}><ActivityIndicator size="small" color="#a5b4fc" /><Text style={s.status}>Verifying inheritance brief…</Text></View>}

            {preview?.inherited && (
              <View style={s.inheritBox}>
                <Text style={s.inheritTitle}>Inheriting from canon</Text>
                <Text style={s.inheritLine}>📜 Contract: {preview.inherited.contract?.replace(/\+/g, ', ')}</Text>
                {!!preview.inherited.characters && <Text style={s.inheritLine}>🎭 Characters: {preview.inherited.characters.join(', ')}</Text>}
                {!!preview.inherited.quests && <Text style={s.inheritLine}>🗺️ Beats: {preview.inherited.quests.join('; ')}</Text>}
                {!!preview.inherited.factions && <Text style={s.inheritLine}>⚔️ Factions: {preview.inherited.factions.join(', ')}</Text>}
              </View>
            )}

            {!!status && <Text style={s.status}>{status}</Text>}

            <View style={s.depthRow}>
              <Text style={s.noteLabel}>Build quality</Text>
              <View style={s.depthToggle}>
                {(['fast', 'studio'] as const).map(d => (
                  <TouchableOpacity key={d} testID={`mode-depth-${d}`} onPress={() => setDepth(d)} activeOpacity={0.85}
                    style={[s.depthOpt, depth === d && s.depthOptOn]}>
                    <Text style={[s.depthTxt, depth === d && s.depthTxtOn]}>{d === 'fast' ? '⚡ Fast' : '✨ Studio'}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <TouchableOpacity testID="mode-create" onPress={create} disabled={busy || (!preview && !activeJob)}
              style={[s.createBtn, (busy || (!preview && !activeJob)) && s.btnDisabled]} activeOpacity={0.9}>
              {busy ? <ActivityIndicator size="small" color="#fff" /> : (
                <Text style={s.createTxt}>{activeJob ? '↻ Resume build status' : `✨ Create “${preview?.title || '…'}”`}</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#05070d' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#141c2e', gap: 8 },
  back: { paddingVertical: 6, paddingHorizontal: 8 },
  backTxt: { color: '#60a5fa', fontSize: 15, fontWeight: '700' },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '800' },
  sub: { color: '#94A3B8', fontSize: 13, lineHeight: 19, marginBottom: 16 },
  errorCard: { backgroundColor: '#30161d', borderColor: '#7f3342', borderWidth: 1, borderRadius: 10, padding: 12, marginBottom: 14 },
  errorText: { color: '#fca5a5', fontSize: 12, lineHeight: 18, fontWeight: '700' },
  retry: { alignSelf: 'flex-start', marginTop: 8, borderColor: '#7f3342', borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7 },
  retryText: { color: '#E2E8F0', fontSize: 12, fontWeight: '800' },
  previewBusy: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  empty: { color: '#94A3B8', fontSize: 14, padding: 24, textAlign: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: { width: '31%', minWidth: 100, backgroundColor: '#0b1220', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', padding: 12, minHeight: 92, justifyContent: 'center' },
  cardOn: { borderColor: '#6366f1', backgroundColor: '#141a36' },
  cardEmoji: { fontSize: 22, marginBottom: 4 },
  cardLabel: { color: '#E2E8F0', fontSize: 13, fontWeight: '800' },
  cardLabelOn: { color: '#a5b4fc' },
  cardInherit: { color: '#64748b', fontSize: 10, marginTop: 3 },
  detail: { marginTop: 18, backgroundColor: '#0b1220', borderRadius: 14, borderWidth: 1, borderColor: '#1e293b', padding: 16 },
  detailDirective: { color: '#CBD5E1', fontSize: 14, lineHeight: 20, marginBottom: 14 },
  noteLabel: { color: '#94A3B8', fontSize: 12, fontWeight: '700', marginBottom: 6 },
  noteInput: { backgroundColor: '#070b16', borderRadius: 9, borderWidth: 1, borderColor: '#27324A', color: '#E2E8F0', fontSize: 13, padding: 10, minHeight: 56, textAlignVertical: 'top' },
  inheritBox: { marginTop: 14, backgroundColor: '#0a1528', borderRadius: 10, borderWidth: 1, borderColor: '#1e3a5f', padding: 12, gap: 4 },
  inheritTitle: { color: '#93C5FD', fontSize: 12, fontWeight: '800', marginBottom: 2 },
  inheritLine: { color: '#cbd5e1', fontSize: 12, lineHeight: 18 },
  status: { color: '#CBD5E1', fontSize: 13, marginTop: 12 },
  depthRow: { marginTop: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  depthToggle: { flexDirection: 'row', backgroundColor: '#070b16', borderRadius: 9, borderWidth: 1, borderColor: '#27324A', overflow: 'hidden' },
  depthOpt: { paddingVertical: 7, paddingHorizontal: 14 },
  depthOptOn: { backgroundColor: '#6366f1' },
  depthTxt: { color: '#94A3B8', fontSize: 12, fontWeight: '800' },
  depthTxtOn: { color: '#fff' },
  createBtn: { marginTop: 14, backgroundColor: '#6366f1', borderRadius: 11, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', minHeight: 50 },
  btnDisabled: { opacity: 0.5 },
  createTxt: { color: '#fff', fontSize: 15, fontWeight: '800' },
});
