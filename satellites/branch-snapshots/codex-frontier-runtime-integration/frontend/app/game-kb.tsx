/**
 * /game-kb — Central Game Knowledge Base viewer.
 *
 * Reads /api/pipeline/{game}/kb and shows every pipeline artifact (core_specs.json,
 * lore_graph.json, quest_DB.json, mechanics_config.json, asset_manifest, build_manifest):
 * present/missing, a summary, expandable pretty-JSON, and a ⚒ Forge / Re-forge action
 * (regenerate) per artifact via /api/pipeline/{game}/forge/{stage}/async.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet,
  SafeAreaView, RefreshControl, TextInput,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';

const FORGEABLE: Record<string, string> = {
  spec: 'spec', world: 'world', narrative: 'narrative', mechanics: 'mechanics',
  procedural: 'procedural', assets: 'assets', qa: 'qa', build: 'build', launch: 'launch',
};
// Stages that participate in the Iterate-&-Refine human-approval loop.
const APPROVABLE = new Set(['spec', 'world', 'narrative', 'mechanics', 'procedural', 'assets', 'qa', 'build']);

export default function GameKB() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const gameId = params?.game ? String(params.game) : '';

  const [kb, setKb] = React.useState<any>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [open, setOpen] = React.useState<Record<string, boolean>>({});
  const [forging, setForging] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState('');
  const [saving, setSaving] = React.useState(false);
  const [editErr, setEditErr] = React.useState('');
  const [applyStatus, setApplyStatus] = React.useState('');
  const [applying, setApplying] = React.useState(false);
  // Iterate & Refine loop
  const [approvals, setApprovals] = React.useState<Record<string, any>>({});
  const [approveBusy, setApproveBusy] = React.useState<string | null>(null);
  const [refineStage, setRefineStage] = React.useState<string | null>(null);
  const [refineDraft, setRefineDraft] = React.useState('');
  const [refineBusy, setRefineBusy] = React.useState<string | null>(null);
  const [refineStatus, setRefineStatus] = React.useState('');

  const load = React.useCallback(async () => {
    if (!gameId) return;
    const r = await api.get<any>(`/api/pipeline/${gameId}/kb`, { timeoutMs: 12000 });
    if (r.ok && r.data && !r.data.error) { setKb(r.data); setApprovals(r.data.approvals || {}); }
  }, [gameId]);

  const toggleApprove = React.useCallback(async (stage: string) => {
    if (!gameId || approveBusy) return;
    const next = !(approvals[stage] && approvals[stage].approved);
    setApproveBusy(stage);
    const r = await api.post<any>(`/api/pipeline/${gameId}/approve/${stage}`,
      { approved: next }, { timeoutMs: 12000 });
    if (r.ok && r.data?.ok) setApprovals(r.data.approvals || {});
    setApproveBusy(null);
  }, [gameId, approveBusy, approvals]);

  const submitRefine = React.useCallback(async (stage: string) => {
    const note = refineDraft.trim();
    if (!gameId || !note || refineBusy) return;
    setRefineBusy(stage); setRefineStatus('Submitting refinement…');
    const r = await api.post<any>(`/api/pipeline/${gameId}/refine/${stage}/async`,
      { instruction: note }, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) { setRefineStatus(`❌ ${r.data?.error || 'could not start'}`); setRefineBusy(null); return; }
    const jid = r.data.job_id; const t0 = Date.now();
    for (let i = 0; i < 50; i++) {
      await new Promise(res => setTimeout(res, 4000));
      const jr = await api.get<any>(`/api/playable/job/${jid}`, { timeoutMs: 12000 });
      const d = jr.data || {};
      if (d.job_status === 'error') { setRefineStatus(`❌ ${d.error || 'refine failed'}`); break; }
      if (d.job_status === 'done') {
        setRefineStatus(d.ok ? `✅ Refined ${d.artifact} — ${d.summary || ''}` : `⚠️ ${d.error || 'kept previous'}`);
        setRefineStage(null); setRefineDraft(''); await load(); break;
      }
      setRefineStatus(`💬 Refining from your note… ${Math.round((Date.now() - t0) / 1000)}s`);
    }
    setRefineBusy(null);
  }, [gameId, refineDraft, refineBusy, load]);

  const beginEdit = React.useCallback((name: string, raw: any) => {
    setEditErr(''); setEditing(name); setDraft(JSON.stringify(raw, null, 2));
  }, []);

  const saveEdit = React.useCallback(async (name: string) => {
    let parsed: any;
    try { parsed = JSON.parse(draft); } catch { setEditErr('Invalid JSON — check syntax.'); return; }
    if (typeof parsed !== 'object' || Array.isArray(parsed)) { setEditErr('Top level must be a JSON object.'); return; }
    setSaving(true); setEditErr('');
    const r = await api.put<any>(`/api/pipeline/${gameId}/kb/${name}`, { data: parsed }, { timeoutMs: 12000 });
    setSaving(false);
    if (r.ok && r.data?.ok) { setEditing(null); await load(); }
    else setEditErr(r.data?.error || 'Save failed.');
  }, [draft, gameId, load]);

  const applyKB = React.useCallback(async () => {
    if (applying) return;
    setApplying(true); setApplyStatus('Submitting…');
    const r = await api.post<any>(`/api/playable/${gameId}/apply-kb/async`, {}, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) { setApplyStatus(`❌ ${r.data?.error || 'could not start'}`); setApplying(false); return; }
    const jid = r.data.job_id; const t0 = Date.now();
    for (let i = 0; i < 60; i++) {
      await new Promise(res => setTimeout(res, 4000));
      const jr = await api.get<any>(`/api/playable/job/${jid}`, { timeoutMs: 12000 });
      const d = jr.data || {};
      if (d.job_status === 'error') { setApplyStatus(`❌ ${d.error || 'sync failed'}`); break; }
      if (d.job_status === 'done') {
        setApplyStatus(d.applied ? `✅ Game synced with KB → v${d.version} (${(d.synced || []).join(', ')})`
                                 : `⚠️ Could not apply cleanly (${d.error || 'kept original'}).`);
        await load(); break;
      }
      setApplyStatus(`⚙️ Retuning game from KB… ${Math.round((Date.now() - t0) / 1000)}s`);
    }
    setApplying(false);
  }, [applying, gameId, load]);

  React.useEffect(() => { load(); }, [load]);

  const onRefresh = React.useCallback(async () => { setRefreshing(true); await load(); setRefreshing(false); }, [load]);

  const forge = React.useCallback(async (stage: string) => {
    if (!gameId || forging) return;
    setForging(stage);
    const r = await api.post<any>(`/api/pipeline/${gameId}/forge/${stage}/async`, {}, { timeoutMs: 15000 });
    if (r.ok && r.data?.job_id) {
      const jid = r.data.job_id;
      for (let i = 0; i < 40; i++) {
        await new Promise(res => setTimeout(res, 3500));
        const jr = await api.get<any>(`/api/playable/job/${jid}`, { timeoutMs: 12000 });
        if (jr.data?.job_status === 'done' || jr.data?.job_status === 'error') break;
      }
      await load();
    }
    setForging(null);
  }, [gameId, forging, load]);

  if (!gameId) {
    return (
      <SafeAreaView style={s.safe}><Text style={s.empty}>No game specified.</Text></SafeAreaView>
    );
  }

  const data = kb?.data || {};

  return (
    <SafeAreaView style={s.safe} testID="game-kb-screen">
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="kb-back" style={s.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Text style={s.backTxt}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>🗄️ Knowledge Base</Text>
        <View style={{ width: 54 }} />
      </View>

      {!kb ? (
        <View style={s.center}><ActivityIndicator color="#60A5FA" /></View>
      ) : (
        <ScrollView style={s.body} contentContainerStyle={{ paddingBottom: 48 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#60A5FA" />}>
          <Text style={s.sub}>{kb.present_count}/{kb.total} artifacts forged · {Object.keys(approvals).length} approved{kb.title ? ` · ${kb.title}` : ''}</Text>

          <TouchableOpacity testID="kb-apply-btn" onPress={applyKB} disabled={applying || kb.present_count === 0}
            style={[s.applyKbBtn, (applying || kb.present_count === 0) && s.btnDisabled]} activeOpacity={0.9}>
            {applying ? <ActivityIndicator size="small" color="#fff" /> : (
              <Text style={s.applyKbTxt}>⚙️ Apply Knowledge Base to game</Text>
            )}
          </TouchableOpacity>
          {!!applyStatus && <Text testID="kb-apply-status" style={s.applyStatus}>{applyStatus}</Text>}

          {(kb.artifacts || []).map((a: any) => {
            const raw = data[a.name];
            const canForge = FORGEABLE[a.stage];
            const isOpen = open[a.name];
            return (
              <View key={a.name} testID={`kb-art-${a.name}`} style={[s.card, a.present ? s.cardOn : s.cardOff]}>
                <TouchableOpacity onPress={() => raw && setOpen(p => ({ ...p, [a.name]: !p[a.name] }))} activeOpacity={0.85}>
                  <View style={s.cardHead}>
                    <Text style={s.cardLabel}>{a.present ? '✅' : '○'} {a.label}</Text>
                    {!!raw && <Text style={s.expand}>{isOpen ? '▲' : '▾ json'}</Text>}
                  </View>
                  {!!a.summary && <Text style={s.cardSummary}>{a.summary}</Text>}
                </TouchableOpacity>

                {isOpen && !!raw && (
                  <ScrollView horizontal style={s.jsonBox} showsHorizontalScrollIndicator>
                    <Text style={s.jsonTxt} selectable>{JSON.stringify(raw, null, 2)}</Text>
                  </ScrollView>
                )}

                {!!raw && editing === a.name && (
                  <View style={{ marginTop: 10 }}>
                    <TextInput testID={`kb-jsoninput-${a.name}`} value={draft} onChangeText={setDraft}
                      multiline style={s.editInput} placeholderTextColor="#475569" autoCapitalize="none" autoCorrect={false} />
                    {!!editErr && <Text style={s.editErr}>{editErr}</Text>}
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                      <TouchableOpacity testID={`kb-save-${a.name}`} onPress={() => saveEdit(a.name)} disabled={saving}
                        style={[s.saveBtn, saving && s.btnDisabled]} activeOpacity={0.9}>
                        {saving ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.forgeTxt}>💾 Save</Text>}
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => { setEditing(null); setEditErr(''); }} style={s.cancelBtn} activeOpacity={0.9}>
                        <Text style={s.cancelTxt}>Cancel</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}

                {!!raw && editing !== a.name && (
                  <TouchableOpacity testID={`kb-edit-${a.name}`} onPress={() => beginEdit(a.name, raw)}
                    style={s.editBtn} activeOpacity={0.85}>
                    <Text style={s.editBtnTxt}>✏️ Edit JSON</Text>
                  </TouchableOpacity>
                )}

                {/* Iterate & Refine — chat-refine this stage from a natural-language note */}
                {!!raw && FORGEABLE[a.stage] && (
                  refineStage === a.stage ? (
                    <View style={{ marginTop: 10 }}>
                      <TextInput testID={`kb-refine-input-${a.stage}`} value={refineDraft} onChangeText={setRefineDraft}
                        placeholder="Describe how to refine this stage (e.g. 'make enemies smarter, add a boss')"
                        placeholderTextColor="#475569" multiline style={s.refineInput} />
                      {!!refineStatus && <Text style={s.refineStatus}>{refineStatus}</Text>}
                      <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                        <TouchableOpacity testID={`kb-refine-submit-${a.stage}`} onPress={() => submitRefine(a.stage)}
                          disabled={!!refineBusy || !refineDraft.trim()} style={[s.saveBtn, (!!refineBusy || !refineDraft.trim()) && s.btnDisabled]} activeOpacity={0.9}>
                          {refineBusy === a.stage ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.forgeTxt}>💬 Refine</Text>}
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => { setRefineStage(null); setRefineDraft(''); setRefineStatus(''); }} style={s.cancelBtn} activeOpacity={0.9}>
                          <Text style={s.cancelTxt}>Cancel</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ) : (
                    <TouchableOpacity testID={`kb-refine-${a.stage}`} onPress={() => { setRefineStage(a.stage); setRefineDraft(''); setRefineStatus(''); }}
                      style={s.refineBtn} activeOpacity={0.85}>
                      <Text style={s.refineBtnTxt}>💬 Refine with a note</Text>
                    </TouchableOpacity>
                  )
                )}

                {/* Iterate & Refine — human approval gate */}
                {APPROVABLE.has(a.stage) && (
                  <TouchableOpacity testID={`kb-approve-${a.stage}`} onPress={() => toggleApprove(a.stage)} disabled={approveBusy === a.stage}
                    style={[s.approveBtn, approvals[a.stage]?.approved ? s.approvedOn : s.approveOff, approveBusy === a.stage && s.btnDisabled]} activeOpacity={0.85}>
                    {approveBusy === a.stage ? <ActivityIndicator size="small" color="#fff" /> : (
                      <Text style={[s.approveTxt, approvals[a.stage]?.approved && s.approvedTxtOn]}>
                        {approvals[a.stage]?.approved ? '✓ Approved — tap to revoke' : '☐ Approve this stage'}
                      </Text>
                    )}
                  </TouchableOpacity>
                )}

                {canForge ? (
                  <TouchableOpacity testID={`kb-forge-${a.stage}`} onPress={() => forge(canForge)}
                    disabled={!!forging} style={[s.forgeBtn, a.present && s.reforgeBtn, !!forging && s.btnDisabled]} activeOpacity={0.9}>
                    {forging === canForge ? <ActivityIndicator size="small" color="#fff" /> : (
                      <Text style={s.forgeTxt}>{a.present ? '↻ Re-forge' : '⚒ Forge'}</Text>
                    )}
                  </TouchableOpacity>
                ) : null}
                {a.name === 'asset_manifest' ? (
                  <TouchableOpacity onPress={() => router.push(`/asset-genesis?game=${gameId}` as any)}
                    style={[s.forgeBtn, s.reforgeBtn]} activeOpacity={0.9}>
                    <Text style={s.forgeTxt}>🎨 Open Asset Genesis</Text>
                  </TouchableOpacity>
                ) : null}
                {a.name === 'launch_manifest' && !!raw ? (
                  <TouchableOpacity testID="kb-launch-deploy" onPress={() => router.push('/build-hub' as any)}
                    style={[s.forgeBtn, s.reforgeBtn]} activeOpacity={0.9}>
                    <Text style={s.forgeTxt}>🚀 Open Build Hub (package & launch)</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            );
          })}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0B1020' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#1E293B' },
  backBtn: { paddingVertical: 6, minWidth: 54 },
  backTxt: { color: '#60A5FA', fontSize: 16, fontWeight: '600' },
  title: { color: '#F1F5F9', fontSize: 18, fontWeight: '800' },
  body: { flex: 1, paddingHorizontal: 16 },
  sub: { color: '#94A3B8', fontSize: 13, marginTop: 14, marginBottom: 8 },
  empty: { color: '#64748B', fontSize: 14, textAlign: 'center', marginTop: 40 },
  card: { borderRadius: 12, padding: 14, marginTop: 12, borderWidth: 1 },
  cardOn: { backgroundColor: '#0d1c14', borderColor: '#14532d' },
  cardOff: { backgroundColor: '#131A2E', borderColor: '#27324A' },
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  cardLabel: { color: '#F1F5F9', fontSize: 15, fontWeight: '700' },
  expand: { color: '#60A5FA', fontSize: 12, fontWeight: '700' },
  cardSummary: { color: '#94A3B8', fontSize: 12, marginTop: 5 },
  jsonBox: { maxHeight: 240, backgroundColor: '#070b16', borderRadius: 8, marginTop: 10, padding: 10 },
  jsonTxt: { color: '#9FE8C0', fontSize: 11, fontFamily: 'monospace' },
  forgeBtn: { marginTop: 12, borderRadius: 10, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', minHeight: 44, backgroundColor: '#2563EB' },
  reforgeBtn: { backgroundColor: '#334155' },
  btnDisabled: { opacity: 0.6 },
  forgeTxt: { color: '#fff', fontSize: 13, fontWeight: '800' },
  applyKbBtn: { marginTop: 12, borderRadius: 12, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', minHeight: 50, backgroundColor: '#7C3AED' },
  applyKbTxt: { color: '#fff', fontSize: 15, fontWeight: '800' },
  applyStatus: { color: '#CBD5E1', fontSize: 13, marginTop: 10, textAlign: 'center' },
  editBtn: { marginTop: 10, borderRadius: 9, paddingVertical: 9, alignItems: 'center', borderWidth: 1, borderColor: '#334155' },
  editBtnTxt: { color: '#94A3B8', fontSize: 12, fontWeight: '700' },
  editInput: { backgroundColor: '#070b16', borderRadius: 8, borderWidth: 1, borderColor: '#27324A', color: '#9FE8C0', fontSize: 11, fontFamily: 'monospace', padding: 10, minHeight: 160, maxHeight: 320, textAlignVertical: 'top' },
  editErr: { color: '#F87171', fontSize: 12, marginTop: 6 },
  saveBtn: { flex: 1, borderRadius: 9, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', minHeight: 44, backgroundColor: '#10B981' },
  cancelBtn: { borderRadius: 9, paddingVertical: 11, paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#334155' },
  cancelTxt: { color: '#94A3B8', fontSize: 13, fontWeight: '700' },
  refineInput: { backgroundColor: '#070b16', borderRadius: 8, borderWidth: 1, borderColor: '#27324A', color: '#E2E8F0', fontSize: 13, padding: 10, minHeight: 70, maxHeight: 160, textAlignVertical: 'top' },
  refineStatus: { color: '#CBD5E1', fontSize: 12, marginTop: 6 },
  refineBtn: { marginTop: 10, borderRadius: 9, paddingVertical: 9, alignItems: 'center', borderWidth: 1, borderColor: '#4338ca' },
  refineBtnTxt: { color: '#a5b4fc', fontSize: 12, fontWeight: '700' },
  approveBtn: { marginTop: 8, borderRadius: 9, paddingVertical: 10, alignItems: 'center', justifyContent: 'center', minHeight: 42, borderWidth: 1 },
  approveOff: { backgroundColor: 'transparent', borderColor: '#334155' },
  approvedOn: { backgroundColor: '#0d2818', borderColor: '#16A34A' },
  approveTxt: { color: '#94A3B8', fontSize: 12, fontWeight: '800' },
  approvedTxtOn: { color: '#4ade80' },
});
