/**
 * /gameforge-studio — CNS Studio console (tabbed).
 *   Overview · Build · Map · Jeeves
 * Governed pipeline oversight, the build flow (questionnaire/steps/forges/deploy),
 * the CNS Master Map (mastermap/rooms/seats/skills/toolbox/systems), and Jeeves
 * (self-trained brain + command channel).
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity,
  ActivityIndicator, TextInput, KeyboardAvoidingView, Platform, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { _circuitBreakerStats } from '../src/utils/apiClient';
import StudioLoginGate, { useStudioAuth } from '../src/auth/StudioLoginGate';
import { authHeaders, getAuthToken, logout as authLogout } from '../src/auth/gameforgeAuth';
import UnifiedVault from '../src/components/UnifiedVault';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

const S = '/api/gameforge/studio';
const M = '/api/gameforge/map';
const BUILD = '/api/gameforge/build';
const RT = '/api/gameforge/runtime';
const PLAN = '/api/gameforge/planning';
const TOOLS = '/api/gameforge/tools';
const WF = '/api/gameforge/workflow';
const AUTH = '/api/auth';
const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const authOpts = (timeoutMs = 20000) =>
  (getAuthToken() ? { timeoutMs, headers: authHeaders() } : { timeoutMs });
const GREEN = '#22c55e';
const BLUE = '#3b82f6';
const CARD = '#111827';
const BG = '#0b1220';
const MUTE = '#94a3b8';
const VC: Record<string, string> = { accept: GREEN, revise: '#f59e0b', reject: '#ef4444' };
const TABS = ['Overview', 'Build', 'Ship', 'Vault', 'Map', 'Jeeves', 'Learn', 'Observe', 'Agents'] as const;
type Tab = typeof TABS[number];

export default function GameforgeStudio() {
  return (
    <StudioLoginGate>
      <StudioInner />
    </StudioLoginGate>
  );
}

function StudioInner() {
  const router = useRouter();
  const { role: authRole, user: authUser, enforced, refresh: refreshAuth } = useStudioAuth();
  const [tab, setTab] = React.useState<Tab>('Overview');
  const [busy, setBusy] = React.useState(false);

  // shared state
  const [oversight, setOversight] = React.useState<any>(null);
  const [ledger, setLedger] = React.useState<any[]>([]);
  const [activity, setActivity] = React.useState<any[]>([]);
  const [flow, setFlow] = React.useState<any[]>([]);
  const [steps, setSteps] = React.useState<any>({});
  const [questions, setQuestions] = React.useState<any[]>([]);
  const [forgeLog, setForgeLog] = React.useState<string>('');
  const [mapData, setMapData] = React.useState<any>(null);
  const [systems, setSystems] = React.useState<any>(null);
  const [seats, setSeats] = React.useState<any>(null);
  const [skills, setSkills] = React.useState<any>(null);
  const [msg, setMsg] = React.useState('');
  const [reply, setReply] = React.useState('');
  const [knowledge, setKnowledge] = React.useState<any[]>([]);
  // Learn tab
  const [brain, setBrain] = React.useState<any>(null);
  const [apiCats, setApiCats] = React.useState<string[]>([]);
  const [apiTotal, setApiTotal] = React.useState(0);
  const [learnQ, setLearnQ] = React.useState('');
  const [learnRes, setLearnRes] = React.useState('');
  const [improveRes, setImproveRes] = React.useState('');
  const [obs, setObs] = React.useState<any>(null);
  const [obsLive, setObsLive] = React.useState(false);
  const [circuits, setCircuits] = React.useState<any>({});
  // Build artifacts
  const [builds, setBuilds] = React.useState<any[]>([]);
  const [buildMsg, setBuildMsg] = React.useState('');
  // Agents runtime
  const [rtStatus, setRtStatus] = React.useState<any>(null);
  const [agentList, setAgentList] = React.useState<any[]>([]);
  const [rtTasks, setRtTasks] = React.useState<any[]>([]);
  const [groupchat, setGroupchat] = React.useState<any[]>([]);
  const [agentHealth, setAgentHealth] = React.useState<any>(null);
  const [alarms, setAlarms] = React.useState<any[]>([]);
  const [unresolvedAlarms, setUnresolvedAlarms] = React.useState(0);
  const [recoverMsg, setRecoverMsg] = React.useState('');
  const [plan, setPlan] = React.useState<any>(null);
  const [planObjective, setPlanObjective] = React.useState('Ship a roguelike vertical slice');
  const [positions, setPositions] = React.useState<any>(null);
  const [uniLogs, setUniLogs] = React.useState<any[]>([]);
  const [tools, setTools] = React.useState<any[]>([]);
  const [comboMsg, setComboMsg] = React.useState('');

  // ── Ship tab: Autonomous Workflow (Prompt→…→Deployment) + JeevesVault ──
  const [wfPrompt, setWfPrompt] = React.useState('A deep dark-fantasy roguelike RPG with emergent combat, meaningful progression, and branching quests');
  const [wfIters, setWfIters] = React.useState(4);
  const [wfBusy, setWfBusy] = React.useState(false);
  const [wfResult, setWfResult] = React.useState<any>(null);
  const [wfErr, setWfErr] = React.useState('');
  const [vaultPkgs, setVaultPkgs] = React.useState<any[]>([]);
  const [dlMsg, setDlMsg] = React.useState('');
  // Auth (session managed by the gate; this tab shows status + logout)
  const [logoutBusy, setLogoutBusy] = React.useState(false);
  // Audit + build ledger + role admin
  const [auditLog, setAuditLog] = React.useState<any[]>([]);
  const [buildLedger, setBuildLedger] = React.useState<any[]>([]);
  const [roleEmail, setRoleEmail] = React.useState('');
  const [roleValue, setRoleValue] = React.useState<'viewer' | 'editor' | 'admin'>('editor');
  const [roleMsg, setRoleMsg] = React.useState('');

  const loadOverview = React.useCallback(async () => {
    const [o, l, a, f, au] = await Promise.all([
      api.get<any>(`${S}/jeeves/oversight`), api.get<any>(`${S}/boardroom/ledger?limit=8`),
      api.get<any>(`${S}/rooms/activity?limit=10`), api.get<any>(`${S}/flow`),
      api.get<any>(`${S}/audit?limit=12`),
    ]);
    if (o.ok) setOversight(o.data);
    if (l.ok) setLedger(l.data?.ledger || []);
    if (a.ok) setActivity(a.data?.activity || []);
    if (f.ok) setFlow(f.data?.pipeline || []);
    if (au.ok) setAuditLog(au.data?.audit || []);
  }, []);

  const loadVaultTab = React.useCallback(async () => {
    const r = await api.get<any>('/api/galaxy-studio/builds?limit=20', { timeoutMs: 15000 });
    if (r.ok) setBuildLedger(r.data?.builds || r.data?.items || (Array.isArray(r.data) ? r.data : []));
  }, []);

  const loadBuild = React.useCallback(async () => {
    const [st, q] = await Promise.all([api.get<any>(`${S}/steps`), api.get<any>(`${S}/questionnaire/questions`)]);
    if (st.ok) setSteps(st.data?.steps || {});
    if (q.ok) setQuestions(q.data?.questions || []);
  }, []);

  const loadMap = React.useCallback(async () => {
    const [ov, sy, se, sk] = await Promise.all([
      api.get<any>(`${M}/overview`), api.get<any>(`${M}/systems`),
      api.get<any>(`${M}/seats`), api.get<any>(`${M}/skills`),
    ]);
    if (ov.ok) setMapData(ov.data);
    if (sy.ok) setSystems(sy.data);
    if (se.ok) setSeats(se.data);
    if (sk.ok) setSkills(sk.data?.master_skill_bank?.skill_categories || {});
  }, []);

  const loadJeeves = React.useCallback(async () => {
    const k = await api.get<any>(`${S}/jeeves/knowledge`);
    if (k.ok) setKnowledge(k.data?.knowledge || []);
  }, []);

  const loadLearn = React.useCallback(async () => {
    const [k, a] = await Promise.all([api.get<any>(`${S}/jeeves/knowledge`), api.get<any>(`/api/gameforge/knowledge/apis`)]);
    if (k.ok) setBrain(k.data?.status || null);
    if (a.ok) { setApiCats(a.data?.categories || []); setApiTotal(a.data?.total || 0); }
  }, []);

  const loadObserve = React.useCallback(async () => {
    const [r, al, lg] = await Promise.all([
      api.get<any>(`${S}/observability`), api.get<any>(`${S}/alarms?limit=15`), api.get<any>(`${S}/logs?limit=20`),
    ]);
    if (r.ok) setObs(r.data);
    if (al.ok) { setAlarms(al.data?.alarms || []); setUnresolvedAlarms(al.data?.unresolved || 0); }
    if (lg.ok) setUniLogs(lg.data?.logs || []);
    try { setCircuits(_circuitBreakerStats()); } catch { /* noop */ }
  }, []);

  const loadAgents = React.useCallback(async () => {
    const [st, ag, tk, gc, h, pos, tl] = await Promise.all([
      api.get<any>(`${RT}/status`), api.get<any>(`${RT}/agents?limit=20`), api.get<any>(`${RT}/tasks?limit=10`),
      api.get<any>(`${RT}/groupchat?limit=12`), api.get<any>(`${RT}/health`), api.get<any>(`${RT}/positions`),
      api.get<any>(`${TOOLS}`),
    ]);
    if (st.ok) setRtStatus(st.data);
    if (ag.ok) setAgentList(ag.data?.agents || []);
    if (tk.ok) setRtTasks(tk.data?.tasks || []);
    if (gc.ok) setGroupchat(gc.data?.messages || []);
    if (h.ok) setAgentHealth(h.data);
    if (pos.ok) setPositions(pos.data);
    if (tl.ok) setTools(tl.data?.tools || []);
  }, []);
  const scoreCombo = async () => {
    if (tools.length < 2) return;
    setBusy(true); setComboMsg('Scoring synergy…');
    const ids = tools.slice(0, 4).map((t: any) => t.tool_id);
    const r = await api.post<any>(`${TOOLS}/combination/score`, { tool_ids: ids }, { timeoutMs: 15000 });
    setComboMsg(r.ok ? `Combo: ${r.data.rating} · score ${r.data.total_score} (${r.data.synergies} synergies, ${r.data.conflicts} conflicts)` : 'Scoring failed.');
    setBusy(false);
  };

  const loadBuildsList = React.useCallback(async () => {
    const r = await api.get<any>(`${BUILD}/list`);
    if (r.ok) setBuilds(r.data?.builds || []);
  }, []);

  React.useEffect(() => { loadOverview(); }, [loadOverview]);
  React.useEffect(() => {
    if (tab === 'Build') { loadBuild(); loadBuildsList(); }
    else if (tab === 'Ship') loadVaultPkgs();
    else if (tab === 'Vault') loadVaultTab();
    else if (tab === 'Map') loadMap();
    else if (tab === 'Jeeves') loadJeeves();
    else if (tab === 'Learn') loadLearn();
    else if (tab === 'Observe') loadObserve();
    else if (tab === 'Agents') loadAgents();
  }, [tab, loadBuild, loadBuildsList, loadVaultPkgs, loadVaultTab, loadMap, loadJeeves, loadLearn, loadObserve, loadAgents]);

  // Priority-4 Observability: live auto-refresh while on the Observe tab.
  React.useEffect(() => {
    if (tab !== 'Observe' || !obsLive) return;
    const id = setInterval(() => { loadObserve(); }, 5000);
    return () => clearInterval(id);
  }, [tab, obsLive, loadObserve]);

  const doBuild = async (kind: 'web' | 'source' | 'desktop' | 'godot') => {
    setBusy(true); setBuildMsg(`Building ${kind}… (desktop can take ~60s)`);
    const r = await api.post<any>(`${BUILD}/${kind}`, { game_name: 'Studio' }, authOpts(118000));
    setBuildMsg(r.ok && r.data?.ok ? `Built ${kind}: ${((r.data.size_bytes || 0) / 1024).toFixed(1)} KB (sha ${r.data.sha256?.slice(0, 8)})` : `Build ${kind} failed: ${r.data?.error || ''}`);
    await loadBuildsList(); setBusy(false);
  };
  const doShip = async () => {
    setBusy(true); setBuildMsg('🚀 Shipping: build → commit → push…');
    const r = await api.post<any>(`${S}/ship`, { game_name: 'Studio', push: true }, authOpts(60000));
    setBuildMsg(r.ok && r.data?.ok ? `Shipped: ${r.data.steps.join(' → ')} (committed ${r.data.git_committed})` : 'Ship failed');
    await loadBuildsList(); setBusy(false);
  };
  const openDownload = (url: string) => { if (url) Linking.openURL(`${BACKEND}${url}`); };
  const spawnAgents = async () => {
    setBusy(true);
    await api.post(`${RT}/spawn`, { category: 'engineering', count: 3 }, { timeoutMs: 15000 });
    await loadAgents(); setBusy(false);
  };
  const delegate = async () => {
    setBusy(true);
    await api.post(`${RT}/delegate`, { to_category: 'art', task: 'design a hero sprite' }, { timeoutMs: 15000 });
    await loadAgents(); setBusy(false);
  };
  const delegateExecute = async () => {
    setBusy(true);
    await api.post(`${RT}/delegate/execute`, { to_category: 'engineering', task: 'implement double-jump with coyote time' }, { timeoutMs: 20000 });
    await loadAgents(); setBusy(false);
  };
  const autoRecover = async () => {
    setBusy(true); setRecoverMsg('Recovering…');
    const r = await api.post<any>(`${S}/auto-recover`, { reason: 'manual' }, authOpts(20000));
    setRecoverMsg(r.ok && r.data?.recovered
      ? `Recovered: rolled back ${r.data.filename} to v${r.data.restored_from} (new v${r.data.new_version}).`
      : (r.data?.reason || (r.status === 401 || r.status === 403 ? 'Editor role required.' : 'Nothing to recover.')));
    await loadObserve(); setBusy(false);
  };
  const runStrategicPlan = async () => {
    setBusy(true); setPlan(null);
    const r = await api.post<any>(`${PLAN}/strategic-plan`, { objective: planObjective, horizon_days: 45, base_risk: 0.25, scenario: 'aggressive_timeline' }, { timeoutMs: 20000 });
    if (r.ok && r.data?.ok) setPlan(r.data);
    setBusy(false);
  };
  const loadVaultPkgs = React.useCallback(async () => {
    const r = await api.get<any>(`${WF}/vault?limit=25`, { timeoutMs: 15000 });
    if (r.ok && r.data?.ok) setVaultPkgs(r.data.packages || []);
  }, []);

  const runWorkflow = async () => {
    const p = wfPrompt.trim();
    if (!p || wfBusy) return;
    setWfBusy(true); setWfErr(''); setWfResult(null); setDlMsg('');
    const r = await api.post<any>(`${WF}/run`,
      { prompt: p, project_name: 'Studio', max_iterations: wfIters },
      authOpts(118000));
    if (r.ok && r.data?.ok) { setWfResult(r.data); await loadVaultPkgs(); }
    else setWfErr(r.data?.detail || 'Workflow failed — please retry.');
    setWfBusy(false);
  };

  const downloadPackage = async (pkg: any) => {
    if (!pkg?.package_id) return;
    setDlMsg(`Fetching ${pkg.package_name}…`);
    const r = await api.get<any>(`${WF}/vault/${pkg.package_id}/download`, { timeoutMs: 30000 });
    if (!r.ok || !r.data?.ok || !r.data?.content_base64) {
      setDlMsg(`Download failed: ${r.data?.detail || 'unavailable'}`);
      return;
    }
    const { content_base64, package_name, sha256 } = r.data;
    try {
      if (Platform.OS === 'web') {
        const bytes = Uint8Array.from(atob(content_base64), (c) => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: 'application/zip' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = package_name; a.click();
        URL.revokeObjectURL(url);
        setDlMsg(`Downloaded ${package_name} (sha ${String(sha256).slice(0, 8)})`);
      } else {
        const path = `${FileSystem.cacheDirectory}${package_name}`;
        await FileSystem.writeAsStringAsync(path, content_base64, { encoding: FileSystem.EncodingType.Base64 });
        if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(path);
        setDlMsg(`Saved ${package_name} — ready to share.`);
      }
    } catch (e: any) {
      setDlMsg(`Saved to device failed: ${e?.message || e}`);
    }
  };

  const doLogout = async () => {
    setLogoutBusy(true);
    await authLogout();
    await refreshAuth();
    setLogoutBusy(false);
  };
  const updateRole = async () => {
    if (!roleEmail.trim() || busy) return;
    setBusy(true); setRoleMsg('Updating role…');
    const r = await api.post<any>(`${AUTH}/set-role`, { email: roleEmail.trim().toLowerCase(), role: roleValue }, authOpts(15000));
    setRoleMsg(r.ok && r.data?.ok ? `${roleEmail.trim()} is now ${roleValue}` : (r.data?.detail || 'Failed — admin only'));
    if (r.ok && r.data?.ok) setRoleEmail('');
    setBusy(false);
  };

  const teachJeeves = async (text?: string) => {
    const q = (text ?? learnQ).trim(); if (!q || busy) return;
    setBusy(true); setLearnRes('Acquiring knowledge…');
    const r = await api.post<any>('/api/gameforge/knowledge/learn', { query: q }, { timeoutMs: 20000 });
    setLearnRes(r.ok && r.data?.ok ? `[${r.data.api}] ${r.data.summary}` : 'Could not acquire that right now.');
    setLearnQ(''); await loadLearn(); setBusy(false);
  };
  const selfImprove = async () => {
    setBusy(true); setImproveRes('Reflecting…');
    const r = await api.post<any>('/api/gameforge/knowledge/self-improve', { quality: 0.8, coherence: 0.75, synergy: 0.6 }, { timeoutMs: 20000 });
    setImproveRes(r.ok ? (r.data?.reflection?.improvements || []).join(' · ') : 'Self-improve failed.');
    setBusy(false);
  };

  const completeStep = async (id: string) => {
    setBusy(true);
    await api.post(`${S}/step/${id}/complete`, {});
    await loadBuild(); await loadOverview(); setBusy(false);
  };
  const runForges = async () => {
    setBusy(true); setForgeLog('Running forges…');
    const r = await api.post<any>(`${S}/forge/run`, {}, { timeoutMs: 20000 });
    setForgeLog(r.ok ? `Forges complete: ${Object.keys(r.data?.results || {}).join(', ')}` : 'Forge failed');
    setBusy(false);
  };
  const deploy = async () => {
    setBusy(true); setForgeLog('Deploying (APK/EXE/Web)…');
    const r = await api.post<any>(`${S}/deploy`, { game_name: 'Studio' }, { timeoutMs: 20000 });
    setForgeLog(r.ok ? `Deployed: ${(r.data?.deployment?.platforms || []).join(', ')}` : 'Deploy failed');
    setBusy(false);
  };
  const sendCommand = async (text?: string) => {
    const m = (text ?? msg).trim(); if (!m || busy) return;
    setBusy(true); setReply('');
    const r = await api.post<any>(`${S}/jeeves/command`, { message: m, game_name: 'Studio' }, { timeoutMs: 20000 });
    setReply(r.ok ? (r.data?.reply || 'Done.') : 'Jeeves is unavailable.');
    setMsg(''); setBusy(false); loadOverview();
  };

  const stepKeys = Object.keys(steps);
  const completed = stepKeys.filter((k) => steps[k]?.status === 'completed').length;

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="gs-back" onPress={() => router.back()} style={s.back} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color={GREEN} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>🎛️ CNS Studio</Text>
          <Text style={s.sub}>{oversight?.total_rooms ?? '—'} rooms · {mapData?.total_seats ?? seats?.total_seats ?? '—'} seats</Text>
        </View>
        {busy && <ActivityIndicator color={GREEN} size="small" />}
      </View>

      <View style={s.tabBarWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.tabBar}>
          {TABS.map((t) => (
            <TouchableOpacity key={t} testID={`gs-tab-${t}`} style={[s.tab, tab === t && s.tabActive]} onPress={() => setTab(t)}>
              <Text style={[s.tabTxt, tab === t && s.tabTxtActive]}>{t}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
          {tab === 'Overview' && (
            <>
              <View style={s.statRow}>
                <Stat label="Steps" value={`${completed}/${stepKeys.length || 7}`} color={GREEN} />
                <Stat label="Vault" value={`${oversight?.vault_files ?? 0}`} color={BLUE} />
                <Stat label="Q&A" value={`${oversight?.questionnaire_count ?? 0}`} color="#a78bfa" />
                <Stat label="Rooms" value={`${oversight?.total_rooms ?? 0}`} color="#f59e0b" />
              </View>
              <Text style={s.h2}>⚖️ Governed Pipeline</Text>
              <View style={s.card}>
                {flow.map((st: any, i: number) => (
                  <View key={st.stage} style={s.flowRow}>
                    <View style={[s.flowDot, { backgroundColor: i >= 4 && i <= 6 ? BLUE : GREEN }]}><Text style={s.flowNum}>{i + 1}</Text></View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.flowStage}>{st.stage.replace(/_/g, ' ')}</Text>
                      <Text style={s.flowDesc}>{st.desc}</Text>
                    </View>
                  </View>
                ))}
              </View>
              <Text style={s.h2}>🏛️ Boardroom Ledger</Text>
              <View style={s.card}>
                {ledger.length === 0 ? <Text style={s.empty}>No submissions yet.</Text> : ledger.map((e: any, i: number) => (
                  <View key={i} style={s.ledgerRow}>
                    <View style={[s.badge, { backgroundColor: (VC[e.verdict] || MUTE) + '22', borderColor: VC[e.verdict] || MUTE }]}><Text style={[s.badgeTxt, { color: VC[e.verdict] || MUTE }]}>{e.verdict}</Text></View>
                    <Text style={s.ledgerFile} numberOfLines={1}>{e.game_name} · {e.filename}</Text>
                    <Ionicons name={e.vaulted ? 'lock-closed' : 'remove-circle-outline'} size={14} color={e.vaulted ? GREEN : MUTE} />
                  </View>
                ))}
              </View>
              <Text style={s.h2}>📡 Room Activity</Text>
              <View style={s.card}>
                {activity.length === 0 ? <Text style={s.empty}>No activity yet.</Text> : activity.map((a: any, i: number) => (
                  <View key={i} style={s.actRow}><Text style={s.actEvent}>{a.event}</Text><Text style={s.actRooms} numberOfLines={1}>{(a.rooms || []).join(', ')}</Text></View>
                ))}
              </View>
              <Text style={s.h2}>🧾 Audit Log</Text>
              <View style={s.card}>
                {auditLog.length === 0 ? <Text style={s.empty}>No audited actions yet.</Text> : auditLog.map((e: any, i: number) => (
                  <View key={i} style={s.actRow}>
                    <View style={[s.badge, { backgroundColor: BLUE + '22', borderColor: BLUE }]}><Text style={[s.badgeTxt, { color: BLUE }]}>{e.action}</Text></View>
                    <Text style={s.ledgerFile} numberOfLines={1}>{e.target}</Text>
                    <Text style={s.actRooms} numberOfLines={1}>{e.actor}</Text>
                  </View>
                ))}
              </View>
              <TouchableOpacity testID="gs-open-storage" style={[s.bigBtn, { backgroundColor: '#a78bfa', flex: 0, marginTop: 14 }]} onPress={() => router.push('/storage')}>
                <Text style={s.bigBtnTxt}>💾 Open Storage Dashboard</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="gs-open-mission" style={[s.bigBtn, { backgroundColor: BLUE, flex: 0, marginTop: 10 }]} onPress={() => router.push('/mission-control')}>
                <Text style={[s.bigBtnTxt, { color: '#fff' }]}>🛰️ MasterMap Control Center</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="gs-open-jury" style={[s.bigBtn, { backgroundColor: '#f59e0b', flex: 0, marginTop: 10 }]} onPress={() => router.push('/jury-room')}>
                <Text style={s.bigBtnTxt}>⚖️ Jury Room (adjudication)</Text>
              </TouchableOpacity>
            </>
          )}

          {tab === 'Build' && (
            <>
              <Text style={s.h2}>📝 Intake Questionnaire</Text>
              <View style={s.card}>
                {questions.map((q: any) => (<Text key={q.id} style={s.qTxt}>• {q.question}</Text>))}
              </View>
              <Text style={s.h2}>☃️ Snowball Steps</Text>
              <View style={s.card}>
                {stepKeys.map((k) => (
                  <View key={k} style={s.stepRow}>
                    <Ionicons name={steps[k]?.status === 'completed' ? 'checkmark-circle' : 'ellipse-outline'} size={18} color={steps[k]?.status === 'completed' ? GREEN : MUTE} />
                    <Text style={s.stepName} numberOfLines={1}>{steps[k]?.step_name || k}</Text>
                    {steps[k]?.status !== 'completed' && (
                      <TouchableOpacity testID={`gs-step-complete-${k}`} style={s.miniBtn} onPress={() => completeStep(k)} disabled={busy}>
                        <Text style={s.miniBtnTxt}>Complete</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                ))}
              </View>
              <Text style={s.h2}>⚒️ Forges & Deploy</Text>
              <View style={s.card}>
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  <TouchableOpacity testID="gs-run-forges" style={[s.bigBtn, { backgroundColor: GREEN }]} onPress={runForges} disabled={busy}><Text style={s.bigBtnTxt}>Run all forges</Text></TouchableOpacity>
                  <TouchableOpacity testID="gs-deploy" style={[s.bigBtn, { backgroundColor: BLUE }]} onPress={deploy} disabled={busy}><Text style={s.bigBtnTxt}>Deploy build</Text></TouchableOpacity>
                </View>
                {!!forgeLog && <Text style={s.reply}>{forgeLog}</Text>}
              </View>
              <Text style={s.h2}>📦 Real Build Artifacts</Text>
              <View style={s.card}>
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  <TouchableOpacity testID="gs-build-web" style={[s.bigBtn, { backgroundColor: GREEN }]} onPress={() => doBuild('web')} disabled={busy}><Text style={s.bigBtnTxt}>Web bundle</Text></TouchableOpacity>
                  <TouchableOpacity testID="gs-build-source" style={[s.bigBtn, { backgroundColor: BLUE }]} onPress={() => doBuild('source')} disabled={busy}><Text style={s.bigBtnTxt}>Source zip</Text></TouchableOpacity>
                </View>
                <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
                  <TouchableOpacity testID="gs-build-desktop" style={[s.bigBtn, { backgroundColor: '#a78bfa' }]} onPress={() => doBuild('desktop')} disabled={busy}><Text style={s.bigBtnTxt}>Desktop (Linux)</Text></TouchableOpacity>
                  <TouchableOpacity testID="gs-build-godot" style={[s.bigBtn, { backgroundColor: '#f59e0b' }]} onPress={() => doBuild('godot')} disabled={busy}><Text style={s.bigBtnTxt}>Godot project</Text></TouchableOpacity>
                </View>
                <TouchableOpacity testID="gs-ship" style={[s.bigBtn, { backgroundColor: GREEN, flex: 0, marginTop: 10 }]} onPress={doShip} disabled={busy}><Text style={s.bigBtnTxt}>🚀 Ship It (build → commit → push)</Text></TouchableOpacity>
                {!!buildMsg && <Text style={s.reply}>{buildMsg}</Text>}
                {builds.slice(0, 6).map((bd: any, i: number) => (
                  <TouchableOpacity key={`${bd.build_id}-${i}`} style={s.ledgerRow} onPress={() => openDownload(bd.download_url)}>
                    <Ionicons name="cloud-download-outline" size={16} color={GREEN} />
                    <Text style={s.ledgerFile} numberOfLines={1}>{bd.kind} · {bd.filename} · {(bd.size_bytes / 1024).toFixed(1)}KB</Text>
                    <Ionicons name="chevron-forward" size={14} color={MUTE} />
                  </TouchableOpacity>
                ))}
              </View>
            </>
          )}

          {tab === 'Ship' && (
            <>
              <Text style={s.h2}>🚀 Autonomous Workflow — Prompt → Ship</Text>
              <View style={s.card}>
                <Text style={s.qTxt}>Describe the game. Jeeves runs Testing → Concept → Production → Reflection with cross-iteration memory, then deploys a packaged build to the JeevesVault.</Text>
                <TextInput
                  testID="gs-wf-prompt" style={[s.input, { marginTop: 10, minHeight: 72, textAlignVertical: 'top' }]}
                  value={wfPrompt} onChangeText={setWfPrompt} multiline
                  placeholder="e.g. A cozy farming sim with crafting and co-op…" placeholderTextColor={MUTE}
                  editable={!wfBusy}
                />
                <View style={s.chipRow}>
                  {[2, 3, 4, 5, 6].map((n) => (
                    <TouchableOpacity key={n} testID={`gs-wf-iter-${n}`} onPress={() => setWfIters(n)} disabled={wfBusy}
                      style={[s.chip, wfIters === n && { backgroundColor: GREEN }]}>
                      <Text style={[s.chipTxt, wfIters === n && { color: '#04120a', fontWeight: '800' }]}>{n} iters</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity testID="gs-wf-run" style={[s.bigBtn, { backgroundColor: GREEN, flex: 0, marginTop: 12 }]} onPress={runWorkflow} disabled={wfBusy}>
                  {wfBusy ? <ActivityIndicator color="#04120a" size="small" /> : <Text style={s.bigBtnTxt}>▶ Run autonomous workflow</Text>}
                </TouchableOpacity>
                {!!wfErr && <Text style={[s.reply, { color: '#ef4444' }]}>{wfErr}</Text>}
              </View>

              {wfResult && (
                <>
                  <Text style={s.h2}>📊 Result</Text>
                  <View style={s.card}>
                    <View style={s.statRow}>
                      <Stat label="Final Q" value={`${Math.round((wfResult.final_quality ?? 0) * 100)}%`} color={GREEN} />
                      <Stat label="Iters" value={`${wfResult.iterations_run ?? 0}`} color={BLUE} />
                      <Stat label="Deploy" value={wfResult.deploy_ready ? 'Ready' : 'Hold'} color={wfResult.deploy_ready ? GREEN : '#f59e0b'} />
                      <Stat label="Strategy" value={`${wfResult.final_strategy ?? '—'}`} color="#a78bfa" />
                    </View>
                    <Text style={[s.qTxt, { marginTop: 4 }]}>🎮 {wfResult.genre} · {wfResult.scope} · {(wfResult.focus_systems || []).join(', ')}</Text>
                    <Text style={[s.kTopic, { marginTop: 8 }]}>Quality trend</Text>
                    <Text style={s.kText}>{(wfResult.quality_history || []).map((q: number) => `${Math.round(q * 100)}%`).join('  →  ')}</Text>
                    {(wfResult.iterations || []).map((it: any) => (
                      <View key={it.iteration} style={s.ledgerRow}>
                        <View style={[s.badge, { backgroundColor: BLUE + '22', borderColor: BLUE }]}><Text style={[s.badgeTxt, { color: BLUE }]}>{it.strategy}</Text></View>
                        <Text style={s.ledgerFile} numberOfLines={1}>Iteration {it.iteration}</Text>
                        <Text style={s.actRooms}>{Math.round((it.quality ?? 0) * 100)}%</Text>
                      </View>
                    ))}
                    {wfResult.deployment?.package && (
                      <TouchableOpacity testID="gs-wf-download" style={[s.bigBtn, { backgroundColor: BLUE, flex: 0, marginTop: 12 }]} onPress={() => downloadPackage(wfResult.deployment.package)}>
                        <Text style={[s.bigBtnTxt, { color: '#fff' }]}>⬇ Download {wfResult.deployment.package.package_name}</Text>
                      </TouchableOpacity>
                    )}
                    {!!dlMsg && <Text style={s.reply}>{dlMsg}</Text>}
                  </View>
                </>
              )}

              <Text style={s.h2}>📦 JeevesVault ({vaultPkgs.length})</Text>
              <View style={s.card}>
                {vaultPkgs.length === 0 ? <Text style={s.empty}>No packages yet — run a workflow to ship one.</Text> : vaultPkgs.map((p: any) => (
                  <TouchableOpacity key={p.package_id} testID={`gs-vault-pkg-${p.package_id}`} style={s.ledgerRow} onPress={() => downloadPackage(p)}>
                    <Ionicons name="cube-outline" size={16} color={GREEN} />
                    <Text style={s.ledgerFile} numberOfLines={1}>{p.package_name} · {(p.size_bytes / 1024).toFixed(1)}KB · Q{Math.round((p.quality ?? 0) * 100)}%</Text>
                    <Ionicons name="cloud-download-outline" size={15} color={MUTE} />
                  </TouchableOpacity>
                ))}
              </View>
            </>
          )}

          {tab === 'Vault' && (
            <>
              <Text style={s.h2}>🗄️ Unified Vault (mirrored)</Text>
              <UnifiedVault embedded onContinueInBuild={() => setTab('Build')} />
              <Text style={s.h2}>📒 Per-Build Context Ledger</Text>
              <View style={s.card}>
                {buildLedger.length === 0 ? <Text style={s.empty}>No build ledgers yet.</Text> : buildLedger.slice(0, 15).map((b: any, i: number) => (
                  <View key={`${b.build_id || b._id || i}`} style={s.ledgerRow}>
                    <Ionicons name="document-text-outline" size={15} color={BLUE} />
                    <Text style={s.ledgerFile} numberOfLines={1}>{b.build_id || b._id || 'build'}</Text>
                    <Text style={s.actRooms}>{b.events ?? b.event_count ?? b.systems_count ?? 0} events</Text>
                  </View>
                ))}
              </View>
            </>
          )}

          {tab === 'Map' && (
            <>
              <View style={s.statRow}>
                <Stat label="Rooms" value={`${mapData?.rooms ?? 0}`} color={GREEN} />
                <Stat label="Seats" value={`${mapData?.total_seats ?? 0}`} color={BLUE} />
                <Stat label="Roles" value={`${mapData?.total_roles ?? 0}`} color="#a78bfa" />
                <Stat label="Skills" value={`${mapData?.total_skills ?? 0}`} color="#f59e0b" />
              </View>
              <Text style={s.h2}>🧠 Jeeves MasterMap</Text>
              <View style={s.card}>
                {(mapData?.mastermap?.new_components || []).length === 0 ? <Text style={s.empty}>MasterMap loaded ({mapData?.mastermap?.versions ?? 0} versions).</Text> :
                  (mapData?.mastermap?.new_components || []).map((c: string, i: number) => (<Text key={i} style={s.qTxt}>◆ {c}</Text>))}
              </View>
              <Text style={s.h2}>🪑 Seat & Role Categories</Text>
              <View style={s.card}>
                <Text style={s.qTxt}>{seats?.total_categories ?? 0} categories × 100 seats = {seats?.total_seats ?? 0} role-seats</Text>
              </View>
              <Text style={s.h2}>🎓 Master Skill Bank</Text>
              <View style={s.card}>
                {Object.keys(skills || {}).map((c) => (
                  <Text key={c} style={s.qTxt}>• {c.replace(/_/g, ' ')} ({(skills[c] || []).length})</Text>
                ))}
              </View>
              <Text style={s.h2}>🔧 In-Room Systems ({systems?.live ?? 0}/{systems?.total ?? 0} live)</Text>
              <View style={s.card}>
                {Object.entries(systems?.systems || {}).map(([name, st]: any) => (
                  <View key={name} style={s.sysRow}>
                    <View style={[s.sysDot, { backgroundColor: st === 'live' ? GREEN : MUTE }]} />
                    <Text style={s.sysName}>{name.replace(/_/g, ' ')}</Text>
                    <Text style={[s.sysStat, { color: st === 'live' ? GREEN : MUTE }]}>{st}</Text>
                  </View>
                ))}
              </View>
            </>
          )}

          {tab === 'Jeeves' && (
            <>
              <Text style={s.h2}>🤵 Ask Jeeves</Text>
              <View style={s.card}>
                <View style={s.inputRow}>
                  <TextInput testID="gs-jeeves-input" style={s.input} value={msg} onChangeText={setMsg}
                    placeholder="run forges · deploy · rooms · mechanics for a roguelike…" placeholderTextColor={MUTE}
                    onSubmitEditing={() => sendCommand()} editable={!busy} />
                  <TouchableOpacity testID="gs-jeeves-send" style={s.sendBtn} onPress={() => sendCommand()} disabled={busy}>
                    {busy ? <ActivityIndicator color="#000" size="small" /> : <Ionicons name="send" size={18} color="#000" />}
                  </TouchableOpacity>
                </View>
                <View style={s.chipRow}>
                  {['run forges', 'deploy Studio', 'roguelike mechanics', 'rooms', 'oversight'].map((q) => (
                    <TouchableOpacity key={q} style={s.chip} onPress={() => sendCommand(q)} disabled={busy}><Text style={s.chipTxt}>{q}</Text></TouchableOpacity>
                  ))}
                </View>
                {!!reply && <Text testID="gs-jeeves-reply" style={s.reply}>{reply}</Text>}
              </View>
              <Text style={s.h2}>🧠 Strategic Planner (Tier-3 · long-horizon)</Text>
              <View style={s.card}>
                <TextInput testID="gs-plan-objective" style={s.input} value={planObjective} onChangeText={setPlanObjective}
                  placeholder="objective…" placeholderTextColor={MUTE} editable={!busy} />
                <TouchableOpacity testID="gs-plan-run" style={[s.bigBtn, { backgroundColor: '#a78bfa', flex: 0, marginTop: 10 }]} onPress={runStrategicPlan} disabled={busy}>
                  <Text style={s.bigBtnTxt}>{busy ? 'Planning…' : '🧭 Generate strategic plan'}</Text>
                </TouchableOpacity>
                {plan && (
                  <View style={{ marginTop: 12 }}>
                    <View style={s.statRow}>
                      <Stat label="Agents" value={`${plan.forecast?.estimated_agents_needed ?? 0}`} color={GREEN} />
                      <Stat label="Success" value={`${Math.round((plan.simulation?.success_probability ?? 0) * 100)}%`} color={BLUE} />
                      <Stat label="Risk" value={`${Math.round((plan.risk?.final_risk ?? 0) * 100)}%`} color="#f59e0b" />
                      <Stat label="Delay" value={`${plan.simulation?.expected_delay_days ?? 0}d`} color="#ef4444" />
                    </View>
                    <Text style={[s.qTxt, { marginTop: 4 }]}>🧭 {plan.simulation?.recommendation}</Text>
                    <Text style={[s.kTopic, { marginTop: 8 }]}>Critical path</Text>
                    <Text style={s.kText}>{(plan.dependency?.critical_path || []).join('  →  ')}</Text>
                    <Text style={[s.kTopic, { marginTop: 8 }]}>Delegation workflow</Text>
                    {(plan.workflow || []).map((w: any) => (
                      <View key={w.step} style={s.ledgerRow}>
                        <View style={[s.badge, { backgroundColor: BLUE + '22', borderColor: BLUE }]}><Text style={[s.badgeTxt, { color: BLUE }]}>{w.assign_to}</Text></View>
                        <Text style={s.ledgerFile} numberOfLines={1}>{w.step}. {w.milestone}</Text>
                        <Text style={s.actRooms}>{w.budget_hours}h</Text>
                      </View>
                    ))}
                  </View>
                )}
              </View>
              <Text style={s.h2}>📚 Jeeves Trained Brain ({knowledge.length})</Text>
              <View style={s.card}>
                {knowledge.slice(0, 30).map((k: any, i: number) => (
                  <View key={i} style={{ paddingVertical: 5 }}>
                    <Text style={s.kTopic}>{k.topic}</Text>
                    <Text style={s.kText} numberOfLines={2}>{k.text}</Text>
                  </View>
                ))}
              </View>
            </>
          )}

          {tab === 'Learn' && (
            <>
              <View style={s.statRow}>
                <Stat label="Brain" value={`${brain?.knowledge_count ?? 0}`} color={GREEN} />
                <Stat label="Fill" value={`${brain?.fill_percent ?? 0}%`} color={BLUE} />
                <Stat label="Skills" value={`${brain?.skill_count ?? 0}`} color="#a78bfa" />
                <Stat label="APIs" value={`${apiTotal}`} color="#f59e0b" />
              </View>
              <Text style={s.h2}>🧩 Teach Jeeves (query free APIs)</Text>
              <View style={s.card}>
                <View style={s.inputRow}>
                  <TextInput testID="gs-learn-input" style={s.input} value={learnQ} onChangeText={setLearnQ}
                    placeholder="define entropy · what is a roguelike · repos for pathfinding…" placeholderTextColor={MUTE}
                    onSubmitEditing={() => teachJeeves()} editable={!busy} />
                  <TouchableOpacity testID="gs-learn-send" style={s.sendBtn} onPress={() => teachJeeves()} disabled={busy}>
                    {busy ? <ActivityIndicator color="#000" size="small" /> : <Ionicons name="cloud-download" size={18} color="#000" />}
                  </TouchableOpacity>
                </View>
                <View style={s.chipRow}>
                  {['what is a roguelike', 'define entropy', 'repos for pathfinding', 'papers on procedural generation'].map((q) => (
                    <TouchableOpacity key={q} style={s.chip} onPress={() => teachJeeves(q)} disabled={busy}><Text style={s.chipTxt}>{q}</Text></TouchableOpacity>
                  ))}
                </View>
                {!!learnRes && <Text testID="gs-learn-result" style={s.reply}>{learnRes}</Text>}
              </View>
              <Text style={s.h2}>♻️ Self-Improvement</Text>
              <View style={s.card}>
                <TouchableOpacity testID="gs-self-improve" style={[s.bigBtn, { backgroundColor: GREEN, flex: 0 }]} onPress={selfImprove} disabled={busy}>
                  <Text style={s.bigBtnTxt}>Run reflect-and-improve cycle</Text>
                </TouchableOpacity>
                {!!improveRes && <Text style={s.reply}>{improveRes}</Text>}
              </View>
              <Text style={s.h2}>🧠 Brain by Domain</Text>
              <View style={s.card}>
                {Object.entries(brain?.by_domain || {}).map(([d, n]: any) => (
                  <View key={d} style={s.sysRow}>
                    <View style={[s.sysDot, { backgroundColor: n > 0 ? GREEN : MUTE }]} />
                    <Text style={s.sysName}>{d.replace(/_/g, ' ')}</Text>
                    <Text style={[s.sysStat, { color: n > 0 ? GREEN : MUTE }]}>{n}</Text>
                  </View>
                ))}
              </View>
              <Text style={s.h2}>🌐 Free API Catalog ({apiTotal})</Text>
              <View style={s.card}>
                <Text style={s.qTxt}>{apiCats.join(' · ')}</Text>
              </View>
            </>
          )}

          {tab === 'Observe' && (
            <>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={[s.sysDot, { backgroundColor: obsLive ? GREEN : MUTE }]} />
                  <Text style={s.qTxt}>{obsLive ? 'Live · refreshing every 5s' : 'Snapshot'}</Text>
                </View>
                <TouchableOpacity testID="gs-obs-live" style={[s.chip, obsLive && { backgroundColor: GREEN }]} onPress={() => { setObsLive((v) => !v); loadObserve(); }}>
                  <Text style={[s.chipTxt, obsLive && { color: '#04120a', fontWeight: '800' }]}>{obsLive ? 'Live ON' : 'Go Live'}</Text>
                </TouchableOpacity>
              </View>
              <View style={s.statRow}>
                <Stat label="Health" value={`${obs?.health_score ?? 0}%`} color={GREEN} />
                <Stat label="Progress" value={`${obs?.snowball?.progress_percent ?? 0}%`} color={BLUE} />
                <Stat label="Accept" value={`${obs?.jury?.accept_rate ?? 0}%`} color="#a78bfa" />
                <Stat label="Events" value={`${obs?.room_events ?? 0}`} color="#f59e0b" />
              </View>
              <Text style={s.h2}>🛡️ Resilience Circuits</Text>
              <View style={s.card}>
                {Object.keys(circuits || {}).length === 0 ? (
                  <View style={s.sysRow}><View style={[s.sysDot, { backgroundColor: GREEN }]} /><Text style={s.sysName}>All API circuits closed (healthy)</Text><Text style={[s.sysStat, { color: GREEN }]}>ok</Text></View>
                ) : Object.entries(circuits).map(([bucket, st]: any) => {
                  const state = st?.state || 'closed';
                  const col = state === 'closed' ? GREEN : state === 'half_open' ? '#f59e0b' : '#ef4444';
                  return (
                    <View key={bucket} style={s.sysRow}>
                      <View style={[s.sysDot, { backgroundColor: col }]} />
                      <Text style={s.sysName} numberOfLines={1}>{bucket}</Text>
                      <Text style={[s.sysStat, { color: col }]}>{state} · {st?.failures ?? 0} fails</Text>
                    </View>
                  );
                })}
              </View>
              <Text style={s.h2}>⚖️ Jury Decision Analytics</Text>
              <View style={s.card}>
                {['accept', 'revise', 'reject'].map((v) => (
                  <View key={v} style={s.sysRow}>
                    <View style={[s.sysDot, { backgroundColor: VC[v] }]} />
                    <Text style={s.sysName}>{v}</Text>
                    <Text style={[s.sysStat, { color: VC[v] }]}>{obs?.jury?.verdicts?.[v] ?? 0}</Text>
                  </View>
                ))}
                <Text style={[s.qTxt, { marginTop: 6 }]}>Total decisions: {obs?.jury?.total_decisions ?? 0}</Text>
              </View>
              <Text style={s.h2}>⚒️ Forge Activity</Text>
              <View style={s.card}>
                {Object.entries(obs?.forge_activity || {}).length === 0 ? <Text style={s.empty}>No forge activity yet.</Text> :
                  Object.entries(obs?.forge_activity || {}).map(([f, n]: any) => (
                    <View key={f} style={s.sysRow}><View style={[s.sysDot, { backgroundColor: GREEN }]} /><Text style={s.sysName}>{f}</Text><Text style={[s.sysStat, { color: GREEN }]}>{n}</Text></View>
                  ))}
              </View>
              <Text style={s.h2}>🔐 Storage & Knowledge</Text>
              <View style={s.card}>
                <Text style={s.qTxt}>• Vault files: {obs?.vault?.files ?? 0} (🔒 encrypted at rest, persisted)</Text>
                <Text style={s.qTxt}>• Knowledge: {obs?.knowledge?.total ?? 0} (acquired {obs?.knowledge?.acquired ?? 0} · learned {obs?.knowledge?.learned ?? 0})</Text>
                <Text style={s.qTxt}>• Snowball: {obs?.snowball?.completed ?? 0}/{obs?.snowball?.total ?? 0} steps</Text>
              </View>
              <Text style={s.h2}>💚 System Health</Text>
              <View style={s.card}>
                {Object.entries(obs?.health || {}).map(([c, ok]: any) => (
                  <View key={c} style={s.sysRow}>
                    <View style={[s.sysDot, { backgroundColor: ok ? GREEN : '#ef4444' }]} />
                    <Text style={s.sysName}>{c.replace(/_/g, ' ')}</Text>
                    <Text style={[s.sysStat, { color: ok ? GREEN : '#ef4444' }]}>{ok ? 'up' : 'down'}</Text>
                  </View>
                ))}
              </View>
              <Text style={s.h2}>🚨 Error Recovery & Alarms {unresolvedAlarms > 0 ? `(${unresolvedAlarms} active)` : ''}</Text>
              <View style={s.card}>
                {alarms.length === 0 ? <Text style={s.empty}>No alarms — system nominal.</Text> : alarms.slice(0, 10).map((a: any, i: number) => {
                  const col = a.severity === 'error' ? '#ef4444' : a.severity === 'info' ? BLUE : '#f59e0b';
                  return (
                    <View key={i} style={s.actRow}>
                      <View style={[s.badge, { backgroundColor: col + '22', borderColor: col }]}><Text style={[s.badgeTxt, { color: col }]}>{a.severity}</Text></View>
                      <Text style={s.ledgerFile} numberOfLines={1}>{a.kind}{a.detail ? ` · ${a.detail}` : ''}</Text>
                      <Ionicons name={a.resolved ? 'checkmark-circle' : 'alert-circle'} size={14} color={a.resolved ? GREEN : col} />
                    </View>
                  );
                })}
                <TouchableOpacity testID="gs-auto-recover" style={[s.bigBtn, { backgroundColor: '#f59e0b', flex: 0, marginTop: 10 }]} onPress={autoRecover} disabled={busy}>
                  <Text style={s.bigBtnTxt}>🔧 Auto-recover (rollback last vault)</Text>
                </TouchableOpacity>
                {!!recoverMsg && <Text style={s.reply}>{recoverMsg}</Text>}
              </View>
              <Text style={s.h2}>📜 Universal Logs ({uniLogs.length})</Text>
              <View style={s.card}>
                {uniLogs.length === 0 ? <Text style={s.empty}>No logs yet.</Text> : uniLogs.slice(0, 15).map((l: any, i: number) => {
                  const col = l.severity === 'error' ? '#ef4444' : l.severity === 'warning' ? '#f59e0b' : l.component === 'recovery' ? BLUE : '#a78bfa';
                  return (
                    <View key={i} style={s.actRow}>
                      <View style={[s.badge, { backgroundColor: col + '22', borderColor: col }]}><Text style={[s.badgeTxt, { color: col }]}>{l.component}</Text></View>
                      <Text style={s.ledgerFile} numberOfLines={1}>{l.event}{l.detail ? ` · ${l.detail}` : ''}</Text>
                    </View>
                  );
                })}
              </View>
              <Text style={s.h2}>🔑 Session (RBAC / Auth)</Text>
              <View style={s.card}>
                <View style={s.sysRow}>
                  <Ionicons name="person-circle" size={18} color={GREEN} />
                  <Text style={s.sysName} numberOfLines={1}>{authUser?.email || authUser?.name || 'Signed in'}</Text>
                  <View style={[s.badge, { backgroundColor: GREEN + '22', borderColor: GREEN }]}><Text style={[s.badgeTxt, { color: GREEN }]}>{authRole}</Text></View>
                </View>
                <Text style={[s.qTxt, { marginTop: 4 }]}>Enforcement: {enforced ? 'ON (production)' : 'OFF (dev mode)'}</Text>
                <TouchableOpacity testID="gs-auth-logout" style={[s.bigBtn, { backgroundColor: '#ef4444', flex: 0, marginTop: 10 }]} onPress={doLogout} disabled={logoutBusy}>
                  <Text style={[s.bigBtnTxt, { color: '#fff' }]}>{logoutBusy ? 'Signing out…' : 'Sign out'}</Text>
                </TouchableOpacity>
              </View>
              {authRole === 'admin' && (
                <>
                  <Text style={s.h2}>👑 Role Management (admin)</Text>
                  <View style={s.card}>
                    <Text style={[s.qTxt, { marginBottom: 6 }]}>Promote a user (e.g. a Google-provisioned viewer) to editor/admin.</Text>
                    <TextInput testID="gs-role-email" style={s.input} value={roleEmail} onChangeText={setRoleEmail} placeholder="user@email.com" placeholderTextColor={MUTE} autoCapitalize="none" keyboardType="email-address" />
                    <View style={s.chipRow}>
                      {(['viewer', 'editor', 'admin'] as const).map((r) => (
                        <TouchableOpacity key={r} testID={`gs-role-${r}`} style={[s.chip, roleValue === r && { backgroundColor: GREEN }]} onPress={() => setRoleValue(r)}>
                          <Text style={[s.chipTxt, roleValue === r && { color: '#04120a', fontWeight: '800' }]}>{r}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                    <TouchableOpacity testID="gs-role-apply" style={[s.bigBtn, { backgroundColor: GREEN, flex: 0, marginTop: 10 }]} onPress={updateRole} disabled={busy}>
                      <Text style={s.bigBtnTxt}>Apply role</Text>
                    </TouchableOpacity>
                    {!!roleMsg && <Text style={s.reply}>{roleMsg}</Text>}
                  </View>
                </>
              )}
            </>
          )}

          {tab === 'Agents' && (
            <>
              <View style={s.statRow}>
                <Stat label="Active" value={`${rtStatus?.active_agents ?? 0}`} color={GREEN} />
                <Stat label="Msgs" value={`${rtStatus?.messages ?? 0}`} color={BLUE} />
                <Stat label="Open" value={`${rtStatus?.tasks_open ?? 0}`} color="#f59e0b" />
                <Stat label="Done" value={`${rtStatus?.tasks_done ?? 0}`} color="#a78bfa" />
              </View>
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 6 }}>
                <TouchableOpacity testID="gs-spawn" style={[s.bigBtn, { backgroundColor: GREEN }]} onPress={spawnAgents} disabled={busy}><Text style={s.bigBtnTxt}>Spawn 3 agents</Text></TouchableOpacity>
                <TouchableOpacity testID="gs-delegate" style={[s.bigBtn, { backgroundColor: BLUE }]} onPress={delegate} disabled={busy}><Text style={s.bigBtnTxt}>Delegate task</Text></TouchableOpacity>
              </View>
              <TouchableOpacity testID="gs-delegate-execute" style={[s.bigBtn, { backgroundColor: '#a78bfa', flex: 0, marginTop: 10 }]} onPress={delegateExecute} disabled={busy}>
                <Text style={s.bigBtnTxt}>⚡ Delegate & Execute (live)</Text>
              </TouchableOpacity>
              <Text style={s.h2}>💓 Agent Health (heartbeat · self-healing)</Text>
              <View style={s.card}>
                <View style={s.statRow}>
                  <Stat label="Healthy" value={`${agentHealth?.healthy ?? 0}`} color={GREEN} />
                  <Stat label="Stale" value={`${agentHealth?.stale ?? 0}`} color="#f59e0b" />
                  <Stat label="Dead" value={`${agentHealth?.dead ?? 0}`} color="#ef4444" />
                </View>
                <Text style={[s.qTxt, { marginTop: 6 }]}>🔁 Reaper auto-restarts dead agents{agentHealth?.reaped ? ` · healed ${agentHealth.reaped} last check` : ''}</Text>
              </View>
              <Text style={s.h2}>💬 Agent Group Chat ({groupchat.length})</Text>
              <View style={s.card}>
                {groupchat.length === 0 ? <Text style={s.empty}>No messages yet — run “Delegate & Execute”.</Text> : groupchat.map((m: any, i: number) => (
                  <View key={m.id || i} style={{ paddingVertical: 5, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' }}>
                    <Text style={s.kTopic}>{m.role || m.agent_id}</Text>
                    <Text style={s.kText} numberOfLines={3}>{m.content}</Text>
                  </View>
                ))}
              </View>
              <Text style={s.h2}>🛰️ Agent GPS Positions ({positions?.active_rooms ?? 0} rooms)</Text>
              <View style={s.card}>
                {(positions?.positions || []).length === 0 ? <Text style={s.empty}>No positioned agents.</Text> : (positions.positions).slice(0, 12).map((p: any, i: number) => {
                  const col = p.health > 0.6 ? GREEN : p.health > 0.3 ? '#f59e0b' : '#ef4444';
                  return (
                    <View key={p.agent_id || i} style={s.actRow}>
                      <View style={[s.sysDot, { backgroundColor: col }]} />
                      <Text style={s.actEvent} numberOfLines={1}>{p.room_id}</Text>
                      <Text style={s.actRooms} numberOfLines={1}>{p.category} · {p.task}</Text>
                      <Text style={[s.badgeTxt, { color: col }]}>{Math.round(p.health * 100)}%</Text>
                    </View>
                  );
                })}
              </View>
              <Text style={s.h2}>🛠️ Agent Tool Bank ({tools.length})</Text>
              <View style={s.card}>
                {tools.length === 0 ? <Text style={s.empty}>No tools registered.</Text> : tools.map((t: any, i: number) => (
                  <View key={t.tool_id || i} style={s.ledgerRow}>
                    <Ionicons name={t.deprecated ? 'close-circle' : 'build'} size={15} color={t.deprecated ? '#ef4444' : GREEN} />
                    <Text style={s.ledgerFile} numberOfLines={1}>{t.name} · v{t.version}</Text>
                    <Text style={s.actRooms}>{Math.round((t.stats?.success_rate ?? 0) * 100)}% · {t.stats?.uses ?? 0} uses</Text>
                  </View>
                ))}
                <TouchableOpacity testID="gs-tool-combo" style={[s.bigBtn, { backgroundColor: BLUE, flex: 0, marginTop: 10 }]} onPress={scoreCombo} disabled={busy}>
                  <Text style={[s.bigBtnTxt, { color: '#fff' }]}>⚗️ Score tool-combo synergy</Text>
                </TouchableOpacity>
                {!!comboMsg && <Text style={s.reply}>{comboMsg}</Text>}
              </View>
              <Text style={s.h2}>🤖 Active Agents ({agentList.length})</Text>
              <View style={s.card}>
                {agentList.length === 0 ? <Text style={s.empty}>No agents spawned yet.</Text> : agentList.map((a: any) => (
                  <View key={a.agent_id} style={s.actRow}>
                    <View style={[s.sysDot, { backgroundColor: a.status === 'active' ? GREEN : MUTE }]} />
                    <Text style={s.actEvent} numberOfLines={1}>{a.category}</Text>
                    <Text style={s.actRooms} numberOfLines={1}>{a.role?.role_name || a.agent_id}</Text>
                  </View>
                ))}
              </View>
              <Text style={s.h2}>📋 Delegated Tasks</Text>
              <View style={s.card}>
                {rtTasks.length === 0 ? <Text style={s.empty}>No tasks yet.</Text> : rtTasks.map((t: any) => (
                  <View key={t.task_id} style={s.ledgerRow}>
                    <View style={[s.badge, { backgroundColor: (t.status === 'done' ? GREEN : '#f59e0b') + '22', borderColor: t.status === 'done' ? GREEN : '#f59e0b' }]}><Text style={[s.badgeTxt, { color: t.status === 'done' ? GREEN : '#f59e0b' }]}>{t.status}</Text></View>
                    <Text style={s.ledgerFile} numberOfLines={1}>{t.task}</Text>
                  </View>
                ))}
              </View>
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (<View style={s.stat}><Text style={[s.statVal, { color }]}>{value}</Text><Text style={s.statLbl}>{label}</Text></View>);
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937', gap: 10 },
  back: { padding: 2 },
  title: { color: '#f1f5f9', fontSize: 17, fontWeight: '700' },
  sub: { color: MUTE, fontSize: 12, marginTop: 1 },
  tabBarWrap: { paddingTop: 10 },
  tabBar: { flexDirection: 'row', paddingHorizontal: 12, gap: 8 },
  tab: { paddingVertical: 8, paddingHorizontal: 16, borderRadius: 10, backgroundColor: CARD, alignItems: 'center' },
  tabActive: { backgroundColor: GREEN },
  tabTxt: { color: MUTE, fontSize: 12, fontWeight: '700' },
  tabTxtActive: { color: '#04120a' },
  statRow: { flexDirection: 'row', gap: 8, marginBottom: 6 },
  stat: { flex: 1, backgroundColor: CARD, borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  statVal: { fontSize: 17, fontWeight: '800' },
  statLbl: { color: MUTE, fontSize: 11, marginTop: 2 },
  h2: { color: '#e2e8f0', fontSize: 14, fontWeight: '700', marginTop: 18, marginBottom: 8 },
  card: { backgroundColor: CARD, borderRadius: 14, padding: 12 },
  flowRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6 },
  flowDot: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  flowNum: { color: '#000', fontSize: 12, fontWeight: '800' },
  flowStage: { color: '#f1f5f9', fontSize: 13, fontWeight: '600', textTransform: 'capitalize' },
  flowDesc: { color: MUTE, fontSize: 11, marginTop: 1 },
  ledgerRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  badge: { borderRadius: 6, borderWidth: 1, paddingHorizontal: 7, paddingVertical: 2 },
  badgeTxt: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  ledgerFile: { flex: 1, color: '#cbd5e1', fontSize: 12 },
  actRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 5 },
  actEvent: { color: BLUE, fontSize: 12, fontWeight: '600', width: 130 },
  actRooms: { flex: 1, color: MUTE, fontSize: 11 },
  qTxt: { color: '#cbd5e1', fontSize: 12, paddingVertical: 3, lineHeight: 17 },
  stepRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  stepName: { flex: 1, color: '#e2e8f0', fontSize: 13 },
  miniBtn: { backgroundColor: '#1e293b', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 },
  miniBtnTxt: { color: GREEN, fontSize: 11, fontWeight: '700' },
  bigBtn: { flex: 1, borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  bigBtnTxt: { color: '#04120a', fontSize: 13, fontWeight: '800' },
  sysRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  sysDot: { width: 8, height: 8, borderRadius: 4 },
  sysName: { flex: 1, color: '#cbd5e1', fontSize: 12, textTransform: 'capitalize' },
  sysStat: { fontSize: 11, fontWeight: '700' },
  inputRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  input: { flex: 1, backgroundColor: '#0b1220', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: '#f1f5f9', fontSize: 13, borderWidth: StyleSheet.hairlineWidth, borderColor: '#243043' },
  sendBtn: { backgroundColor: GREEN, width: 42, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  chip: { backgroundColor: '#1e293b', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  chipTxt: { color: '#cbd5e1', fontSize: 11 },
  reply: { color: GREEN, fontSize: 13, marginTop: 12, lineHeight: 19 },
  kTopic: { color: BLUE, fontSize: 11, fontWeight: '700' },
  kText: { color: MUTE, fontSize: 11, marginTop: 1, lineHeight: 15 },
  empty: { color: MUTE, fontSize: 12, fontStyle: 'italic' },
});
