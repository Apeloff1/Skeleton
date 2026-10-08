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
import { watchBuildJob } from '../src/product/buildJobLifecycle';
import { validBuildId } from '../src/product/journeyCatalog';
import { confirmedApprovalCount, parseEditableKnowledge } from '../src/product/knowledgeExperience';

const FORGEABLE: Record<string, string> = {
  spec: 'spec', world: 'world', narrative: 'narrative', mechanics: 'mechanics',
  procedural: 'procedural', assets: 'assets', qa: 'qa', build: 'build', launch: 'launch',
};
// Stages that participate in the Iterate-&-Refine human-approval loop.
const APPROVABLE = new Set(['spec', 'world', 'narrative', 'mechanics', 'procedural', 'assets', 'qa', 'build']);

export default function GameKB() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const gameId = validBuildId(params?.game);

  const [kb, setKb] = React.useState<any>(null);
  const [loadState, setLoadState] = React.useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = React.useState('');
  const [jobStatus, setJobStatus] = React.useState('');
  const jobController = React.useRef<AbortController | null>(null);
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
  const [approveStatus, setApproveStatus] = React.useState('');
  const [refineStage, setRefineStage] = React.useState<string | null>(null);
  const [refineDraft, setRefineDraft] = React.useState('');
  const [refineBusy, setRefineBusy] = React.useState<string | null>(null);
  const [refineStatus, setRefineStatus] = React.useState('');

  const load = React.useCallback(async () => {
    if (!gameId) return;
    setLoadError('');
    try {
      const result = await api.get<any>(`/api/pipeline/${encodeURIComponent(gameId)}/kb`,
        { timeoutMs: 12_000, retries: 0 });
      if (!result.ok || !result.data || result.data.error) {
        setLoadError('Could not read this knowledge base. Check your connection and retry.');
        setLoadState('error');
        return;
      }
      setKb(result.data);
      setApprovals(result.data.approvals || {});
      setLoadState('ready');
    } catch {
      setLoadError('The knowledge service is unavailable. Retry to read saved artifacts.');
      setLoadState('error');
    }
  }, [gameId]);

  React.useEffect(() => {
    setKb(null);
    setLoadState('loading');
    setOpen({});
    void load();
    return () => {
      // Client monitoring is cancellable. Backend execution is not cancelled.
      jobController.current?.abort();
      jobController.current = null;
    };
  }, [load]);

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    try { await load(); }
    finally { setRefreshing(false); }
  }, [load]);

  const runJob = React.useCallback(async (
    endpoint: string, setFeedback: React.Dispatch<React.SetStateAction<string>>,
    payload: Record<string, unknown> = {},
  ): Promise<boolean> => {
    if (jobController.current || !gameId) return false;
    const controller = new AbortController();
    jobController.current = controller;
    setFeedback('Submitting to the build service…');
    try {
      const result = await api.post<any>(endpoint, payload, { timeoutMs: 15_000, signal: controller.signal, retries: 0 });
      const jobId = result.data?.job_id;
      if (!result.ok || typeof jobId !== 'string' || !jobId) {
        setFeedback('Could not start this operation. Your existing knowledge was not confirmed changed.');
        return false;
      }
      const outcome = await watchBuildJob(
        () => api.get<any>(`/api/playable/job/${encodeURIComponent(jobId)}`,
          { timeoutMs: 12_000, retries: 0, signal: controller.signal }),
        {
          signal: controller.signal,
          intervalMs: 3_000,
          maxChecks: 120,
          onPending: () => setFeedback('Job is queued or running. Waiting for confirmed completion…'),
        },
      );
      if (controller.signal.aborted) return false;
      setFeedback(outcome.message);
      if (outcome.phase !== 'completed') return false;
      await load();
      return true;
    } catch {
      if (!controller.signal.aborted) setFeedback('Status is unavailable. Refresh before retrying to avoid duplicate work.');
      return false;
    } finally {
      if (jobController.current === controller) jobController.current = null;
    }
  }, [gameId, load]);

  const toggleApprove = React.useCallback(async (stage: string) => {
    if (!gameId || approveBusy || jobController.current) return;
    const next = !(approvals[stage] && approvals[stage].approved);
    setApproveBusy(stage);
    setApproveStatus('');
    try {
      const result = await api.post<any>(`/api/pipeline/${encodeURIComponent(gameId)}/approve/${encodeURIComponent(stage)}`,
        { approved: next }, { timeoutMs: 12_000, retries: 0 });
      if (result.ok && result.data?.ok) {
        setApprovals(result.data.approvals || {});
        setApproveStatus('Approval state saved by the game knowledge service.');
      } else {
        setApproveStatus('Approval was not saved. Check your connection before retrying.');
      }
    } catch { setApproveStatus('Approval service unavailable; no change confirmed.'); }
    finally { setApproveBusy(null); }
  }, [gameId, approveBusy, approvals]);

  const submitRefine = React.useCallback(async (stage: string) => {
    const note = refineDraft.trim();
    if (!gameId || !note || refineBusy || jobController.current) return;
    setRefineBusy(stage);
    try {
      const success = await runJob(
        `/api/pipeline/${encodeURIComponent(gameId)}/refine/${encodeURIComponent(stage)}/async`,
        setRefineStatus, { instruction: note });
      if (success) {
        setRefineStage(null);
        setRefineDraft('');
      }
    } finally { setRefineBusy(null); }
  }, [gameId, refineDraft, refineBusy, runJob]);

  const beginEdit = React.useCallback((name: string, raw: unknown) => {
    setEditErr(''); setEditing(name); setDraft(JSON.stringify(raw, null, 2));
  }, []);

  const saveEdit = React.useCallback(async (name: string) => {
    if (!gameId || saving || approveBusy || jobController.current) return;
    let parsed: Record<string, unknown>;
    try { parsed = parseEditableKnowledge(draft); }
    catch (error) {
      setEditErr(error instanceof Error ? error.message : 'Invalid knowledge JSON.');
      return;
    }
    setSaving(true);
    setEditErr('');
    try {
      const result = await api.put<any>(`/api/pipeline/${encodeURIComponent(gameId)}/kb/${encodeURIComponent(name)}`,
        { data: parsed }, { timeoutMs: 12_000, retries: 0 });
      if (result.ok && result.data?.ok) {
        setEditing(null);
        await load();
      } else {
        setEditErr('Save was not confirmed. Your draft is still available for correction.');
      }
    } catch { setEditErr('Save service unavailable. Your unsaved draft remains in the editor.'); }
    finally { setSaving(false); }
  }, [draft, gameId, saving, approveBusy, load]);

  const applyKB = React.useCallback(async () => {
    if (!gameId || applying || jobController.current) return;
    setApplying(true);
    try {
      await runJob(`/api/playable/${encodeURIComponent(gameId)}/apply-kb/async`, setApplyStatus);
    } finally { setApplying(false); }
  }, [gameId, applying, runJob]);

  const forge = React.useCallback(async (stage: string) => {
    if (!gameId || forging || jobController.current) return;
    setForging(stage);
    try {
      await runJob(`/api/pipeline/${encodeURIComponent(gameId)}/forge/${encodeURIComponent(stage)}/async`, setJobStatus);
    } finally { setForging(null); }
  }, [gameId, forging, runJob]);

  if (!gameId) {
    return (
      <SafeAreaView style={s.safe} testID="kb-choose-build">
        <View style={{ padding: 24, gap: 12 }}>
          <Text style={s.title}>Choose a game to inspect</Text>
          <Text style={s.empty}>A game knowledge base requires a real build ID. No demo or unrelated project will be substituted.</Text>
          <TouchableOpacity accessibilityRole="button" testID="kb-select-build"
            style={s.applyKbBtn} onPress={() => router.replace('/my-builds' as never)}>
            <Text style={s.applyKbTxt}>Browse My Builds</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
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
        <TouchableOpacity testID="kb-guided-journeys" accessibilityRole="button"
          accessibilityLabel="Continue guided workflow with this game's knowledge"
          onPress={() => router.push(`/journeys?game=${encodeURIComponent(gameId)}&workflow=knowledge-iteration` as never)}
          style={s.backBtn}>
          <Text style={s.backTxt}>Journey ›</Text>
        </TouchableOpacity>
      </View>

      {!kb && loadState === 'loading' ? (
        <View style={s.center}><ActivityIndicator color="#60A5FA" accessibilityLabel="Loading game knowledge" /></View>
      ) : !kb ? (
        <View testID="kb-error" style={{ padding: 22, gap: 12 }}>
          <Text style={s.empty}>{loadError || 'Game knowledge is not yet available.'}</Text>
          <TouchableOpacity accessibilityRole="button" testID="kb-retry" style={s.applyKbBtn}
            onPress={() => { setLoadState('loading'); void load(); }}>
            <Text style={s.applyKbTxt}>Retry knowledge load</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="button" onPress={() => router.push(`/studio?game=${encodeURIComponent(gameId)}` as never)}
            style={s.forgeBtn}>
            <Text style={s.forgeTxt}>Return to Studio</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView style={s.body} contentContainerStyle={{ paddingBottom: 48 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#60A5FA" />}>
          <Text style={s.sub}>{kb.present_count}/{kb.total} artifacts forged · {confirmedApprovalCount(approvals)} confirmed approved{kb.title ? ` · ${kb.title}` : ''}</Text>
          {!!loadError && <Text testID="kb-stale-warning" style={s.editErr}>Refresh failed. Showing the last successful response; retry before applying changes.</Text>}
          <TouchableOpacity testID="kb-open-studio" accessibilityRole="button"
            onPress={() => router.push(`/studio?game=${encodeURIComponent(gameId)}` as never)}
            style={s.forgeBtn}>
            <Text style={s.forgeTxt}>Continue this game in Studio →</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="kb-world-workbench" accessibilityRole="button"
            accessibilityLabel="Open World Workbench for this game"
            onPress={() => router.push(`/world-workbench?game=${encodeURIComponent(gameId)}` as never)}
            style={[s.forgeBtn, s.reforgeBtn]}>
            <Text style={s.forgeTxt}>Explore world, mechanics and assets →</Text>
          </TouchableOpacity>
          {!!jobStatus && <Text testID="kb-forge-status" accessibilityLiveRegion="polite" style={s.applyStatus}>{jobStatus}</Text>}
          {!!approveStatus && <Text testID="kb-approve-status" accessibilityLiveRegion="polite" style={s.applyStatus}>{approveStatus}</Text>}
          {!!refineStatus && <Text testID="kb-refine-status" accessibilityLiveRegion="polite" style={s.applyStatus}>{refineStatus}</Text>}

          <TouchableOpacity testID="kb-apply-btn" onPress={applyKB} disabled={applying || !!jobController.current || loadState === 'error' || kb.present_count === 0}
            style={[s.applyKbBtn, (applying || !!jobController.current || loadState === 'error' || kb.present_count === 0) && s.btnDisabled]} activeOpacity={0.9}>
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
                      <TouchableOpacity testID={`kb-save-${a.name}`} onPress={() => saveEdit(a.name)} disabled={saving || !!jobController.current || loadState === 'error'}
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
                          disabled={!!refineBusy || !!jobController.current || loadState === 'error' || !refineDraft.trim()} style={[s.saveBtn, (!!refineBusy || !refineDraft.trim()) && s.btnDisabled]} activeOpacity={0.9}>
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
                  <TouchableOpacity testID={`kb-approve-${a.stage}`} onPress={() => toggleApprove(a.stage)} disabled={!!approveBusy || !!jobController.current || loadState === 'error'}
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
                    disabled={!!forging || !!jobController.current || loadState === 'error'} style={[s.forgeBtn, a.present && s.reforgeBtn, !!forging && s.btnDisabled]} activeOpacity={0.9}>
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
