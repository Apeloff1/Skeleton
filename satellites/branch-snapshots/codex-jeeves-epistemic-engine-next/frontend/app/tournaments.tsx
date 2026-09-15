/**
 * /tournaments — Seasonal Tournaments (single-elimination brackets over games).
 *
 * Create an auto-seeded bracket from the top ready games, vote head-to-head
 * matches, then advance rounds until a champion is crowned and a rotating
 * reward is awarded.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
  StyleSheet, SafeAreaView, Image, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Slot = { playable_id: string; title?: string; seed?: number; has_cover?: boolean };
type Match = { match_id: string; a: Slot; b: Slot; votes: { a: number; b: number }; winner: string | null };
type Tournament = {
  tournament_id: string; name: string; theme?: string; size: number;
  status: 'live' | 'complete'; current_round: number; rounds: Match[][];
  champion_id?: string | null; champion?: Slot; reward?: string;
};

function MiniCover({ id, hasCover, size = 30 }: { id?: string; hasCover?: boolean; size?: number }) {
  const [err, setErr] = React.useState(false);
  if (!id || !hasCover || err) return <View style={[styles.mini, { width: size, height: size }]}><Text>🎮</Text></View>;
  return <Image source={{ uri: `${BACKEND}/api/playable/${id}/cover.png` }} style={{ width: size, height: size, borderRadius: 6 }} onError={() => setErr(true)} />;
}

export default function Tournaments() {
  const router = useRouter();
  const haptics = useHaptics();
  const [list, setList] = React.useState<Tournament[]>([]);
  const [active, setActive] = React.useState<Tournament | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [size, setSize] = React.useState(4);
  const [name, setName] = React.useState('');
  const [msg, setMsg] = React.useState<string | null>(null);

  const loadList = React.useCallback(async () => {
    setLoading(true);
    const r = await api.get<{ tournaments: Tournament[] }>('/api/tournaments', { timeoutMs: 12000 });
    if (r.ok && r.data) setList(r.data.tournaments || []);
    setLoading(false);
  }, []);

  const open = React.useCallback(async (tid: string) => {
    const r = await api.get<{ tournament: Tournament }>(`/api/tournaments/${tid}`, { timeoutMs: 12000 });
    if (r.ok && r.data?.tournament) setActive(r.data.tournament);
  }, []);

  React.useEffect(() => { loadList(); }, [loadList]);

  const create = React.useCallback(async () => {
    setBusy(true); setMsg(null); haptics.selection();
    const r = await api.post<{ ok?: boolean; tournament?: Tournament; error?: string }>(
      '/api/tournaments/create', { name, size }, { timeoutMs: 15000 });
    setBusy(false);
    if (r.data?.ok && r.data.tournament) { setActive(r.data.tournament); setName(''); loadList(); haptics.notify('success'); }
    else setMsg(r.data?.error || 'Could not create tournament.');
  }, [name, size, haptics, loadList]);

  const vote = React.useCallback(async (tid: string, mid: string, slot: 'a' | 'b') => {
    haptics.selection();
    const r = await api.post<any>(`/api/tournaments/${tid}/match/${mid}/vote`, { slot }, { timeoutMs: 10000 });
    if (r.ok) open(tid);
  }, [haptics, open]);

  const advance = React.useCallback(async (tid: string) => {
    setBusy(true); haptics.selection();
    const r = await api.post<any>(`/api/tournaments/${tid}/advance`, {}, { timeoutMs: 12000 });
    setBusy(false);
    if (r.ok) { open(tid); loadList(); if (r.data?.status === 'complete') haptics.notify('success'); }
  }, [haptics, open, loadList]);

  if (active) {
    const round = active.rounds[active.current_round] || [];
    return (
      <SafeAreaView style={styles.safe} testID="tournament-detail">
        <View style={styles.header}>
          <TouchableOpacity testID="trn-back-list" onPress={() => setActive(null)} style={styles.backBtn}><Text style={styles.backTxt}>‹ Brackets</Text></TouchableOpacity>
          <Text style={styles.title} numberOfLines={1}>{active.name}</Text>
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
          <Text style={styles.meta}>Bracket of {active.size} · Round {active.current_round + 1} · {active.status === 'complete' ? '🏆 Complete' : 'Live'}</Text>
          {active.status === 'complete' && active.champion ? (
            <View testID="trn-champion" style={styles.champBox}>
              <MiniCover id={active.champion.playable_id} hasCover={active.champion.has_cover} size={64} />
              <View style={{ marginLeft: 14, flex: 1 }}>
                <Text style={styles.champLabel}>👑 CHAMPION</Text>
                <Text style={styles.champTitle} numberOfLines={2}>{active.champion.title}</Text>
                <Text style={styles.reward}>{active.reward}</Text>
              </View>
            </View>
          ) : null}

          {active.status === 'live' ? round.map((m) => (
            <View key={m.match_id} testID={`trn-match-${m.match_id}`} style={styles.matchCard}>
              {(['a', 'b'] as const).map((slot) => {
                const s = m[slot];
                const won = m.winner === s.playable_id;
                return (
                  <TouchableOpacity key={slot} testID={`trn-vote-${m.match_id}-${slot}`} style={[styles.fighter, won && styles.fighterWon]} disabled={!!m.winner} onPress={() => vote(active.tournament_id, m.match_id, slot)}>
                    <MiniCover id={s.playable_id} hasCover={s.has_cover} />
                    <Text style={styles.fighterTitle} numberOfLines={1}>#{s.seed} {s.title}</Text>
                    <Text style={styles.voteCount}>▲ {m.votes[slot]}</Text>
                  </TouchableOpacity>
                );
              })}
              <Text style={styles.vs}>VS</Text>
            </View>
          )) : null}

          {active.status === 'live' ? (
            <TouchableOpacity testID="trn-advance" style={[styles.advanceBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => advance(active.tournament_id)}>
              <Text style={styles.advanceTxt}>{busy ? '…' : (round.length === 1 ? '🏆 Crown the Champion' : '⏭️ Resolve Round → Next')}</Text>
            </TouchableOpacity>
          ) : null}
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} testID="tournaments-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="trn-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🏆 Tournaments</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={loading} tintColor="#A78BFA" onRefresh={loadList} />}
      >
        <View style={styles.createBox}>
          <Text style={styles.createTitle}>Create a bracket</Text>
          <TextInput testID="trn-name" style={styles.input} value={name} onChangeText={setName} placeholder="Tournament name (optional)" placeholderTextColor="#475569" />
          <View style={styles.sizeRow}>
            {[4, 8, 16].map((s) => (
              <TouchableOpacity key={s} testID={`trn-size-${s}`} style={[styles.sizeChip, size === s && styles.sizeChipActive]} onPress={() => setSize(s)}>
                <Text style={[styles.sizeTxt, size === s && styles.sizeTxtActive]}>{s} games</Text>
              </TouchableOpacity>
            ))}
          </View>
          {msg ? <Text style={styles.errMsg}>{msg}</Text> : null}
          <TouchableOpacity testID="trn-create" style={[styles.createBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={create}>
            <Text style={styles.advanceTxt}>{busy ? 'Seeding…' : '⚔️ Auto-seed & Start'}</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionTitle}>Brackets</Text>
        {loading ? <ActivityIndicator color="#A78BFA" style={{ marginTop: 20 }} /> : null}
        {!loading && list.length === 0 ? <Text style={styles.empty}>No tournaments yet — create one above.</Text> : null}
        {list.map((t) => (
          <TouchableOpacity key={t.tournament_id} testID={`trn-row-${t.tournament_id}`} style={styles.row} onPress={() => open(t.tournament_id)}>
            <Text style={{ fontSize: 22 }}>{t.status === 'complete' ? '🏆' : '⚔️'}</Text>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>{t.name}</Text>
              <Text style={styles.rowSub}>Bracket of {t.size} · {t.status === 'complete' ? 'Complete' : `Round ${t.current_round + 1}`}</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#262626' },
  backBtn: { paddingVertical: 6, paddingRight: 12 }, backTxt: { color: '#94a3b8', fontSize: 15 },
  title: { flex: 1, color: '#f1f5f9', fontSize: 20, fontWeight: '800' },
  meta: { color: '#94a3b8', fontSize: 13, marginBottom: 14 },
  createBox: { backgroundColor: '#141414', borderRadius: 14, padding: 16, borderWidth: 1, borderColor: '#2E1B5B', marginBottom: 20 },
  createTitle: { color: '#f1f5f9', fontSize: 16, fontWeight: '800', marginBottom: 10 },
  input: { backgroundColor: '#0A0A0A', borderRadius: 10, borderWidth: 1, borderColor: '#404040', color: '#e2e8f0', paddingHorizontal: 12, paddingVertical: 10 },
  sizeRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  sizeChip: { flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: '#1F1F1F', borderWidth: 1, borderColor: '#262626', alignItems: 'center' }, sizeChipActive: { backgroundColor: '#2E1B5B', borderColor: '#8B5CF6' },
  sizeTxt: { color: '#94a3b8', fontWeight: '700' }, sizeTxtActive: { color: '#e0e7ff' },
  errMsg: { color: '#fca5a5', marginTop: 10, fontSize: 13 },
  createBtn: { backgroundColor: '#8B5CF6', borderRadius: 10, paddingVertical: 13, alignItems: 'center', marginTop: 14 },
  advanceBtn: { backgroundColor: '#16a34a', borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 8 },
  advanceTxt: { color: '#fff', fontWeight: '800', fontSize: 15 },
  sectionTitle: { color: '#cbd5e1', fontSize: 15, fontWeight: '800', marginBottom: 10 },
  empty: { color: '#64748b', textAlign: 'center', marginTop: 20 },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#262626' },
  rowTitle: { color: '#e2e8f0', fontSize: 15, fontWeight: '700' }, rowSub: { color: '#64748b', fontSize: 12, marginTop: 3 },
  chevron: { color: '#475569', fontSize: 24 },
  mini: { borderRadius: 6, backgroundColor: '#141414', alignItems: 'center', justifyContent: 'center' },
  matchCard: { backgroundColor: '#141414', borderRadius: 12, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: '#262626', position: 'relative' },
  fighter: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', borderRadius: 10, padding: 10, marginVertical: 4, borderWidth: 1, borderColor: '#262626' },
  fighterWon: { borderColor: '#22c55e', backgroundColor: '#0f1f16' },
  fighterTitle: { flex: 1, color: '#e2e8f0', marginLeft: 10, fontSize: 13 },
  voteCount: { color: '#A78BFA', fontWeight: '800', marginLeft: 8 },
  vs: { position: 'absolute', right: 16, top: '50%', color: '#475569', fontWeight: '800', fontSize: 12 },
  champBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1c1503', borderRadius: 14, padding: 16, borderWidth: 1, borderColor: '#a16207', marginBottom: 20 },
  champLabel: { color: '#fbbf24', fontWeight: '800', fontSize: 12 },
  champTitle: { color: '#fef3c7', fontSize: 16, fontWeight: '800', marginTop: 3 },
  reward: { color: '#fcd34d', marginTop: 6, fontSize: 14 },
});
