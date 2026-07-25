/**
 * /mission-control — MasterMap Control Center.
 * One live "mission control" view unifying the whole CNS: runtime status,
 * agent GPS positions, heartbeat health (self-healing), active strategic plans,
 * and the universal log feed. Read-only, auto-refreshing.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl, TextInput, Platform, Alert, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import api from '../src/utils/apiClient';
import ChurnPanel from '../src/components/ChurnPanel';
import Svg, { Polyline, Circle, Line as SvgLine, Rect } from 'react-native-svg';

const GREEN = '#22c55e';
const BLUE = '#3b82f6';
const PURPLE = '#a78bfa';
const AMBER = '#f59e0b';
const RED = '#ef4444';
const CARD = '#111827';
const BG = '#0b1220';
const MUTE = '#94a3b8';

const RT = '/api/gameforge/runtime';
const S = '/api/gameforge/studio';
const PLAN = '/api/gameforge/planning';

// System-IQ growth sparkline — charts the fabric's recent_growth IQ series so
// the self-learning progress is visible at a glance.
function IqSparkline({ points }: { points: number[] }) {
  const W = 300, H = 64, PAD = 6;
  if (!points || points.length < 2) {
    return <Text style={s.roomMeta}>Emit through Jeeves/agents to grow System-IQ…</Text>;
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = Math.max(1, max - min);
  const stepX = (W - PAD * 2) / (points.length - 1);
  const coords = points.map((p, i) => {
    const x = PAD + i * stepX;
    const y = H - PAD - ((p - min) / span) * (H - PAD * 2);
    return { x, y };
  });
  const poly = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const last = coords[coords.length - 1];
  return (
    <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
      <SvgLine x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="#1f2937" strokeWidth={1} />
      <Polyline points={poly} fill="none" stroke={PURPLE} strokeWidth={2}
        strokeLinejoin="round" strokeLinecap="round" />
      <Circle cx={last.x} cy={last.y} r={3.5} fill={GREEN} />
    </Svg>
  );
}

export default function MissionControl() {
  const router = useRouter();
  const [status, setStatus] = React.useState<any>(null);
  const [health, setHealth] = React.useState<any>(null);
  const [positions, setPositions] = React.useState<any>(null);
  const [plans, setPlans] = React.useState<any[]>([]);
  const [logs, setLogs] = React.useState<any[]>([]);
  const [coverage, setCoverage] = React.useState<any>(null);
  const [prood, setProod] = React.useState<any>(null);
  const [saga, setSaga] = React.useState<any>(null);
  const [sagaBusy, setSagaBusy] = React.useState(false);
  const [fabric, setFabric] = React.useState<any>(null);
  const [delta, setDelta] = React.useState<any>(null);
  const [heatmap, setHeatmap] = React.useState<number[][]>([]);
  const [activity, setActivity] = React.useState<any[]>([]);
  const [topEfe, setTopEfe] = React.useState<any[]>([]);
  const [ask, setAsk] = React.useState('');
  const [asking, setAsking] = React.useState(false);
  const [askReply, setAskReply] = React.useState<any>(null);
  const [legions, setLegions] = React.useState<any>(null);
  const [mobilizing, setMobilizing] = React.useState(false);
  const [attachment, setAttachment] = React.useState<any>(null);
  const [activateMsg, setActivateMsg] = React.useState('');
  const [selftest, setSelftest] = React.useState<any>(null);
  const [testing, setTesting] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [live, setLive] = React.useState(false);

  const load = React.useCallback(async () => {
    const [st, h, pos, pl, lg, cov, prd, fab, dl, hm, act, efe, lgn] = await Promise.all([
      api.get<any>(`${RT}/status`), api.get<any>(`${RT}/health`), api.get<any>(`${RT}/positions`),
      api.get<any>(`${PLAN}/plans?limit=6`), api.get<any>(`${S}/logs?limit=18`),
      api.get<any>('/api/gameforge/coverage', { timeoutMs: 20000 }),
      api.get<any>('/api/prood/readiness', { timeoutMs: 25000 }),
      api.get<any>('/api/omega/fabric', { timeoutMs: 20000 }),
      api.get<any>('/api/omega/delta/stats'),
      api.get<any>('/api/omega/delta/heatmap?cells=8'),
      api.get<any>('/api/prood/logs?limit=12'),
      api.get<any>('/api/lafs/top-efe?k=5'),
      api.get<any>('/api/omega/legions', { timeoutMs: 15000 }),
    ]);
    if (st.ok) setStatus(st.data);
    if (h.ok) setHealth(h.data);
    if (pos.ok) setPositions(pos.data);
    if (pl.ok) setPlans(pl.data?.plans || []);
    if (lg.ok) setLogs(lg.data?.logs || []);
    if (cov.ok) setCoverage(cov.data);
    if (prd.ok) setProod(prd.data);
    if (fab.ok) setFabric(fab.data);
    if (dl.ok) setDelta(dl.data);
    if (hm.ok) setHeatmap(hm.data?.heatmap || []);
    if (act.ok) setActivity(act.data?.logs || []);
    if (efe.ok) setTopEfe(efe.data?.top || []);
    if (lgn.ok) setLegions(lgn.data);
    setLoading(false);
    setRefreshing(false);
  }, []);

  const mobilizeArmy = async () => {
    setMobilizing(true);
    const r = await api.post<any>('/api/omega/legions/mobilize',
      { wave_size: 800, directive: 'commander wave from mission control' }, { timeoutMs: 30000 });
    if (r.ok) {
      const lgn = await api.get<any>('/api/omega/legions');
      if (lgn.ok) setLegions(lgn.data);
    }
    setMobilizing(false);
  };

  const pickImage = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        if (!perm.canAskAgain) {
          Alert.alert('Photos access needed', 'Enable photo access to attach an image.',
            [{ text: 'Cancel' }, { text: 'Open Settings', onPress: () => Linking.openSettings() }]);
        }
        return;
      }
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images, base64: true, quality: 0.6,
      });
      if (!res.canceled && res.assets?.[0]?.base64) {
        setAttachment({ modality: 'image', base64: res.assets[0].base64, name: 'image' });
      }
    } catch { /* no-op */ }
  };

  const readBase64 = async (uri: string, file?: File) => {
    if (Platform.OS === 'web') {
      if (file) {
        return await new Promise<string>((resolve) => {
          const rd = new FileReader();
          rd.onload = () => resolve(String(rd.result).split(',')[1] || '');
          rd.readAsDataURL(file);
        });
      }
      const blob = await (await fetch(uri)).blob();
      return await new Promise<string>((resolve) => {
        const rd = new FileReader();
        rd.onload = () => resolve(String(rd.result).split(',')[1] || '');
        rd.readAsDataURL(blob);
      });
    }
    return await FileSystem.readAsStringAsync(uri, { encoding: 'base64' as any });
  };

  const pickDoc = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'video/*'], copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const a = res.assets[0];
      const isPdf = (a.mimeType || '').includes('pdf') || (a.name || '').toLowerCase().endsWith('.pdf');
      const b64 = await readBase64(a.uri, (a as any).file);
      if (b64) setAttachment({ modality: isPdf ? 'pdf' : 'video', base64: b64, name: a.name || (isPdf ? 'document.pdf' : 'video') });
    } catch { /* no-op */ }
  };

  const askJeeves = async () => {
    if (!ask.trim() && !attachment) return;
    setAsking(true); setAskReply(null);
    const body: any = { query: ask.trim() || 'Analyze the attached file', top_k: 5 };
    if (attachment) body[`${attachment.modality}_base64`] = attachment.base64;
    const r = await api.post<any>('/api/lafs/jeeves/ask', body, { timeoutMs: 60000 });
    if (r.ok) setAskReply(r.data);
    setAttachment(null);
    setAsking(false);
  };

  const activateEngines = async () => {
    setActivateMsg('Activating all engines…');
    const r = await api.post<any>('/api/gameforge/coverage/activate', {}, { timeoutMs: 30000 });
    setActivateMsg(r.ok ? r.data.message : 'Activation failed.');
    load();
  };

  const runSelfTest = async () => {
    setTesting(true);
    const r = await api.get<any>('/api/gameforge/coverage/selftest', { timeoutMs: 30000 });
    if (r.ok) setSelftest(r.data);
    setTesting(false);
  };

  const runSaga = async (failAt: string | null) => {
    setSagaBusy(true); setSaga(null);
    const r = await api.post<any>('/api/prood/saga/deploy',
      { project_name: failAt ? 'SagaRollback' : 'SagaDeploy', fail_at: failAt },
      { timeoutMs: 30000 });
    if (r.ok) setSaga(r.data);
    setSagaBusy(false);
  };

  React.useEffect(() => { load(); }, [load]);
  React.useEffect(() => {
    if (!live) return;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [live, load]);

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="mc-back" onPress={() => router.back()} style={{ padding: 4 }} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color={GREEN} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>🛰️ MasterMap Control Center</Text>
          <Text style={s.sub}>{live ? 'Live · every 5s' : 'Snapshot'} · unified CNS mission control</Text>
        </View>
        <TouchableOpacity testID="mc-live" style={[s.liveBtn, live && { backgroundColor: GREEN }]} onPress={() => { setLive((v) => !v); load(); }}>
          <Text style={[s.liveTxt, live && { color: '#04120a' }]}>{live ? 'LIVE' : 'Go Live'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={GREEN} />}
      >
        {loading ? (
          <View style={{ paddingVertical: 60, alignItems: 'center' }}><ActivityIndicator color={GREEN} size="large" /></View>
        ) : (
          <>
            <View style={s.statRow}>
              <Stat label="Agents" value={`${status?.active_agents ?? 0}`} color={GREEN} />
              <Stat label="Healthy" value={`${health?.healthy ?? 0}`} color={BLUE} />
              <Stat label="Dead" value={`${health?.dead ?? 0}`} color={RED} />
              <Stat label="Done" value={`${status?.tasks_done ?? 0}`} color={PURPLE} />
            </View>

            <View style={s.selfHeal}>
              <Ionicons name="sync-circle" size={16} color={GREEN} />
              <Text style={s.selfHealTxt}>Self-healing runtime active{health?.reaped ? ` · reaped ${health.reaped}` : ''} · {status?.groupchat ?? 0} chat msgs</Text>
            </View>

            {prood && (
              <>
                <Text style={s.h2}>🏗️ PROOD Readiness ({prood.overall_percent}%)</Text>
                <View style={s.card}>
                  <View style={[s.readyBanner, { backgroundColor: (prood.overall_percent >= 95 ? GREEN : AMBER) + '22' }]}>
                    <Ionicons name={prood.overall_percent >= 95 ? 'checkmark-circle' : 'construct'} size={16} color={prood.overall_percent >= 95 ? GREEN : AMBER} />
                    <Text style={[s.readyTxt, { color: prood.overall_percent >= 95 ? GREEN : AMBER }]}>
                      {prood.capabilities_live}/{prood.capabilities_total} capabilities live · weighted {prood.overall_percent}% complete
                    </Text>
                  </View>
                  {(prood.capabilities || []).map((c: any) => {
                    const col = c.status === 'live' ? GREEN : c.status === 'partial' ? AMBER : RED;
                    return (
                      <View key={c.key} style={{ marginTop: 8 }}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 }}>
                            <View style={[s.dot, { backgroundColor: col }]} />
                            <Text style={s.roomName} numberOfLines={1}>{c.name}</Text>
                          </View>
                          <Text style={[s.pct, { color: col }]}>{Math.round((c.score ?? 0) * 100)}%</Text>
                        </View>
                        <View style={s.covTrack}><View style={[s.covFill, { width: `${Math.round((c.score ?? 0) * 100)}%`, backgroundColor: col }]} /></View>
                      </View>
                    );
                  })}
                </View>
              </>
            )}

            <Text style={s.h2}>📦 Zip Coverage ({coverage?.overall_percent ?? 0}%)</Text>
            <View style={s.card}>
              <View style={s.statRow}>
                <Stat label="Subsystems" value={`${coverage?.subsystem_count ?? 0}`} color={GREEN} />
                <Stat label="Engines live" value={`${coverage?.engines?.live ?? 0}/${coverage?.engines?.total ?? 0}`} color={BLUE} />
                <Stat label="Dormant" value={`${coverage?.engines?.failed ?? 0}`} color={(coverage?.engines?.failed ?? 0) === 0 ? GREEN : RED} />
              </View>
              {(coverage?.zip_audit || []).map((z: any, i: number) => (
                <View key={i} style={{ marginTop: 8 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <Text style={s.roomName} numberOfLines={1}>{z.zip}</Text>
                    <Text style={s.roomMeta}>{z.percent}% · {z.modules} mods</Text>
                  </View>
                  <View style={s.covTrack}><View style={[s.covFill, { width: `${z.percent}%` }]} /></View>
                </View>
              ))}
              <TouchableOpacity testID="mc-activate" style={s.activateBtn} onPress={activateEngines}>
                <Ionicons name="flash" size={16} color="#04120a" />
                <Text style={s.activateTxt}>Activate all engines (0 dormant)</Text>
              </TouchableOpacity>
              {!!activateMsg && <Text style={s.msg}>{activateMsg}</Text>}
            </View>

            <Text style={s.h2}>🩺 System Self-Test {selftest ? `(${selftest.passed}/${selftest.total})` : ''}</Text>
            <View style={s.card}>
              {selftest ? (
                <>
                  <View style={[s.readyBanner, { backgroundColor: (selftest.ready ? GREEN : RED) + '22' }]}>
                    <Ionicons name={selftest.ready ? 'checkmark-circle' : 'alert-circle'} size={16} color={selftest.ready ? GREEN : RED} />
                    <Text style={[s.readyTxt, { color: selftest.ready ? GREEN : RED }]}>{selftest.ready ? 'All subsystems healthy — production ready' : 'Some subsystems are down'}</Text>
                  </View>
                  {selftest.results.map((r: any, i: number) => (
                    <View key={i} style={s.row}>
                      <View style={[s.dot, { backgroundColor: r.ok ? GREEN : RED }]} />
                      <Text style={s.roomName} numberOfLines={1}>{r.name}</Text>
                      <Text style={[s.pct, { color: r.ok ? GREEN : RED }]}>{r.ok ? 'OK' : 'FAIL'} · {r.latency_ms}ms</Text>
                    </View>
                  ))}
                </>
              ) : <Text style={s.empty}>Run a self-test to check every subsystem.</Text>}
              <TouchableOpacity testID="mc-selftest" style={[s.activateBtn, { backgroundColor: GREEN }]} onPress={runSelfTest} disabled={testing}>
                {testing ? <ActivityIndicator color="#04120a" size="small" /> : <><Ionicons name="pulse" size={16} color="#04120a" /><Text style={s.activateTxt}>Run System Self-Test</Text></>}
              </TouchableOpacity>
            </View>

            <Text style={s.h2}>🛰️ Agent GPS ({positions?.active_rooms ?? 0} rooms)</Text>
            <View style={s.card}>
              {(positions?.positions || []).length === 0 ? <Text style={s.empty}>No positioned agents.</Text> : (positions.positions).slice(0, 14).map((p: any, i: number) => {
                const col = p.health > 0.6 ? GREEN : p.health > 0.3 ? AMBER : RED;
                return (
                  <View key={p.agent_id || i} style={s.row}>
                    <View style={[s.dot, { backgroundColor: col }]} />
                    <Text style={s.roomName} numberOfLines={1}>{p.room_id}</Text>
                    <Text style={s.roomMeta} numberOfLines={1}>{p.category} · {p.task}</Text>
                    <Text style={[s.pct, { color: col }]}>{Math.round(p.health * 100)}%</Text>
                  </View>
                );
              })}
            </View>

            <Text style={s.h2}>🧠 Active Strategic Plans ({plans.length})</Text>
            <View style={s.card}>
              {plans.length === 0 ? <Text style={s.empty}>No plans yet — generate one in Jeeves → Strategic Planner.</Text> : plans.map((p: any, i: number) => (
                <View key={p.plan_id || i} style={{ paddingVertical: 7, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' }}>
                  <Text style={s.planObj} numberOfLines={1}>{p.objective}</Text>
                  <Text style={s.roomMeta}>{p.horizon_days}d · success {Math.round((p.simulation?.success_probability ?? 0) * 100)}% · risk {Math.round((p.risk?.final_risk ?? 0) * 100)}% · {p.scenario}</Text>
                </View>
              ))}
            </View>

            <Text style={s.h2}>🏛️ PROOD Architecture</Text>
            {fabric && (
              <View style={[s.card, { marginBottom: 12 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Text style={s.planObj}>Ω-Ultra Fabric · Jeeves + Agents</Text>
                  <View style={[s.readyBanner, { backgroundColor: PURPLE + '22', marginTop: 0 }]}>
                    <Ionicons name="pulse" size={14} color={PURPLE} />
                    <Text style={[s.readyTxt, { color: PURPLE }]}>System IQ {Math.round(fabric.system_iq)}</Text>
                  </View>
                </View>
                <View style={[s.statRow, { marginTop: 10 }]}>
                  <Stat label="Agents" value={`${fabric.agents_tracked}`} color={GREEN} />
                  <Stat label="Emissions" value={`${fabric.total_emissions}`} color={BLUE} />
                  <Stat label="Blocked" value={`${fabric.blocked_repeats}`} color={AMBER} />
                </View>
                <View style={{ marginTop: 12 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={s.roomMeta}>System-IQ growth</Text>
                    {fabric.persisted && (
                      <View style={[s.readyBanner, { backgroundColor: GREEN + '18', marginTop: 0, paddingVertical: 2, paddingHorizontal: 8 }]}>
                        <Ionicons name="save-outline" size={11} color={GREEN} />
                        <Text style={[s.readyTxt, { color: GREEN, fontSize: 11 }]}>
                          {fabric.restored ? 'persisted · restored' : 'persisted'}
                        </Text>
                      </View>
                    )}
                  </View>
                  <IqSparkline points={(fabric.recent_growth || []).map((g: any) => g.iq).filter((n: any) => typeof n === 'number')} />
                </View>
                <Text style={[s.roomMeta, { marginTop: 8 }]}>{fabric.topology}</Text>
              </View>
            )}

            {/* Delta (KDA) multimodal memory */}
            {delta && (
              <View style={[s.card, { marginBottom: 12 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Text style={s.planObj}>Δ Delta Memory · KDA</Text>
                  {delta.multimodal && (
                    <View style={[s.readyBanner, { backgroundColor: BLUE + '22', marginTop: 0, paddingVertical: 2, paddingHorizontal: 8 }]}>
                      <Ionicons name="layers-outline" size={12} color={BLUE} />
                      <Text style={[s.readyTxt, { color: BLUE, fontSize: 11 }]}>multimodal</Text>
                    </View>
                  )}
                </View>
                <Text style={[s.roomMeta, { marginTop: 4 }]}>
                  Fixed {delta.capacity_floats} floats · corrects, never appends
                </Text>
                <View style={{ flexDirection: 'row', gap: 12, marginTop: 10 }}>
                  <Svg width={132} height={132} viewBox="0 0 8 8">
                    {heatmap.map((row, i) =>
                      row.map((v, j) => {
                        const mx = Math.max(0.0001, ...heatmap.flat());
                        const a = Math.min(1, v / mx);
                        return <Rect key={`${i}-${j}`} x={j} y={i} width={1} height={1}
                          fill={PURPLE} opacity={0.12 + 0.88 * a} />;
                      })
                    )}
                  </Svg>
                  <View style={{ flex: 1, justifyContent: 'center' }}>
                    <Stat label="Writes" value={`${delta.writes}`} color={GREEN} />
                    <View style={{ height: 8 }} />
                    <Stat label="Distinct keys" value={`${delta.distinct_keys}`} color={AMBER} />
                    <View style={{ height: 8 }} />
                    <Stat label="Spectral ‖M‖" value={`${delta.spectral_norm}`} color={PURPLE} />
                  </View>
                </View>
                <Text style={[s.roomMeta, { marginTop: 8 }]}>
                  {Object.entries(delta.modality_writes || {}).filter(([, c]: any) => c > 0)
                    .map(([m, c]: any) => `${m}:${c}`).join(' · ') || 'text only'}
                </Text>
              </View>
            )}

            {/* Legion Command — Jeeves' game-building army */}
            {legions && (
              <View style={[s.card, { marginBottom: 12 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Text style={s.planObj}>⚔️ Legion Command</Text>
                  <Text style={s.roomMeta}>{(legions.total_roster_agents || 0).toLocaleString()} agents</Text>
                </View>
                <Text style={[s.roomMeta, { marginTop: 4 }]}>
                  {legions.legion_count} specialty legions · army competency {legions.army_competency}
                </Text>
                <View style={{ height: 8, backgroundColor: '#0b1220', borderRadius: 4, marginTop: 8, overflow: 'hidden' }}>
                  <View style={{ height: 8, width: `${Math.min(100, (legions.army_competency / 1000) * 100)}%`, backgroundColor: PURPLE }} />
                </View>
                {(legions.legions || []).slice(0, 5).map((l: any) => (
                  <View key={l.id} style={{ marginTop: 10 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={{ color: '#e2e8f0', fontSize: 12 }} numberOfLines={1}>{l.name}</Text>
                      <Text style={s.roomMeta}>{l.competency} · {l.size.toLocaleString()}</Text>
                    </View>
                    <View style={{ height: 5, backgroundColor: '#0b1220', borderRadius: 3, marginTop: 3, overflow: 'hidden' }}>
                      <View style={{ height: 5, width: `${Math.min(100, (l.competency / 1000) * 100)}%`, backgroundColor: GREEN }} />
                    </View>
                    <Text style={[s.roomMeta, { fontSize: 10 }]} numberOfLines={1}>{l.specialty}</Text>
                  </View>
                ))}
                <TouchableOpacity testID="mobilize-army-btn" onPress={mobilizeArmy} disabled={mobilizing}
                  style={[s.askBtn, { marginTop: 12, paddingVertical: 11, backgroundColor: PURPLE }, mobilizing && { opacity: 0.6 }]}>
                  {mobilizing ? <ActivityIndicator size="small" color="#fff" />
                    : <Text style={[s.askBtnTxt, { color: '#fff' }]}>Jeeves: Mobilize the Army ⚔️</Text>}
                </TouchableOpacity>
                <Text style={[s.roomMeta, { marginTop: 6, textAlign: 'center' }]}>
                  {(legions.total_agents_activated || 0).toLocaleString()} agents activated to date
                </Text>
              </View>
            )}

            {/* What Jeeves Knows — top-EFE canon + RAG ask */}
            <View style={[s.card, { marginBottom: 12 }]}>
              <Text style={s.planObj}>🧠 What Jeeves Knows</Text>
              {topEfe.length === 0 ? (
                <Text style={[s.roomMeta, { marginTop: 6 }]}>No canon yet — teach Jeeves via online learning.</Text>
              ) : topEfe.map((sheet: any, i: number) => (
                <View key={sheet.id || i} style={{ paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' }}>
                  <Text style={{ color: '#e2e8f0', fontSize: 13 }} numberOfLines={1}>
                    {sheet.path} <Text style={{ color: PURPLE }}>· EFE {sheet.efe}</Text>
                  </Text>
                  <Text style={s.roomMeta} numberOfLines={1}>
                    posterior {sheet.posterior} · {(sheet.tags || []).slice(0, 3).join(', ')}
                  </Text>
                </View>
              ))}
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <TouchableOpacity testID="attach-image-btn" onPress={pickImage} style={s.attachBtn}>
                  <Ionicons name="image-outline" size={18} color={BLUE} />
                </TouchableOpacity>
                <TouchableOpacity testID="attach-doc-btn" onPress={pickDoc} style={s.attachBtn}>
                  <Ionicons name="document-attach-outline" size={18} color={AMBER} />
                </TouchableOpacity>
                <TextInput
                  testID="jeeves-ask-input"
                  value={ask} onChangeText={setAsk}
                  placeholder="Ask Jeeves (grounded in canon)…"
                  placeholderTextColor={MUTE}
                  style={s.askInput} />
                <TouchableOpacity testID="jeeves-ask-btn" onPress={askJeeves} disabled={asking}
                  style={[s.askBtn, asking && { opacity: 0.6 }]}>
                  {asking ? <ActivityIndicator size="small" color="#0b1220" />
                    : <Text style={s.askBtnTxt}>Ask</Text>}
                </TouchableOpacity>
              </View>
              {attachment && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 }}>
                  <Ionicons name="attach" size={14} color={GREEN} />
                  <Text style={[s.roomMeta, { color: GREEN, flex: 1 }]} numberOfLines={1}>
                    {attachment.modality.toUpperCase()} attached · {attachment.name}
                  </Text>
                  <TouchableOpacity onPress={() => setAttachment(null)}>
                    <Ionicons name="close-circle" size={16} color={MUTE} />
                  </TouchableOpacity>
                </View>
              )}
              {askReply && (
                <View style={{ marginTop: 10, backgroundColor: '#0b1220', borderRadius: 10, padding: 10 }}>
                  <Text style={[s.roomMeta, { marginBottom: 4 }]}>
                    {askReply.model} · grounded in {askReply.recalled_count} sheet(s)
                    {askReply.modalities && askReply.modalities.length > 1 ? ` · ${askReply.modalities.join('+')}` : ''}
                  </Text>
                  <Text style={{ color: '#e2e8f0', fontSize: 13, lineHeight: 19 }}>{askReply.reply}</Text>
                </View>
              )}
            </View>

            {/* Live distributed activity (PROOD event bus) */}
            {activity.length > 0 && (
              <View style={[s.card, { marginBottom: 12 }]}>
                <Text style={s.planObj}>📡 Distributed Activity</Text>
                {activity.map((e: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 5 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4,
                      backgroundColor: e.severity === 'error' ? RED : e.severity === 'warning' ? AMBER : GREEN }} />
                    <Text style={{ color: '#cbd5e1', fontSize: 12, flex: 1 }} numberOfLines={1}>
                      {e.event_type}
                    </Text>
                    <Text style={s.roomMeta}>{e.severity}</Text>
                  </View>
                ))}
              </View>
            )}
            <ChurnPanel projectName="MissionChurn" />
            <View style={[s.card, { marginTop: 12 }]}>
              <Text style={s.planObj}>Saga Orchestration (compensation & recovery)</Text>
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
                <TouchableOpacity testID="mc-saga-ok" style={[s.activateBtn, { flex: 1, backgroundColor: GREEN }]} onPress={() => runSaga(null)} disabled={sagaBusy}>
                  <Ionicons name="git-merge" size={15} color="#04120a" /><Text style={s.activateTxt}>Run saga</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="mc-saga-fail" style={[s.activateBtn, { flex: 1, backgroundColor: AMBER }]} onPress={() => runSaga('deliver')} disabled={sagaBusy}>
                  <Ionicons name="arrow-undo" size={15} color="#04120a" /><Text style={s.activateTxt}>Fail → rollback</Text>
                </TouchableOpacity>
              </View>
              {sagaBusy && <View style={{ paddingVertical: 10, alignItems: 'center' }}><ActivityIndicator color={GREEN} /></View>}
              {saga && (
                <View style={{ marginTop: 10 }}>
                  <View style={[s.readyBanner, { backgroundColor: (saga.status === 'completed' ? GREEN : AMBER) + '22' }]}>
                    <Ionicons name={saga.status === 'completed' ? 'checkmark-circle' : 'refresh-circle'} size={16} color={saga.status === 'completed' ? GREEN : AMBER} />
                    <Text style={[s.readyTxt, { color: saga.status === 'completed' ? GREEN : AMBER }]}>Saga {saga.status}</Text>
                  </View>
                  {(saga.forward_trace || []).map((t: any, i: number) => (
                    <View key={`f${i}`} style={s.row}>
                      <View style={[s.dot, { backgroundColor: t.status === 'ok' ? GREEN : RED }]} />
                      <Text style={s.roomName}>→ {t.step}</Text>
                      <Text style={[s.pct, { color: t.status === 'ok' ? GREEN : RED }]}>{t.status}</Text>
                    </View>
                  ))}
                  {(saga.compensation_trace || []).map((t: any, i: number) => (
                    <View key={`c${i}`} style={s.row}>
                      <View style={[s.dot, { backgroundColor: BLUE }]} />
                      <Text style={s.roomName}>↩ {t.step}</Text>
                      <Text style={[s.pct, { color: BLUE }]}>{t.status}</Text>
                    </View>
                  ))}
                </View>
              )}
            </View>

            <Text style={s.h2}>📜 Universal Logs</Text>
            <View style={s.card}>
              {logs.length === 0 ? <Text style={s.empty}>No logs yet.</Text> : logs.slice(0, 16).map((l: any, i: number) => {
                const col = l.severity === 'error' ? RED : l.severity === 'warning' ? AMBER : l.component === 'recovery' ? BLUE : PURPLE;
                return (
                  <View key={i} style={s.row}>
                    <View style={[s.badge, { borderColor: col, backgroundColor: col + '22' }]}><Text style={[s.badgeTxt, { color: col }]}>{l.component}</Text></View>
                    <Text style={s.roomMeta} numberOfLines={1}>{l.event}{l.detail ? ` · ${l.detail}` : ''}</Text>
                  </View>
                );
              })}
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={s.stat}>
      <Text style={[s.statVal, { color }]}>{value}</Text>
      <Text style={s.statLbl}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  askInput: { flex: 1, backgroundColor: '#0b1220', borderColor: '#334155', borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: '#e2e8f0', fontSize: 13 },
  askBtn: { backgroundColor: '#22c55e', borderRadius: 10, paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center', minWidth: 64 },
  askBtnTxt: { color: '#0b1220', fontWeight: '700', fontSize: 14 },
  attachBtn: { backgroundColor: '#0b1220', borderColor: '#334155', borderWidth: 1, borderRadius: 10, width: 40, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '700' },
  sub: { color: MUTE, fontSize: 11, marginTop: 1 },
  liveBtn: { backgroundColor: '#1e293b', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  liveTxt: { color: '#cbd5e1', fontSize: 11, fontWeight: '800' },
  statRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  stat: { flex: 1, backgroundColor: CARD, borderRadius: 12, paddingVertical: 13, alignItems: 'center' },
  statVal: { fontSize: 18, fontWeight: '800' },
  statLbl: { color: MUTE, fontSize: 10, marginTop: 2 },
  selfHeal: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: GREEN + '18', borderRadius: 10, padding: 10, marginBottom: 4 },
  selfHealTxt: { color: '#bbf7d0', fontSize: 12, flex: 1 },
  h2: { color: '#e2e8f0', fontSize: 14, fontWeight: '700', marginTop: 18, marginBottom: 8 },
  card: { backgroundColor: CARD, borderRadius: 14, padding: 12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 7, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  dot: { width: 9, height: 9, borderRadius: 5 },
  roomName: { color: '#f1f5f9', fontSize: 13, fontWeight: '600' },
  roomMeta: { color: MUTE, fontSize: 11, flex: 1 },
  pct: { fontSize: 11, fontWeight: '800' },
  planObj: { color: '#f1f5f9', fontSize: 13, fontWeight: '600' },
  covTrack: { height: 7, borderRadius: 4, backgroundColor: '#1e293b', marginTop: 5, overflow: 'hidden' },
  covFill: { height: 7, borderRadius: 4, backgroundColor: GREEN },
  activateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: AMBER, borderRadius: 10, paddingVertical: 12, marginTop: 14 },
  activateTxt: { color: '#04120a', fontSize: 13, fontWeight: '800' },
  msg: { color: GREEN, fontSize: 12, marginTop: 8, textAlign: 'center' },
  readyBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 10, padding: 10, marginBottom: 8 },
  readyTxt: { fontSize: 12, fontWeight: '700', flex: 1 },
  badge: { borderRadius: 6, borderWidth: 1, paddingHorizontal: 7, paddingVertical: 2 },
  badgeTxt: { fontSize: 9, fontWeight: '800', textTransform: 'uppercase' },
  empty: { color: MUTE, fontSize: 12, fontStyle: 'italic', textAlign: 'center', paddingVertical: 16 },
});
