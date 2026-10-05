/**
 * /creator — Creator Dashboard (DELUXE).
 * A premium command center: glass hero with Battle-Pass tier over a cinematic
 * gradient, KPI tiles (Revenue / Sales / Plays / Games), and the creator's
 * listed games with live status. Identity = local visitor id (shared w/ marketplace).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, Image, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import { getVisitorId } from '../src/utils/liveops';
import { C, S, R } from '../src/theme/deluxe';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const HERO_BG = 'https://images.unsplash.com/photo-1637825891028-564f672aa42c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzl8MHwxfHNlYXJjaHwzfHxhYnN0cmFjdCUyMGdyYWRpZW50JTIwZGFyayUyMHB1cnBsZSUyMG5lb24lMjB0ZXh0dXJlfGVufDB8fHx8MTc4MTg4NTA4MHww&ixlib=rb-4.1.0&q=85';

type Listing = {
  playable_id: string; title: string; genre: string; price_usd: number;
  has_cover?: boolean; sales?: number; revenue_usd?: number; active?: boolean;
  plays?: number; overall?: number; asset_status?: string;
};
type Totals = { games: number; active: number; sales: number; revenue_usd: number; plays: number };

function Cover({ id, hasCover, size = 52 }: { id: string; hasCover?: boolean; size?: number }) {
  const [err, setErr] = React.useState(false);
  if (!hasCover || err) return <View style={[styles.coverFallback, { width: size, height: size }]}><Text style={{ fontSize: size * 0.42 }}>🎮</Text></View>;
  return <Image source={{ uri: `${BACKEND}/api/playable/${id}/cover.png` }} style={{ width: size, height: size, borderRadius: R.md, backgroundColor: C.surface2 }} onError={() => setErr(true)} />;
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <View style={styles.kpi} testID={`cd-kpi-${label.toLowerCase()}`}>
      <Text style={[styles.kpiValue, accent ? { color: accent } : null]}>{value}</Text>
      <Text style={styles.kpiLabel}>{label}</Text>
    </View>
  );
}

export default function CreatorDashboard() {
  const router = useRouter();
  const haptics = useHaptics();
  const [visitor, setVisitor] = React.useState('');
  const [listings, setListings] = React.useState<Listing[]>([]);
  const [totals, setTotals] = React.useState<Totals>({ games: 0, active: 0, sales: 0, revenue_usd: 0, plays: 0 });
  const [tier, setTier] = React.useState(1);
  const [xp, setXp] = React.useState(0);
  const [nextXp, setNextXp] = React.useState<number | null>(null);
  const [reward, setReward] = React.useState<string>('');
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [creators, setCreators] = React.useState<any[]>([]);
  const [notifs, setNotifs] = React.useState<any[]>([]);

  const load = React.useCallback(async (vid: string) => {
    const [mine, pass, trending, notes] = await Promise.all([
      api.get<{ listings: Listing[]; totals: Totals }>(`/api/marketplace/mine?creator_id=${encodeURIComponent(vid)}`, { timeoutMs: 12000 }),
      api.get<any>(`/api/liveops/pass?visitor_id=${encodeURIComponent(vid)}`, { timeoutMs: 12000 }),
      api.get<{ creators: any[] }>(`/api/marketplace/creators/trending?limit=10`, { timeoutMs: 12000 }),
      api.get<{ notifications: any[] }>(`/api/governance/notifications/${encodeURIComponent(vid)}`, { timeoutMs: 12000 }),
    ]);
    if (mine.ok && mine.data) { setListings(mine.data.listings || []); setTotals(mine.data.totals); }
    if (trending.ok && trending.data) setCreators(trending.data.creators || []);
    if (notes.ok && notes.data) setNotifs(notes.data.notifications || []);
    if (pass.ok && pass.data) {
      setXp(pass.data.xp || 0); setTier(pass.data.tier || 1); setNextXp(pass.data.next_xp ?? null);
      const t = (pass.data.tiers || []).find((x: any) => x.tier === pass.data.tier);
      setReward(t?.reward || '');
    }
  }, []);

  React.useEffect(() => { getVisitorId().then(async (v) => { setVisitor(v); await load(v); setLoading(false); }); }, [load]);

  const onRefresh = React.useCallback(async () => { setRefreshing(true); await load(visitor); setRefreshing(false); }, [visitor, load]);

  const dismissNotifs = React.useCallback(async () => {
    setNotifs([]);
    if (visitor) await api.post(`/api/governance/notifications/${encodeURIComponent(visitor)}/ack`, {}, { timeoutMs: 12000 });
  }, [visitor]);

  const progress = nextXp ? Math.min(1, xp / nextXp) : 1;

  return (
    <SafeAreaView style={styles.safe} testID="creator-dashboard">
      <ScrollView
        contentContainerStyle={{ paddingBottom: S.xxxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.brand} />}
      >
        {/* Cinematic glass hero */}
        {notifs.length > 0 ? (
          <View style={styles.notifBanner} testID="cd-appeal-notifs">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={styles.notifTitle}>⚖️ Appeal updates ({notifs.length})</Text>
              <TouchableOpacity testID="cd-notifs-dismiss" onPress={dismissNotifs} hitSlop={10}><Text style={styles.notifDismiss}>Dismiss</Text></TouchableOpacity>
            </View>
            {notifs.slice(0, 4).map((n) => (
              <Text key={n.appeal_id} style={styles.notifRow} numberOfLines={2}>
                {n.status === 'granted' ? '✅' : '❌'} “{n.title}” — appeal {n.status === 'granted' ? 'granted, game restored' : 'denied'}
                {n.note ? `: ${n.note}` : ''}
              </Text>
            ))}
          </View>
        ) : null}
        <View style={styles.hero}>
          <Image source={{ uri: HERO_BG }} style={StyleSheet.absoluteFill as any} resizeMode="cover" />
          <LinearGradient colors={['rgba(10,10,10,0.30)', 'rgba(10,10,10,0.75)', C.bg]} style={StyleSheet.absoluteFill as any} />
          <View style={styles.heroTop}>
            <TouchableOpacity testID="cd-back" onPress={() => router.back()} hitSlop={10}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
            <Text style={styles.kicker}>CREATOR STUDIO</Text>
          </View>
          <BlurView intensity={28} tint="dark" style={styles.glassCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <View>
                <Text style={styles.passLabel}>BATTLE PASS</Text>
                <Text style={styles.tierBig} testID="cd-tier">Tier {tier}</Text>
                {reward ? <Text style={styles.rewardTxt} numberOfLines={1}>{reward}</Text> : null}
              </View>
              <View style={styles.tierMedallion}><Text style={styles.tierMedNum}>{tier}</Text></View>
            </View>
            <View style={styles.track}><View style={[styles.fill, { width: `${progress * 100}%` }]} /></View>
            <Text style={styles.xpHint}>{xp} XP{nextXp ? ` / ${nextXp} to next tier` : ' · MAX TIER'}</Text>
          </BlurView>
        </View>

        {loading ? <ActivityIndicator color={C.brand} style={{ marginTop: S.xxl }} /> : (
          <View style={{ paddingHorizontal: S.lg }}>
            {/* KPI grid */}
            <View style={styles.kpiGrid}>
              <Kpi label="Revenue" value={`$${totals.revenue_usd.toFixed(2)}`} accent={C.success} />
              <Kpi label="Sales" value={`${totals.sales}`} accent={C.brand2} />
              <Kpi label="Plays" value={`${totals.plays}`} accent={C.info} />
              <Kpi label="Games" value={`${totals.games}`} accent={C.warning} />
            </View>

            <View style={styles.sectionHead}>
              <Text style={styles.sectionTitle}>YOUR LISTINGS</Text>
              <TouchableOpacity testID="cd-go-market" onPress={() => { haptics.selection(); router.push('/marketplace' as any); }}>
                <Text style={styles.link}>Marketplace ›</Text>
              </TouchableOpacity>
            </View>

            {listings.length === 0 ? (
              <View style={styles.empty} testID="cd-empty">
                <Text style={{ fontSize: 40 }}>🪐</Text>
                <Text style={styles.emptyTitle}>No games listed yet</Text>
                <Text style={styles.emptyBody}>Generate a game, then tap “🛒 Sell” to list it. Your sales & revenue will show up here.</Text>
                <TouchableOpacity testID="cd-create" style={styles.cta} onPress={() => { haptics.selection(); router.push('/playable' as any); }}>
                  <Text style={styles.ctaTxt}>✨ Create a game</Text>
                </TouchableOpacity>
              </View>
            ) : listings.map((l) => (
              <TouchableOpacity key={l.playable_id} testID={`cd-listing-${l.playable_id}`} style={styles.row} onPress={() => router.push(`/playable?id=${l.playable_id}`)}>
                <Cover id={l.playable_id} hasCover={l.has_cover} />
                <View style={{ flex: 1, marginLeft: S.md, minWidth: 0 }}>
                  <Text style={styles.rowTitle} numberOfLines={1}>{l.title}{l.asset_status === 'complete' ? ' 🎨' : ''}</Text>
                  <Text style={styles.rowSub}>{l.genre} · ${ (l.price_usd || 0).toFixed(2)} · 🛒 {l.sales || 0} · ▶ {l.plays || 0}</Text>
                  {l.moderation_status && l.moderation_status !== 'ok' && l.moderation_note ? (
                    <Text testID={`cd-modnote-${l.playable_id}`} style={styles.modNote} numberOfLines={2}>⚖️ {l.moderation_note}</Text>
                  ) : null}
                </View>
                {l.moderation_status && l.moderation_status !== 'ok' ? (
                  <View testID={`cd-mod-${l.playable_id}`} style={[styles.badge, styles.badgeMod]}>
                    <Text style={[styles.badgeTxt, { color: C.gold }]}>{l.moderation_status === 'hidden' ? '🚫 HIDDEN' : l.moderation_status === 'warned' ? '⚠️ WARNED' : '⏳ REVIEW'}</Text>
                  </View>
                ) : null}
                <View style={[styles.badge, l.active ? styles.badgeLive : styles.badgeOff]}>
                  <Text style={[styles.badgeTxt, { color: l.active ? C.success : C.textMute }]}>{l.active ? 'LIVE' : 'OFF'}</Text>
                </View>
              </TouchableOpacity>
            ))}

            {/* Trending Creators leaderboard */}
            {creators.length > 0 ? (
              <View testID="cd-trending">
                <View style={styles.sectionHead}>
                  <Text style={styles.sectionTitle}>TRENDING CREATORS</Text>
                  <Text style={styles.small}>by revenue · sales · plays</Text>
                </View>
                {creators.map((c) => {
                  const isMe = c.creator_id === visitor;
                  const medal = c.rank === 1 ? '🥇' : c.rank === 2 ? '🥈' : c.rank === 3 ? '🥉' : `#${c.rank}`;
                  const name = isMe ? 'You' : `Creator ${String(c.creator_id).replace(/^v_/, '').slice(0, 5)}`;
                  return (
                    <View key={c.creator_id} testID={`cd-creator-${c.rank}`} style={[styles.row, isMe && styles.rowMe]}>
                      <Text style={styles.rankTxt}>{medal}</Text>
                      <View style={{ flex: 1, marginLeft: S.md, minWidth: 0 }}>
                        <Text style={[styles.rowTitle, isMe && { color: C.brand2 }]} numberOfLines={1}>{name}</Text>
                        <Text style={styles.rowSub}>{c.games} game{c.games === 1 ? '' : 's'} · 🛒 {c.sales} · ▶ {c.plays}</Text>
                      </View>
                      <Text style={styles.revTxt}>${(c.revenue_usd || 0).toFixed(2)}</Text>
                    </View>
                  );
                })}
              </View>
            ) : null}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  notifBanner: { backgroundColor: '#1e293b', borderWidth: 1, borderColor: C.gold, borderRadius: R.lg, margin: S.md, padding: S.md },
  notifTitle: { color: C.gold, fontSize: 14, fontWeight: '800' },
  notifDismiss: { color: C.textMute, fontSize: 13, fontWeight: '700' },
  notifRow: { color: C.textDim, fontSize: 13, marginTop: 8, lineHeight: 18 },
  hero: { height: 270, justifyContent: 'flex-end', paddingHorizontal: S.lg, paddingBottom: S.lg, overflow: 'hidden' },
  heroTop: { position: 'absolute', top: S.md, left: S.lg, right: S.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  backTxt: { color: C.textDim, fontSize: 15, fontWeight: '600' },
  kicker: { color: C.brand2, fontSize: 12, fontWeight: '800', letterSpacing: 2 },
  glassCard: { borderRadius: R.lg, padding: S.lg, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(139,92,246,0.35)', backgroundColor: 'rgba(20,20,20,0.45)' },
  passLabel: { color: C.brand2, fontSize: 11, fontWeight: '800', letterSpacing: 1.5 },
  tierBig: { color: C.text, fontSize: 30, fontWeight: '800', letterSpacing: 0.5, marginTop: 2 },
  rewardTxt: { color: C.gold, fontSize: 13, marginTop: 2 },
  tierMedallion: { width: 56, height: 56, borderRadius: 28, backgroundColor: C.brandDeep, borderWidth: 2, borderColor: C.brand, alignItems: 'center', justifyContent: 'center' },
  tierMedNum: { color: C.brand2, fontSize: 24, fontWeight: '800' },
  track: { height: 10, backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: R.pill, marginTop: S.md, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: C.brand, borderRadius: R.pill },
  xpHint: { color: C.textMute, fontSize: 12, marginTop: S.sm },
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: S.md, marginTop: S.lg },
  kpi: { width: '47%', flexGrow: 1, backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, paddingVertical: S.lg, paddingHorizontal: S.lg },
  kpiValue: { color: C.text, fontSize: 24, fontWeight: '800', letterSpacing: 0.5 },
  kpiLabel: { color: C.textMute, fontSize: 11, fontWeight: '700', letterSpacing: 1.2, marginTop: 4, textTransform: 'uppercase' },
  sectionHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: S.xl, marginBottom: S.md },
  sectionTitle: { color: C.textDim, fontSize: 13, fontWeight: '800', letterSpacing: 1.5 },
  link: { color: C.brand2, fontWeight: '700', fontSize: 13 },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: R.lg, padding: S.md, marginBottom: S.sm, borderWidth: 1, borderColor: C.border },
  coverFallback: { borderRadius: R.md, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { color: C.text, fontSize: 15, fontWeight: '700' },
  rowMe: { borderColor: C.brand, backgroundColor: '#160F24' },
  rankTxt: { color: C.gold, fontSize: 17, fontWeight: '800', width: 30, textAlign: 'center' },
  revTxt: { color: C.success, fontSize: 15, fontWeight: '800' },
  rowSub: { color: C.textMute, fontSize: 12, marginTop: 3 },
  badge: { paddingHorizontal: S.sm, paddingVertical: 4, borderRadius: R.sm, borderWidth: 1 },
  badgeLive: { borderColor: 'rgba(16,185,129,0.4)', backgroundColor: 'rgba(16,185,129,0.1)' },
  badgeOff: { borderColor: C.border, backgroundColor: C.surface2 },
  badgeMod: { borderColor: 'rgba(245,200,66,0.5)', backgroundColor: 'rgba(245,200,66,0.12)', marginRight: 6 },
  modNote: { color: C.gold, fontSize: 12, marginTop: 4, lineHeight: 16 },
  badgeTxt: { fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  empty: { alignItems: 'center', paddingVertical: S.xxl, paddingHorizontal: S.lg },
  emptyTitle: { color: C.text, fontSize: 17, fontWeight: '800', marginTop: S.md },
  emptyBody: { color: C.textMute, fontSize: 13, textAlign: 'center', lineHeight: 20, marginTop: S.sm },
  cta: { backgroundColor: C.brand, borderRadius: R.md, paddingVertical: S.md, paddingHorizontal: S.xl, marginTop: S.lg },
  ctaTxt: { color: '#fff', fontWeight: '800', fontSize: 15 },
});
