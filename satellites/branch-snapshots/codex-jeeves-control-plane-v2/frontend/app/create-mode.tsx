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

  React.useEffect(() => {
    (async () => {
      const r = await api.get<any>('/api/modes/options', { timeoutMs: 12000 });
      if (r.ok && r.data?.modes) setModes(r.data.modes);
      if (parentId) {
        const g = await api.get<any>(`/api/playable/${parentId}`, { timeoutMs: 12000 });
        if (g.ok && g.data?.title) setParentTitle(g.data.title);
      }
    })();
  }, [parentId]);

  // forge the inheritance brief whenever the picked mode (or note) changes
  const pick = React.useCallback(async (id: string) => {
    setPicked(id); setPreview(null); setStatus('');
    if (!parentId) return;
    const r = await api.post<any>('/api/modes/forge-brief',
      { parent_id: parentId, mode: id, extra: note.trim() }, { timeoutMs: 12000 });
    if (r.ok && r.data?.brief) setPreview(r.data);
  }, [parentId, note]);

  const create = React.useCallback(async () => {
    if (!preview?.brief || busy) return;
    setBusy(true); setStatus('🚀 Forging your new game…');
    const r = await api.post<any>('/api/playable/generate/async',
      { brief: preview.brief, title: preview.title, depth, forged_from: parentId, derive_mode: picked },
      { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) { setStatus(`❌ ${r.data?.error || 'could not start'}`); setBusy(false); return; }
    const jid = r.data.job_id; const t0 = Date.now();
    for (let i = 0; i < 90; i++) {
      await new Promise(res => setTimeout(res, 4000));
      const jr = await api.get<any>(`/api/playable/job/${jid}`, { timeoutMs: 12000 });
      const d = jr.data || {};
      if (d.job_status === 'error') { setStatus(`❌ ${d.error || 'generation failed'}`); break; }
      if (d.job_status === 'done') {
        const newId = d.playable_id || d.id;
        setStatus('✅ Created!');
        if (newId) router.replace(`/playable?id=${newId}` as any);
        break;
      }
      setStatus(`🚀 Building (${Math.round((Date.now() - t0) / 1000)}s)… inheriting canon & applying the mode`);
    }
    setBusy(false);
  }, [preview, busy, parentId, router, picked, depth]);

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

            <TouchableOpacity testID="mode-create" onPress={create} disabled={busy || !preview}
              style={[s.createBtn, (busy || !preview) && s.btnDisabled]} activeOpacity={0.9}>
              {busy ? <ActivityIndicator size="small" color="#fff" /> : (
                <Text style={s.createTxt}>✨ Create “{preview?.title || '…'}”</Text>
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
