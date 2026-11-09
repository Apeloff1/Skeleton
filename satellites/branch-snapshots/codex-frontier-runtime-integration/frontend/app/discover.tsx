/**
 * /discover — Unified Discovery feed for Galaxy Studio.
 *
 * One smart-scrolling home that interleaves every discovery signal:
 *  🌟 Spotlight hero · 📅 Daily Challenge banner · 🗓️ Theme of the Week rail ·
 *  📈 Trending rail · ⭐ Staff Picks rail · ❤️ Most Loved rail.
 * Tapping any game opens /playable; a CTA links to the full leaderboard (/top).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, Image, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import theme from '../theme/tokens';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const C = theme.colors, S = theme.spacing, R = theme.radii;

interface Game {
  playable_id: string; title: string; genre: string; has_cover?: boolean;
  overall?: number; plays?: number; difficulty?: string; reactions_total?: number; velocity?: number;
}

function Cover({ g, size }: { g: Game; size: number }) {
  const [err, setErr] = React.useState(false);
  if (!g.has_cover || err) {
    return <View style={[styles.fallback, { width: size, height: size }]}><Text style={{ fontSize: size * 0.4 }}>🎮</Text></View>;
  }
  return (
    <Image source={{ uri: `${BACKEND}/api/playable/${g.playable_id}/cover.png` }} style={{ width: size, height: size, borderRadius: 12, backgroundColor: '#141414' }} resizeMode="cover" onError={() => setErr(true)} />
  );
}

export default function DiscoverScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [spotlight, setSpotlight] = React.useState<Game | null>(null);
  const [daily, setDaily] = React.useState<{ theme: string; prompt: string; count: number } | null>(null);
  const [trending, setTrending] = React.useState<Game[]>([]);
  const [themeWeek, setThemeWeek] = React.useState<{ theme: string; games: Game[] } | null>(null);
  const [staff, setStaff] = React.useState<Game[]>([]);
  const [loved, setLoved] = React.useState<Game[]>([]);
  const [affinity, setAffinity] = React.useState<Record<string, number>>({});

  // Local, no-auth personalization: remember which genres a visitor opens.
  React.useEffect(() => {
    AsyncStorage.getItem('discover_affinity').then((raw) => {
      if (raw) { try { setAffinity(JSON.parse(raw)); } catch { /* ignore */ } }
    });
  }, []);

  const open = React.useCallback((id: string, genre?: string) => {
    haptics.selection();
    if (genre) {
      setAffinity((prev) => {
        // Decay all genres so the feed adapts to RECENT taste, then bump this one.
        const next: Record<string, number> = {};
        for (const k in prev) { const v = prev[k] * 0.85; if (v >= 0.1) next[k] = Math.round(v * 100) / 100; }
        next[genre] = (next[genre] || 0) + 1;
        AsyncStorage.setItem('discover_affinity', JSON.stringify(next)).catch(() => {});
        return next;
      });
    }
    router.push(`/playable?id=${id}`);
  }, [haptics, router]);

  // 🎲 Surprise Me — jump to a random high-quality game, biased to your top genre.
  const surpriseMe = React.useCallback(async () => {
    haptics.notify('success');
    const top = Object.entries(affinity).sort((a, b) => b[1] - a[1])[0];
    const qs = top ? `?genre=${encodeURIComponent(top[0])}` : '';
    let r = await api.get<{ surprise: Game | null }>(`/api/playable/surprise${qs}`, { timeoutMs: 12_000 });
    let s = r.ok ? r.data?.surprise : null;
    if (!s && qs) { r = await api.get<{ surprise: Game | null }>('/api/playable/surprise', { timeoutMs: 12_000 }); s = r.ok ? r.data?.surprise : null; }
    if (s?.playable_id) { router.push(`/playable?id=${s.playable_id}`); }
  }, [affinity, haptics, router]);

  const loadAll = React.useCallback(async () => {
    const [sp, dl, tr, tw, st, lv] = await Promise.all([
      api.get<{ spotlight: Game | null }>('/api/playable/spotlight', { timeoutMs: 12_000 }),
      api.get<{ theme: string; prompt: string; count: number }>('/api/playable/daily', { timeoutMs: 12_000 }),
      api.get<{ trending: Game[] }>('/api/playable/trending?limit=12&hours=24', { timeoutMs: 12_000 }),
      api.get<{ theme: string; games: Game[] }>('/api/playable/theme-of-week?limit=12', { timeoutMs: 12_000 }),
      api.get<{ staff_picks: Game[] }>('/api/playable/staff-picks?limit=12', { timeoutMs: 12_000 }),
      api.get<{ most_loved: Game[] }>('/api/playable/most-loved?limit=12', { timeoutMs: 12_000 }),
    ]);
    if (sp.ok && sp.data) setSpotlight(sp.data.spotlight);
    if (dl.ok && dl.data) setDaily({ theme: dl.data.theme, prompt: dl.data.prompt, count: dl.data.count });
    if (tr.ok && tr.data) setTrending(tr.data.trending || []);
    if (tw.ok && tw.data) setThemeWeek({ theme: tw.data.theme, games: tw.data.games || [] });
    if (st.ok && st.data) setStaff(st.data.staff_picks || []);
    if (lv.ok && lv.data) setLoved(lv.data.most_loved || []);
    setLoading(false); setRefreshing(false);
  }, []);

  React.useEffect(() => { loadAll(); }, [loadAll]);

  // 🎯 "For You": de-duped pool ranked by the visitor's genre affinity.
  const forYou = React.useMemo(() => {
    if (!Object.keys(affinity).length) return [];
    const pool = new Map<string, Game>();
    [spotlight ? [spotlight] : [], trending, themeWeek?.games || [], staff, loved]
      .flat().forEach((g) => { if (g && !pool.has(g.playable_id)) pool.set(g.playable_id, g); });
    return [...pool.values()]
      .map((g) => ({ g, w: affinity[g.genre] || 0 }))
      .filter((x) => x.w > 0)
      .sort((a, b) => b.w - a.w)
      .slice(0, 12)
      .map((x) => x.g);
  }, [affinity, spotlight, trending, themeWeek, staff, loved]);

  const Rail = ({ id, label, games, badge }: { id: string; label: string; games: Game[]; badge?: (g: Game) => string }) => {
    if (!games.length) return null;
    return (
      <View testID={id} style={{ marginBottom: S.md }}>
        <Text style={styles.railLabel}>{label}</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.railRow}>
          {games.map((g) => (
            <TouchableOpacity key={g.playable_id} testID={`${id}-${g.playable_id}`} style={styles.card} activeOpacity={0.85} onPress={() => open(g.playable_id, g.genre)}>
              <Cover g={g} size={124} />
              <Text style={styles.cardTitle} numberOfLines={1}>{g.title}</Text>
              <Text style={styles.cardSub} numberOfLines={1}>{badge ? badge(g) : `⭐${g.overall ?? '–'} · ▶${g.plays ?? 0}`}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="dsc-back" hitSlop={theme.hitSlop.md} onPress={() => { try { { if (router.canGoBack()) router.back(); else router.replace('/playable'); } } catch { router.replace('/playable'); } }}>
          <Text style={styles.headerBtn}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>✨ Discover</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <TouchableOpacity testID="dsc-surprise" hitSlop={theme.hitSlop.sm} onPress={surpriseMe}>
            <Text style={styles.headerBtn}>🎲</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="dsc-board" hitSlop={theme.hitSlop.md} onPress={() => { haptics.selection(); router.push('/top'); }}>
            <Text style={styles.headerBtn}>🏆 Board</Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={C.accent} /></View>
      ) : (
        <ScrollView contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadAll(); }} tintColor={C.accent} />}>
          {spotlight ? (
            <TouchableOpacity testID="dsc-spotlight" activeOpacity={0.9} style={styles.hero} onPress={() => open(spotlight.playable_id, spotlight.genre)}>
              <Cover g={spotlight} size={92} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.heroLabel}>🌟 SPOTLIGHT · featured today</Text>
                <Text style={styles.heroTitle} numberOfLines={2}>{spotlight.title}</Text>
                <Text style={styles.heroMeta} numberOfLines={1}>{spotlight.genre} · ⭐{spotlight.overall ?? '–'} · ▶{spotlight.plays ?? 0}</Text>
              </View>
              <Text style={styles.heroPlay}>▶</Text>
            </TouchableOpacity>
          ) : null}

          {daily ? (
            <TouchableOpacity testID="dsc-daily" activeOpacity={0.9} style={styles.daily} onPress={() => { haptics.selection(); router.push(`/playable?brief=${encodeURIComponent(daily.prompt)}`); }}>
              <Text style={styles.dailyLabel}>📅 DAILY CHALLENGE · {daily.count} {daily.count === 1 ? 'entry' : 'entries'}</Text>
              <Text style={styles.dailyTheme} numberOfLines={2}>Build {daily.theme}</Text>
              <Text style={styles.dailyCta}>⚡ Tap to build today&apos;s challenge →</Text>
            </TouchableOpacity>
          ) : null}

          {forYou.length ? <Rail id="dsc-foryou" label="🎯 FOR YOU · based on what you play" games={forYou} /> : null}
          {themeWeek ? <Rail id="dsc-theme" label={`🗓️ THEME OF THE WEEK · ${themeWeek.theme}`} games={themeWeek.games} /> : null}
          <Rail id="dsc-trending" label="📈 TRENDING NOW" games={trending} badge={(g) => `⚡${g.velocity ?? 0} · ▶${g.plays ?? 0}`} />
          <Rail id="dsc-staff" label="⭐ STAFF PICKS" games={staff} />
          <Rail id="dsc-loved" label="❤️ MOST LOVED" games={loved} badge={(g) => `❤️${g.reactions_total ?? 0} · ⭐${g.overall ?? '–'}`} />

          <TouchableOpacity testID="dsc-full-board" style={styles.boardBtn} onPress={() => { haptics.selection(); router.push('/top'); }}>
            <Text style={styles.boardBtnTxt}>🏆 View the full leaderboard →</Text>
          </TouchableOpacity>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: S.base, paddingVertical: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  headerBtn: { color: C.accent, ...theme.typography.body, fontWeight: '700' },
  headerTitle: { color: C.text, ...theme.typography.h4, fontWeight: '800' },
  body: { paddingVertical: S.base, paddingBottom: 56 },
  fallback: { borderRadius: 12, backgroundColor: '#161b2e', alignItems: 'center', justifyContent: 'center' },
  hero: { flexDirection: 'row', alignItems: 'center', gap: S.md, marginHorizontal: S.base, marginBottom: S.sm, padding: S.md, borderRadius: R.xl, borderWidth: 1.5, borderColor: '#8B5CF6', backgroundColor: 'rgba(168,85,247,0.12)' },
  heroLabel: { color: '#d8b4fe', ...theme.typography.micro, fontWeight: '800', marginBottom: 2 },
  heroTitle: { color: C.text, ...theme.typography.h4, fontWeight: '800' },
  heroMeta: { color: C.textDim, ...theme.typography.caption, marginTop: 2 },
  heroPlay: { color: '#d8b4fe', fontSize: 22, fontWeight: '800' },
  daily: { marginHorizontal: S.base, marginBottom: S.md, padding: S.md, borderRadius: R.xl, borderWidth: 1.5, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.10)' },
  dailyLabel: { color: '#4ade80', ...theme.typography.micro, fontWeight: '800', marginBottom: 3 },
  dailyTheme: { color: C.text, ...theme.typography.h4, fontWeight: '800' },
  dailyCta: { color: '#86efac', ...theme.typography.caption, marginTop: 4, fontWeight: '700' },
  railLabel: { color: C.accentGold, ...theme.typography.micro, fontWeight: '800', marginLeft: S.base, marginBottom: 6 },
  railRow: { paddingHorizontal: S.base, gap: S.sm },
  card: { width: 124, marginRight: S.sm },
  cardTitle: { color: C.text, ...theme.typography.caption, fontWeight: '700', marginTop: 5 },
  cardSub: { color: C.textDim, ...theme.typography.micro, marginTop: 1 },
  boardBtn: { marginHorizontal: S.base, marginTop: S.sm, padding: S.md, borderRadius: R.xl, alignItems: 'center', borderWidth: 1, borderColor: C.accentGold, backgroundColor: 'rgba(251,191,36,0.10)' },
  boardBtnTxt: { color: C.accentGold, ...theme.typography.body, fontWeight: '800' },
});
