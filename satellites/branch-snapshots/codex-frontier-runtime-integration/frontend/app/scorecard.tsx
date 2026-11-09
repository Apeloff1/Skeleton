/**
 * /scorecard — 🩺 10-Level Quality Scorecard + hard 95 delivery gate.
 * Shows every audit level, the gate verdict (ship-ready badge), fix-it deep-links,
 * a Deliver button (server-gated), scorecard PNG share, and gate-floor history trend.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet, SafeAreaView, Linking, Platform, Share,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

function bandColor(s: number) {
  return s >= 95 ? '#4ade80' : s >= 85 ? '#60a5fa' : s >= 70 ? '#fbbf24' : s >= 50 ? '#fb923c' : '#f87171';
}

export default function Scorecard() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const gameId = params?.game ? String(params.game) : '';
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const [delivering, setDelivering] = React.useState(false);
  const [deliverMsg, setDeliverMsg] = React.useState<string | null>(null);
  const [history, setHistory] = React.useState<any[]>([]);

  const load = React.useCallback(async () => {
    setLoading(true);
    const [a, h] = await Promise.all([
      api.get<any>(`/api/snowball/${gameId}/audit?deep=true`, { timeoutMs: 90000 }),
      api.get<any>(`/api/snowball/${gameId}/audit/history?limit=12`, { timeoutMs: 12000 }),
    ]);
    if (a.ok && a.data && !a.data.error) setData(a.data);
    if (h.ok && h.data?.history) setHistory(h.data.history);
    setLoading(false);
  }, [gameId]);

  React.useEffect(() => { load(); }, [load]);

  const deliver = React.useCallback(async () => {
    setDelivering(true); setDeliverMsg(null);
    const r = await api.post<any>(`/api/snowball/${gameId}/deliver`, {}, { timeoutMs: 90000 });
    setDeliverMsg(r.ok && r.data ? r.data.message : 'Delivery failed — try again.');
    setDelivering(false);
    load();
  }, [gameId, load]);

  const [improve, setImprove] = React.useState<any>(null);
  const [improving, setImproving] = React.useState(false);
  const [retryMsg, setRetryMsg] = React.useState<string | null>(null);

  const runImprove = React.useCallback(async () => {
    setImproving(true); setImprove(null); setRetryMsg(null);
    const r = await api.post<any>(`/api/snowball/${gameId}/auto-improve`, {}, { timeoutMs: 120000 });
    setImprove(r.ok && r.data && !r.data.error ? r.data : { error: r.data?.error || 'Auto-improve failed.', upgrades: [] });
    setImproving(false);
  }, [gameId]);

  const runRetry = React.useCallback(async () => {
    setRetryMsg('⏳ Regenerating weak stages…');
    const r = await api.post<any>(`/api/snowball/${gameId}/auto-improve/retry`, {}, { timeoutMs: 30000 });
    setRetryMsg(r.ok && r.data ? r.data.message : 'Retry failed.');
  }, [gameId]);

  const publish = React.useCallback(async () => {
    setRetryMsg('⏳ Checking publish gate…');
    const r = await api.post<any>(`/api/snowball/${gameId}/publish`, {}, { timeoutMs: 90000 });
    setRetryMsg(r.ok && r.data ? r.data.message : 'Publish failed.');
  }, [gameId]);

  const [loopId, setLoopId] = React.useState<string | null>(null);
  const [loopStatus, setLoopStatus] = React.useState<any>(null);
  const [vault, setVault] = React.useState<any>(null);

  React.useEffect(() => {
    api.get<any>(`/api/snowball/${gameId}/vault-digest`, { timeoutMs: 12000 })
      .then((r) => { if (r.ok && r.data?.digest) setVault(r.data.digest); });
  }, [gameId]);

  const startAutoLoop = React.useCallback(async () => {
    setLoopStatus({ status: 'running', passes: [] });
    const r = await api.post<any>(`/api/snowball/${gameId}/auto-improve/auto-loop?max_passes=3`, {}, { timeoutMs: 20000 });
    if (r.ok && r.data?.loop_id) setLoopId(r.data.loop_id);
    else setLoopStatus({ status: 'error' });
  }, [gameId]);

  React.useEffect(() => {
    if (!loopId) return;
    const t = setInterval(async () => {
      const r = await api.get<any>(`/api/snowball/auto-loop/${loopId}`, { timeoutMs: 12000 });
      if (r.ok && r.data) {
        setLoopStatus(r.data);
        if (r.data.status === 'done') { clearInterval(t); load(); }
      }
    }, 5000);
    return () => clearInterval(t);
  }, [loopId, load]);

  const shareCard = React.useCallback(async () => {
    const url = `${BACKEND}/api/snowball/${gameId}/scorecard.png`;
    if (Platform.OS === 'web') Linking.openURL(url);
    else try { await Share.share({ url, message: 'My Galaxy Studio quality scorecard' }); } catch {}
  }, [gameId]);

  if (loading) {
    return (
      <SafeAreaView style={s.root}>
        <View style={s.header}><Text style={s.title}>🩺 Quality Scorecard</Text></View>
        <View style={{ padding: 50, alignItems: 'center' }}>
          <ActivityIndicator size="large" color="#93C5FD" />
          <Text style={{ color: '#64748b', marginTop: 14, fontSize: 13 }}>Auditing 10 levels + LLM quality…</Text>
        </View>
      </SafeAreaView>
    );
  }
  if (!data) {
    return (
      <SafeAreaView style={s.root}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
          <Text style={s.title}>🩺 Quality Scorecard</Text>
        </View>
        <Text style={{ color: '#94a3b8', padding: 24 }}>No audit available for this game.</Text>
      </SafeAreaView>
    );
  }

  const llm = data.llm;
  const ship = data.deliverable;

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={s.title}>🩺 Quality Scorecard</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
        {/* gate hero */}
        <View style={[s.hero, { borderColor: ship ? '#166534' : '#854d0e' }]}>
          <Text style={[s.gate, { color: bandColor(data.gate_floor) }]}>{data.gate_floor}</Text>
          <View style={{ flex: 1 }}>
            {ship
              ? <View testID="ship-badge" style={s.shipBadge}><Text style={s.shipTxt}>✓ SHIP-READY</Text></View>
              : <View testID="notready-badge" style={s.notBadge}><Text style={s.notTxt}>NOT YET 95</Text></View>}
            <Text style={s.heroSub}>Hard gate at {data.threshold}. Lowest level = {data.gate_floor}.</Text>
            <Text style={s.heroSub}>{data.blocker_count} blocker(s) · grade {data.band}</Text>
          </View>
        </View>

        {/* deliver gate */}
        <TouchableOpacity testID="deliver-btn" onPress={deliver} disabled={delivering}
          style={[s.deliverBtn, ship ? s.deliverOn : s.deliverOff, delivering && { opacity: 0.6 }]} activeOpacity={0.9}>
          {delivering ? <ActivityIndicator size="small" color="#fff" />
            : <Text style={s.deliverTxt}>{ship ? '🚀 Deliver (gate passes)' : '🔒 Deliver locked — resolve blockers'}</Text>}
        </TouchableOpacity>
        {deliverMsg && <Text testID="deliver-msg" style={s.deliverMsg}>{deliverMsg}</Text>}

        {/* ✨ Auto-improve loop — summary first, then retry */}
        <TouchableOpacity testID="auto-improve-btn" onPress={runImprove} disabled={improving}
          style={[s.improveBtn, improving && { opacity: 0.6 }]} activeOpacity={0.9}>
          {improving ? <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}><ActivityIndicator size="small" color="#fff" /><Text style={s.improveTxt}>Analyzing upgrades…</Text></View>
            : <Text style={s.improveTxt}>✨ Auto-improve — summarize upgrades</Text>}
        </TouchableOpacity>
        {improve && !improve.error && (improve.upgrades || []).length > 0 && (
          <View testID="improve-summary" style={s.improveBox}>
            <Text style={s.improveHead}>{improve.upgrades.length} upgrades across {(improve.weak_stages || []).join(', ') || 'stages'}</Text>
            {improve.upgrades.map((u: any, i: number) => (
              <View key={i} testID={`upgrade-${i}`} style={s.upgrade}>
                <Text style={s.upSignal}>{u.signal} · {u.current}/100</Text>
                <Text style={s.upText}>{u.upgrade}</Text>
                {!!u.impact && <Text style={s.upImpact}>↑ {u.impact}</Text>}
              </View>
            ))}
            <TouchableOpacity testID="retry-btn" onPress={runRetry} style={s.retryBtn}>
              <Text style={s.retryTxt}>♻️ Apply &amp; regenerate weak stages</Text>
            </TouchableOpacity>
          </View>
        )}
        {improve?.error && <Text style={s.deliverMsg}>⚠️ {improve.error}</Text>}
        {retryMsg && <Text testID="retry-msg" style={s.deliverMsg}>{retryMsg}</Text>}

        {/* 🔁 Auto-loop to 95 */}
        <TouchableOpacity testID="auto-loop-btn" onPress={startAutoLoop}
          disabled={loopStatus?.status === 'running'}
          style={[s.loopBtn, loopStatus?.status === 'running' && { opacity: 0.6 }]} activeOpacity={0.9}>
          <Text style={s.loopTxt}>🔁 Auto-loop to 95 (drive to ship-quality)</Text>
        </TouchableOpacity>
        {loopStatus && (
          <View testID="auto-loop-status" style={s.loopBox}>
            <Text style={s.loopStat}>
              {loopStatus.status === 'running' ? `⏳ Pass ${loopStatus.pass || 0}/${loopStatus.max_passes || 3} · gate ${loopStatus.gate_floor ?? 0}`
                : loopStatus.status === 'done' ? `${loopStatus.deliverable ? '✓' : '•'} ${loopStatus.message || 'Done'}`
                : '⚠️ Could not start loop'}
            </Text>
            {(loopStatus.passes || []).map((p: any, i: number) => (
              <Text key={i} style={s.loopPass}>· pass {p.pass}: {p.gate_floor}/100{p.deliverable ? ' ✓' : ''}</Text>
            ))}
          </View>
        )}

        {/* 🧠 Vault tips inline (manual-pass reference) */}
        {vault && (
          <>
            <Text style={s.section}>🧠 Stage knowledge (vault)</Text>
            {Object.keys(vault).map((st) => (
              <View key={st} testID={`vault-${st}`} style={s.vaultRow}>
                <Text style={s.vaultStage}>{st}</Text>
                <Text style={s.vaultTip}>{vault[st]}</Text>
              </View>
            ))}
          </>
        )}

        {/* 10 levels */}
        <Text style={s.section}>10 audit levels</Text>
        {data.levels.map((lv: any, i: number) => (
          <View key={lv.key} testID={`level-${i}`} style={s.level}>
            <View style={s.levelTop}>
              <Text style={s.levelName}>{lv.pass ? '✅' : '⚠️'} {lv.label}</Text>
              <Text style={[s.levelScore, { color: bandColor(lv.score) }]}>{lv.score}</Text>
            </View>
            <View style={s.barBg}>
              <View style={[s.barFill, { width: `${lv.score}%`, backgroundColor: bandColor(lv.score) }]} />
            </View>
            {!lv.pass && (
              <TouchableOpacity testID={`fixit-${i}`} onPress={() => router.push(`/${lv.fix_route}?game=${gameId}` as any)}>
                <Text style={s.fixit}>🔧 Fix in {lv.fix_route} →</Text>
              </TouchableOpacity>
            )}
          </View>
        ))}

        {/* LLM confirmation */}
        {llm && (
          <>
            <Text style={s.section}>LLM quality confirmation {llm.model ? `· ${llm.model}` : ''}</Text>
            <View style={s.llmRow}>
              {[['Quality', llm.quality], ['Parse', llm.parse_confidence], ['Recall', llm.recall]].map(([k, v]: any) => (
                <View key={k} style={s.llmCell}>
                  <Text style={[s.llmNum, { color: bandColor(v) }]}>{v}</Text>
                  <Text style={s.llmLbl}>{k}</Text>
                </View>
              ))}
            </View>
            {!!llm.notes && <Text style={s.llmNotes}>“{llm.notes}”</Text>}
          </>
        )}

        {/* actions */}
        <View style={s.actions}>
          <TouchableOpacity testID="share-scorecard" onPress={shareCard} style={s.actBtn}><Text style={s.actTxt}>🖼️ Share scorecard PNG</Text></TouchableOpacity>
          <TouchableOpacity testID="refresh-audit" onPress={load} style={s.actBtn}><Text style={s.actTxt}>🔄 Re-audit</Text></TouchableOpacity>
        </View>
        <View style={s.actions}>
          <TouchableOpacity testID="open-atlas" onPress={() => Linking.openURL(`${BACKEND}/api/snowball/${gameId}/atlas.html`)} style={s.actBtn}><Text style={s.actTxt}>📖 World Atlas</Text></TouchableOpacity>
          <TouchableOpacity testID="open-compare" onPress={() => router.push(`/render-compare?game=${gameId}` as any)} style={s.actBtn}><Text style={s.actTxt}>🖼️ Compare renders</Text></TouchableOpacity>
          <TouchableOpacity testID="publish-btn" onPress={publish} style={s.actBtn}><Text style={s.actTxt}>🏪 Publish</Text></TouchableOpacity>
        </View>

        {/* history trend */}
        {history.length > 1 && (
          <>
            <Text style={s.section}>📈 Gate-floor trend</Text>
            <View style={s.trend}>
              {history.slice().reverse().map((h: any, i: number) => (
                <View key={i} style={s.trendCol}>
                  <View style={[s.trendBar, { height: Math.max(4, h.gate_floor * 0.9), backgroundColor: bandColor(h.gate_floor) }]} />
                  <Text style={s.trendNum}>{h.gate_floor}</Text>
                </View>
              ))}
            </View>
          </>
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
  hero: { flexDirection: 'row', alignItems: 'center', gap: 16, backgroundColor: '#0b1220', borderRadius: 16, borderWidth: 2, padding: 18 },
  gate: { fontSize: 64, fontWeight: '900', minWidth: 96, textAlign: 'center' },
  shipBadge: { alignSelf: 'flex-start', backgroundColor: '#166534', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4, marginBottom: 6 },
  shipTxt: { color: '#dcfce7', fontWeight: '900', fontSize: 13 },
  notBadge: { alignSelf: 'flex-start', backgroundColor: '#3f2d09', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4, marginBottom: 6 },
  notTxt: { color: '#fde68a', fontWeight: '900', fontSize: 13 },
  heroSub: { color: '#94a3b8', fontSize: 12, marginTop: 2 },
  deliverBtn: { marginTop: 12, borderRadius: 12, paddingVertical: 15, alignItems: 'center' },
  deliverOn: { backgroundColor: '#16a34a' },
  deliverOff: { backgroundColor: '#3f2d09' },
  deliverTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  deliverMsg: { color: '#cbd5e1', fontSize: 12, marginTop: 8, lineHeight: 17 },
  improveBtn: { marginTop: 10, backgroundColor: '#7c3aed', borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  improveTxt: { color: '#fff', fontWeight: '800', fontSize: 13 },
  improveBox: { marginTop: 10, backgroundColor: '#160d2e', borderRadius: 12, borderWidth: 1, borderColor: '#4c1d95', padding: 12 },
  improveHead: { color: '#c084fc', fontWeight: '800', fontSize: 13, marginBottom: 8 },
  upgrade: { borderLeftWidth: 3, borderLeftColor: '#a855f7', paddingLeft: 10, marginBottom: 8 },
  upSignal: { color: '#f5f3ff', fontWeight: '800', fontSize: 12 },
  upText: { color: '#cbd5e1', fontSize: 12, lineHeight: 17, marginTop: 1 },
  upImpact: { color: '#86efac', fontSize: 11, marginTop: 2 },
  retryBtn: { backgroundColor: '#6d28d9', borderRadius: 9, paddingVertical: 11, alignItems: 'center', marginTop: 4 },
  retryTxt: { color: '#fff', fontWeight: '800', fontSize: 12 },
  loopBtn: { marginTop: 10, backgroundColor: '#1E40AF', borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  loopTxt: { color: '#fff', fontWeight: '800', fontSize: 13 },
  loopBox: { marginTop: 8, backgroundColor: '#06222b', borderRadius: 10, borderWidth: 1, borderColor: '#1E40AF', padding: 10 },
  loopStat: { color: '#BFDBFE', fontWeight: '700', fontSize: 12 },
  loopPass: { color: '#93C5FD', fontSize: 11, marginTop: 2 },
  vaultRow: { backgroundColor: '#0b1220', borderRadius: 10, borderWidth: 1, borderColor: '#1e293b', padding: 10, marginBottom: 6 },
  vaultStage: { color: '#fbbf24', fontSize: 11, fontWeight: '800', textTransform: 'uppercase' },
  vaultTip: { color: '#cbd5e1', fontSize: 11, lineHeight: 16, marginTop: 2 },
  section: { color: '#94A3B8', fontSize: 13, fontWeight: '800', marginTop: 22, marginBottom: 8 },
  level: { backgroundColor: '#0b1220', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', padding: 12, marginBottom: 8 },
  levelTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  levelName: { color: '#E2E8F0', fontSize: 14, fontWeight: '700', flex: 1 },
  levelScore: { fontSize: 18, fontWeight: '900' },
  barBg: { height: 10, backgroundColor: '#1e293b', borderRadius: 6, marginTop: 8, overflow: 'hidden' },
  barFill: { height: 10, borderRadius: 6 },
  fixit: { color: '#fbbf24', fontSize: 12, fontWeight: '700', marginTop: 8 },
  llmRow: { flexDirection: 'row', gap: 10 },
  llmCell: { flex: 1, backgroundColor: '#0b1220', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', alignItems: 'center', paddingVertical: 14 },
  llmNum: { fontSize: 26, fontWeight: '900' },
  llmLbl: { color: '#64748b', fontSize: 11, fontWeight: '700', marginTop: 2 },
  llmNotes: { color: '#94a3b8', fontSize: 12, fontStyle: 'italic', marginTop: 8 },
  actions: { flexDirection: 'row', gap: 10, marginTop: 18 },
  actBtn: { flex: 1, backgroundColor: '#1e293b', borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  actTxt: { color: '#e2e8f0', fontSize: 12, fontWeight: '700' },
  trend: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 110, backgroundColor: '#0b1220', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', padding: 10 },
  trendCol: { flex: 1, alignItems: 'center', justifyContent: 'flex-end' },
  trendBar: { width: '70%', borderRadius: 4 },
  trendNum: { color: '#64748b', fontSize: 9, marginTop: 3 },
});
