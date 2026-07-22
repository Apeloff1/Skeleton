/**
 * /jury-room — Adversarial Jury Room.
 * Universal information is prosecuted (Library), defended (Grader), scrutinized
 * by the jury, and only accepted verdicts reach the wiki. Active & continuous.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, RefreshControl, KeyboardAvoidingView, Platform,
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
const J = '/api/gameforge/jury';

const VERDICT_COLOR: Record<string, string> = { accepted: GREEN, revise: AMBER, rejected: RED, pending: MUTE };

export default function JuryRoom() {
  const router = useRouter();
  const [status, setStatus] = React.useState<any>(null);
  const [verdicts, setVerdicts] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [live, setLive] = React.useState(false);
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [topic, setTopic] = React.useState('');
  const [content, setContent] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState('');

  const load = React.useCallback(async () => {
    const [st, v] = await Promise.all([
      api.get<any>(`${J}/status`, { timeoutMs: 15000 }),
      api.get<any>(`${J}/verdicts?limit=25`, { timeoutMs: 15000 }),
    ]);
    if (st.ok) setStatus(st.data);
    if (v.ok) setVerdicts(v.data?.verdicts || []);
    setLoading(false); setRefreshing(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);
  React.useEffect(() => {
    if (!live) return;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [live, load]);

  const submit = async () => {
    if (!topic.trim() || !content.trim() || busy) return;
    setBusy(true); setMsg('Submitting to docket…');
    const r = await api.post<any>(`${J}/submit`, { topic: topic.trim(), content: content.trim(), source: 'manual' }, { timeoutMs: 15000 });
    if (r.ok && r.data?.queued) { setMsg('Queued — running adjudication…'); await api.post(`${J}/tick`, { max_items: 5 }, { timeoutMs: 20000 }); setTopic(''); setContent(''); await load(); }
    else setMsg(r.data?.duplicate ? 'Already adjudicated (duplicate).' : 'Submit failed.');
    setBusy(false);
  };

  const runTick = async () => {
    setBusy(true); setMsg('Ingesting + adjudicating…');
    const r = await api.post<any>(`${J}/tick`, { max_items: 10 }, { timeoutMs: 25000 });
    setMsg(r.ok ? `Processed ${r.data?.count ?? 0} case(s).` : 'Tick failed.');
    await load(); setBusy(false);
  };

  return (
    <SafeAreaView style={s.root}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity testID="jury-back" onPress={() => router.back()} style={{ padding: 4 }} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color={GREEN} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>⚖️ Jury Room</Text>
            <Text style={s.sub}>{live ? 'Live · every 5s' : 'Adversarial adjudication'} · scrutiny → wiki</Text>
          </View>
          <TouchableOpacity testID="jury-live" style={[s.liveBtn, live && { backgroundColor: GREEN }]} onPress={() => { setLive((v) => !v); load(); }}>
            <Text style={[s.liveTxt, live && { color: '#04120a' }]}>{live ? 'LIVE' : 'Go Live'}</Text>
          </TouchableOpacity>
        </View>

        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
          keyboardShouldPersistTaps="handled"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={GREEN} />}
        >
          {loading ? <View style={{ paddingVertical: 60, alignItems: 'center' }}><ActivityIndicator color={GREEN} size="large" /></View> : (
            <>
              <View style={s.statRow}>
                <Stat label="Pending" value={`${status?.pending ?? 0}`} color={AMBER} />
                <Stat label="Accepted" value={`${status?.accepted ?? 0}`} color={GREEN} />
                <Stat label="Rejected" value={`${status?.rejected ?? 0}`} color={RED} />
                <Stat label="Wiki" value={`${status?.wiki_size ?? 0}`} color={BLUE} />
              </View>

              <View style={s.rolesCard}>
                <Role icon="shield-checkmark" color={GREEN} title="Grader" role="Defense (pro)" />
                <Role icon="library" color={RED} title="Library" role="Prosecution (con)" />
                <Role icon="people" color={PURPLE} title="Jury" role="Scrutinize" />
              </View>

              <Text style={s.h2}>📥 Submit information for judgment</Text>
              <View style={s.card}>
                <TextInput testID="jury-topic" style={s.input} value={topic} onChangeText={setTopic} placeholder="topic" placeholderTextColor={MUTE} editable={!busy} />
                <TextInput testID="jury-content" style={[s.input, { marginTop: 8, height: 76, textAlignVertical: 'top' }]} value={content} onChangeText={setContent} placeholder="information / claim to adjudicate…" placeholderTextColor={MUTE} multiline editable={!busy} />
                <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
                  <TouchableOpacity testID="jury-submit" style={[s.btn, { backgroundColor: GREEN }]} onPress={submit} disabled={busy}>
                    <Text style={s.btnTxt}>{busy ? '…' : 'Submit → adjudicate'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="jury-tick" style={[s.btn, { backgroundColor: BLUE }]} onPress={runTick} disabled={busy}>
                    <Text style={[s.btnTxt, { color: '#fff' }]}>Run pipeline tick</Text>
                  </TouchableOpacity>
                </View>
                {!!msg && <Text style={s.msg}>{msg}</Text>}
              </View>

              <Text style={s.h2}>⚖️ Verdicts ({verdicts.length}) · accept {status?.accept_rate ?? 0}%</Text>
              {verdicts.length === 0 ? <Text style={s.empty}>No cases yet — submit info or run a tick.</Text> : verdicts.map((c: any) => {
                const col = VERDICT_COLOR[c.verdict] || MUTE;
                const open = expanded === c.id;
                return (
                  <View key={c.id} style={s.caseCard}>
                    <TouchableOpacity testID={`jury-case-${c.id}`} style={s.caseHead} onPress={() => setExpanded(open ? null : c.id)}>
                      <View style={[s.vBadge, { borderColor: col, backgroundColor: col + '22' }]}><Text style={[s.vBadgeTxt, { color: col }]}>{c.verdict}</Text></View>
                      <Text style={s.caseTopic} numberOfLines={1}>{c.topic}</Text>
                      <Text style={[s.scrutiny, { color: col }]}>{Math.round((c.jury?.scrutiny_score ?? 0) * 100)}%</Text>
                      <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={14} color={MUTE} />
                    </TouchableOpacity>
                    <Text style={s.caseSrc}>source: {c.source}</Text>
                    {open && (
                      <View style={{ marginTop: 8 }}>
                        <Text style={[s.side, { color: GREEN }]}>🛡️ Defense (Grader) · pro {Math.round((c.defense?.pro_score ?? 0) * 100)}%</Text>
                        {(c.defense?.arguments || []).map((a: string, i: number) => <Text key={i} style={s.arg}>+ {a}</Text>)}
                        <Text style={[s.side, { color: RED, marginTop: 8 }]}>⚔️ Prosecution (Library) · con {Math.round((c.prosecution?.con_score ?? 0) * 100)}%</Text>
                        {(c.prosecution?.arguments || []).map((a: string, i: number) => <Text key={i} style={s.arg}>− {a}</Text>)}
                        <Text style={[s.side, { color: PURPLE, marginTop: 8 }]}>👥 Jury scrutiny</Text>
                        {Object.entries(c.jury?.rubric || {}).map(([k, v]: any) => (
                          <View key={k} style={s.rubricRow}>
                            <Text style={s.rubricLbl}>{k}</Text>
                            <View style={s.rubricTrack}><View style={[s.rubricFill, { width: `${Math.round(v * 100)}%` }]} /></View>
                            <Text style={s.rubricVal}>{Math.round(v * 100)}%</Text>
                          </View>
                        ))}
                        {c.verdict === 'accepted' && <Text style={[s.msg, { color: GREEN }]}>✓ Written to wiki after scrutiny.</Text>}
                        {c.verdict === 'rejected' && <Text style={[s.msg, { color: RED }]}>✗ Rejected — held in Boardroom, not in wiki.</Text>}
                        {c.verdict === 'revise' && <Text style={[s.msg, { color: AMBER }]}>↺ Needs revision before wiki.</Text>}
                      </View>
                    )}
                  </View>
                );
              })}
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return <View style={s.stat}><Text style={[s.statVal, { color }]}>{value}</Text><Text style={s.statLbl}>{label}</Text></View>;
}
function Role({ icon, color, title, role }: { icon: any; color: string; title: string; role: string }) {
  return (
    <View style={s.role}>
      <Ionicons name={icon} size={18} color={color} />
      <Text style={s.roleTitle}>{title}</Text>
      <Text style={[s.roleSub, { color }]}>{role}</Text>
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
  statRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  stat: { flex: 1, backgroundColor: CARD, borderRadius: 12, paddingVertical: 13, alignItems: 'center' },
  statVal: { fontSize: 18, fontWeight: '800' },
  statLbl: { color: MUTE, fontSize: 10, marginTop: 2 },
  rolesCard: { flexDirection: 'row', backgroundColor: CARD, borderRadius: 14, padding: 12, gap: 8 },
  role: { flex: 1, alignItems: 'center', gap: 3 },
  roleTitle: { color: '#f1f5f9', fontSize: 12, fontWeight: '700' },
  roleSub: { fontSize: 10, fontWeight: '600' },
  h2: { color: '#e2e8f0', fontSize: 14, fontWeight: '700', marginTop: 18, marginBottom: 8 },
  card: { backgroundColor: CARD, borderRadius: 14, padding: 14 },
  input: { backgroundColor: '#0b1220', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, color: '#f1f5f9', fontSize: 13, borderWidth: StyleSheet.hairlineWidth, borderColor: '#243043' },
  btn: { flex: 1, borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  btnTxt: { color: '#04120a', fontSize: 13, fontWeight: '800' },
  msg: { color: GREEN, fontSize: 12, marginTop: 10 },
  empty: { color: MUTE, fontSize: 12, fontStyle: 'italic', textAlign: 'center', paddingVertical: 20 },
  caseCard: { backgroundColor: CARD, borderRadius: 12, padding: 12, marginBottom: 8 },
  caseHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  vBadge: { borderRadius: 6, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 2 },
  vBadgeTxt: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  caseTopic: { color: '#f1f5f9', fontSize: 13, fontWeight: '600', flex: 1 },
  scrutiny: { fontSize: 12, fontWeight: '800' },
  caseSrc: { color: MUTE, fontSize: 10, marginTop: 4 },
  side: { fontSize: 12, fontWeight: '700' },
  arg: { color: '#cbd5e1', fontSize: 12, marginTop: 2, marginLeft: 4 },
  rubricRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  rubricLbl: { color: MUTE, fontSize: 11, width: 84, textTransform: 'capitalize' },
  rubricTrack: { flex: 1, height: 6, borderRadius: 3, backgroundColor: '#1e293b', overflow: 'hidden' },
  rubricFill: { height: 6, borderRadius: 3, backgroundColor: PURPLE },
  rubricVal: { color: '#cbd5e1', fontSize: 11, width: 34, textAlign: 'right' },
});
