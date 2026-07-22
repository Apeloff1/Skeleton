/**
 * /mission-control — MasterMap Control Center.
 * One live "mission control" view unifying the whole CNS: runtime status,
 * agent GPS positions, heartbeat health (self-healing), active strategic plans,
 * and the universal log feed. Read-only, auto-refreshing.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/utils/apiClient';

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

export default function MissionControl() {
  const router = useRouter();
  const [status, setStatus] = React.useState<any>(null);
  const [health, setHealth] = React.useState<any>(null);
  const [positions, setPositions] = React.useState<any>(null);
  const [plans, setPlans] = React.useState<any[]>([]);
  const [logs, setLogs] = React.useState<any[]>([]);
  const [coverage, setCoverage] = React.useState<any>(null);
  const [activateMsg, setActivateMsg] = React.useState('');
  const [selftest, setSelftest] = React.useState<any>(null);
  const [testing, setTesting] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [live, setLive] = React.useState(false);

  const load = React.useCallback(async () => {
    const [st, h, pos, pl, lg, cov] = await Promise.all([
      api.get<any>(`${RT}/status`), api.get<any>(`${RT}/health`), api.get<any>(`${RT}/positions`),
      api.get<any>(`${PLAN}/plans?limit=6`), api.get<any>(`${S}/logs?limit=18`),
      api.get<any>('/api/gameforge/coverage', { timeoutMs: 20000 }),
    ]);
    if (st.ok) setStatus(st.data);
    if (h.ok) setHealth(h.data);
    if (pos.ok) setPositions(pos.data);
    if (pl.ok) setPlans(pl.data?.plans || []);
    if (lg.ok) setLogs(lg.data?.logs || []);
    if (cov.ok) setCoverage(cov.data);
    setLoading(false);
    setRefreshing(false);
  }, []);

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
