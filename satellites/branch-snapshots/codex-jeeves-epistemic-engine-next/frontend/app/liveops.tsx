/**
 * /liveops — Live-Ops Engine: current season, rotating events, and a battle pass.
 *
 * Shows the active season + events, the visitor's battle-pass progress with
 * tiered rewards, and an action that earns XP (XP is server-authoritative).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import { safeGetItem, safeSetItem } from '../utils/safeStorage';

async function getVisitorId(): Promise<string> {
  let id = await safeGetItem('mkt_visitor_id');
  if (!id) {
    id = 'v_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    await safeSetItem('mkt_visitor_id', id);
  }
  return id;
}

type Tier = { tier: number; xp: number; reward: string; unlocked?: boolean; free?: boolean };
type Event = { id: string; name: string; desc: string; multiplier: number };
type Season = { season_id: string; name: string; week: number; ends_at: string; events: Event[]; xp_multiplier: number };

export default function LiveOps() {
  const router = useRouter();
  const haptics = useHaptics();
  const [visitor, setVisitor] = React.useState('');
  const [season, setSeason] = React.useState<Season | null>(null);
  const [xp, setXp] = React.useState(0);
  const [tier, setTier] = React.useState(1);
  const [nextXp, setNextXp] = React.useState<number | null>(null);
  const [tiers, setTiers] = React.useState<Tier[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [toast, setToast] = React.useState<string | null>(null);

  const loadPass = React.useCallback(async (vid: string) => {
    const r = await api.get<any>(`/api/liveops/pass?visitor_id=${encodeURIComponent(vid)}`, { timeoutMs: 12000 });
    if (r.ok && r.data) {
      setXp(r.data.xp || 0); setTier(r.data.tier || 1);
      setNextXp(r.data.next_xp ?? null); setTiers(r.data.tiers || []);
    }
  }, []);

  const refreshAll = React.useCallback(async (vid: string) => {
    const s = await api.get<{ season: Season }>('/api/liveops/season', { timeoutMs: 12000 });
    if (s.ok && s.data) setSeason(s.data.season);
    await loadPass(vid);
  }, [loadPass]);

  React.useEffect(() => {
    (async () => {
      const v = await getVisitorId(); setVisitor(v);
      const s = await api.get<{ season: Season }>('/api/liveops/season', { timeoutMs: 12000 });
      if (s.ok && s.data) setSeason(s.data.season);
      await loadPass(v);
      setLoading(false);
    })();
  }, [loadPass]);

  const earn = React.useCallback(async (action: string) => {
    if (!visitor) return;
    haptics.selection();
    const r = await api.post<any>('/api/liveops/xp', { visitor_id: visitor, action }, { timeoutMs: 10000 });
    if (r.ok && r.data?.ok) {
      setXp(r.data.xp); setTier(r.data.tier);
      const unlocked = r.data.unlocked_rewards || [];
      setToast(r.data.tier_up ? `🎉 Tier ${r.data.tier}! Unlocked: ${unlocked.join(', ')}` : `+${r.data.gained} XP`);
      if (r.data.tier_up) haptics.notify('success');
      loadPass(visitor);
      setTimeout(() => setToast(null), 2600);
    }
  }, [visitor, haptics, loadPass]);

  const progress = nextXp ? Math.min(1, xp / nextXp) : 1;

  return (
    <SafeAreaView style={styles.safe} testID="liveops-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="lo-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🎟️ Live-Ops</Text>
      </View>

      {toast ? <View testID="lo-toast" style={styles.toast}><Text style={styles.toastTxt}>{toast}</Text></View> : null}

      {loading ? <ActivityIndicator color="#A78BFA" style={{ marginTop: 50 }} /> : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
          refreshControl={<RefreshControl refreshing={refreshing} tintColor="#A78BFA"
            onRefresh={async () => { if (!visitor) return; setRefreshing(true); await refreshAll(visitor); setRefreshing(false); }} />}
        >
          {season ? (
            <View testID="lo-season" style={styles.seasonCard}>
              <Text style={styles.seasonName}>🌟 {season.name}</Text>
              <Text style={styles.seasonMeta}>Season {season.season_id}{season.xp_multiplier > 1 ? `  ·  ⚡ ${season.xp_multiplier}× XP` : ''}</Text>
              <View style={styles.eventRow}>
                {season.events.map((e) => (
                  <View key={e.id} testID={`lo-event-${e.id}`} style={styles.eventChip}>
                    <Text style={styles.eventName}>{e.name}</Text>
                    <Text style={styles.eventDesc}>{e.desc}</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}

          <View style={styles.passHead}>
            <Text style={styles.passTitle}>Battle Pass · Tier {tier}</Text>
            <Text style={styles.xpTxt}>{xp} XP{nextXp ? ` / ${nextXp}` : ' · MAX'}</Text>
          </View>
          <View style={styles.progressTrack}><View testID="lo-progress" style={[styles.progressFill, { width: `${progress * 100}%` }]} /></View>

          <View style={styles.earnRow}>
            <TouchableOpacity testID="lo-earn-play" style={styles.earnBtn} onPress={() => earn('play')}><Text style={styles.earnTxt}>▶ Play +5</Text></TouchableOpacity>
            <TouchableOpacity testID="lo-earn-share" style={styles.earnBtn} onPress={() => earn('share')}><Text style={styles.earnTxt}>🔗 Share +4</Text></TouchableOpacity>
            <TouchableOpacity testID="lo-earn-vote" style={styles.earnBtn} onPress={() => earn('vote')}><Text style={styles.earnTxt}>▲ Vote +3</Text></TouchableOpacity>
          </View>

          <Text style={styles.sectionTitle}>Rewards track</Text>
          {tiers.map((t) => (
            <View key={t.tier} testID={`lo-tier-${t.tier}`} style={[styles.tierRow, t.unlocked && styles.tierUnlocked]}>
              <View style={[styles.tierBadge, t.unlocked && styles.tierBadgeOn]}><Text style={styles.tierNum}>{t.tier}</Text></View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.tierReward}>{t.reward}</Text>
                <Text style={styles.tierXp}>{t.xp} XP{t.free ? ' · free' : ''}</Text>
              </View>
              <Text style={styles.tierState}>{t.unlocked ? '✅' : '🔒'}</Text>
            </View>
          ))}
          <Text style={styles.hint}>Earn XP by playing, sharing, voting, generating and buying games. Events can multiply your XP. Browse games on the <Text style={styles.link} onPress={() => router.push('/discover')}>Discover</Text> feed.</Text>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#262626' },
  backBtn: { paddingVertical: 6, paddingRight: 12 }, backTxt: { color: '#94a3b8', fontSize: 15 },
  title: { flex: 1, color: '#f1f5f9', fontSize: 20, fontWeight: '800' },
  toast: { backgroundColor: '#2E1B5B', margin: 12, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: '#8B5CF6' }, toastTxt: { color: '#e0e7ff', fontWeight: '700' },
  seasonCard: { backgroundColor: '#141414', borderRadius: 14, padding: 16, borderWidth: 1, borderColor: '#2E1B5B', marginBottom: 20 },
  seasonName: { color: '#f5d0fe', fontSize: 20, fontWeight: '800' }, seasonMeta: { color: '#a78bfa', fontSize: 13, marginTop: 4 },
  eventRow: { marginTop: 12, gap: 8 },
  eventChip: { backgroundColor: '#141414', borderRadius: 10, padding: 10, borderWidth: 1, borderColor: '#262626' },
  eventName: { color: '#e2e8f0', fontWeight: '700' }, eventDesc: { color: '#64748b', fontSize: 12, marginTop: 2 },
  passHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 8 },
  passTitle: { color: '#f1f5f9', fontSize: 16, fontWeight: '800' }, xpTxt: { color: '#A78BFA', fontWeight: '700' },
  progressTrack: { height: 12, backgroundColor: '#262626', borderRadius: 8, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#A78BFA', borderRadius: 8 },
  earnRow: { flexDirection: 'row', gap: 8, marginVertical: 16 },
  earnBtn: { flex: 1, backgroundColor: '#262626', borderRadius: 10, paddingVertical: 11, alignItems: 'center' }, earnTxt: { color: '#e2e8f0', fontWeight: '700', fontSize: 13 },
  sectionTitle: { color: '#cbd5e1', fontSize: 15, fontWeight: '800', marginBottom: 10, marginTop: 4 },
  tierRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', borderRadius: 12, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: '#262626' },
  tierUnlocked: { borderColor: '#8B5CF6', backgroundColor: '#160f24' },
  tierBadge: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#262626', alignItems: 'center', justifyContent: 'center' }, tierBadgeOn: { backgroundColor: '#8B5CF6' },
  tierNum: { color: '#fff', fontWeight: '800' },
  tierReward: { color: '#e2e8f0', fontWeight: '700' }, tierXp: { color: '#64748b', fontSize: 12, marginTop: 2 },
  tierState: { fontSize: 18 },
  hint: { color: '#64748b', fontSize: 13, marginTop: 14, lineHeight: 20 }, link: { color: '#A78BFA', fontWeight: '700' },
});
