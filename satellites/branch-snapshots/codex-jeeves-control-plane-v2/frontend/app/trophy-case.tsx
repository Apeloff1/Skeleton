/**
 * /trophy-case — 🏆 Trophy Case.
 * Surfaces the previously-stranded `tournament_rewards` collection via
 * GET /api/tournaments/rewards/ledger — every reward ever awarded to a champion.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { speakCinematic, stopCinematic } from '../src/utils/cinematicVoice';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Reward = {
  reward: string;
  awarded_at?: string;
  tournament_id?: string;
  game?: { playable_id?: string; title?: string; genre?: string };
};

export default function TrophyCase() {
  const router = useRouter();
  const [rewards, setRewards] = React.useState<Reward[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [crowning, setCrowning] = React.useState(false);
  const autoPlayed = React.useRef(false);

  const crownLine = React.useCallback((list: Reward[]) => {
    const latest = list[0];
    const champ = latest?.reward || 'A champion';
    const game = latest?.game?.title || latest?.game?.playable_id || 'the arena';
    return `A champion is crowned! ${champ}, victor of ${game}. The crowd rises — the trophy is yours, and the legend is sealed.`;
  }, []);

  const playCrown = React.useCallback(async (list: Reward[]) => {
    if (!list.length) return;
    setCrowning(true);
    try { await speakCinematic(crownLine(list), { tone: 'triumphant' }); } catch {}
    setCrowning(false);
  }, [crownLine]);

  const load = React.useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND}/api/tournaments/rewards/ledger`);
      const j = await r.json();
      const list = Array.isArray(j?.rewards) ? j.rewards : [];
      setRewards(list);
      // Auto-play the celebratory line once, on first successful load with rewards.
      if (!autoPlayed.current && list.length > 0) {
        autoPlayed.current = true;
        playCrown(list);
      }
    } catch { /* keep prior */ }
    setLoading(false);
    setRefreshing(false);
  }, [playCrown]);

  React.useEffect(() => { load(); }, [load]);
  React.useEffect(() => () => { stopCinematic(); }, []);

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="trophy-back" onPress={() => router.back()} style={s.hBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.hTitle}>🏆 Trophy Case</Text>
        <TouchableOpacity
          testID="trophy-crown-voice"
          onPress={() => playCrown(rewards)}
          disabled={crowning || rewards.length === 0}
          style={s.hBtn}
        >
          <Ionicons
            name={crowning ? 'volume-high' : 'volume-medium-outline'}
            size={22}
            color={rewards.length === 0 ? '#57534e' : '#fbbf24'}
          />
        </TouchableOpacity>
      </View>

      {loading ? (
        <ActivityIndicator color="#fbbf24" style={{ marginTop: 40 }} />
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 48 }}
          refreshControl={<RefreshControl refreshing={refreshing} tintColor="#fbbf24"
            onRefresh={() => { setRefreshing(true); load(); }} />}
        >
          <Text style={s.intro}>Every crown earned across the arenas. {rewards.length} award{rewards.length === 1 ? '' : 's'}.</Text>
          {rewards.length === 0 ? (
            <View style={s.empty}>
              <Text style={s.emptyEmoji}>🏟️</Text>
              <Text style={s.emptyTxt}>No champions crowned yet. Win a tournament to fill the case!</Text>
            </View>
          ) : rewards.map((r, i) => (
            <View key={i} style={s.card}>
              <Text style={s.trophy}>🏆</Text>
              <View style={{ flex: 1 }}>
                <Text style={s.reward}>{r.reward || 'Champion'}</Text>
                <Text style={s.game} numberOfLines={1}>{r.game?.title || r.game?.playable_id || 'Unknown game'}</Text>
                {!!r.awarded_at && <Text style={s.date}>{String(r.awarded_at).slice(0, 10)}</Text>}
              </View>
              {!!r.game?.genre && <View style={s.genrePill}><Text style={s.genreTxt}>{r.game.genre}</Text></View>}
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#14110a' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#1f1a0d', borderBottomWidth: 1, borderBottomColor: '#3a2f14' },
  hBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  hTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: '#F8FAFC' },
  intro: { color: '#a8a29e', fontSize: 13, marginBottom: 14 },
  empty: { alignItems: 'center', marginTop: 40, paddingHorizontal: 24 },
  emptyEmoji: { fontSize: 48, marginBottom: 12 },
  emptyTxt: { color: '#a8a29e', fontSize: 14, textAlign: 'center', lineHeight: 20 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#1f1a0d', borderRadius: 14, borderWidth: 1, borderColor: '#fbbf2433', padding: 14, marginBottom: 10 },
  trophy: { fontSize: 30 },
  reward: { color: '#fde68a', fontSize: 15, fontWeight: '800' },
  game: { color: '#e7e5e4', fontSize: 13, marginTop: 2 },
  date: { color: '#78716c', fontSize: 11, marginTop: 3 },
  genrePill: { backgroundColor: '#fbbf2422', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  genreTxt: { color: '#fbbf24', fontSize: 10, fontWeight: '800' },
});
