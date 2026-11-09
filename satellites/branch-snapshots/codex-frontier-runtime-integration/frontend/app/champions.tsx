/**
 * /champions — 🏛️ Hall of Champions.
 *
 * Each ISO week's #1 game, permanently celebrated with its cover art, crown and
 * final score. The current (in-progress) week is flagged "LIVE". Tap a champion
 * to play it. Backed by GET /api/playable/champions (lazy weekly snapshot).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, Platform, RefreshControl, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import theme from '../theme/tokens';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const C = theme.colors, S = theme.spacing, R = theme.radii;

interface Champion {
  week_start: string; playable_id: string; title: string; genre?: string;
  derive_mode?: string; overall?: number; score: number; wins: number;
  matches: number; has_cover?: boolean; is_current?: boolean;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function weekLabel(iso: string) {
  const [y, m, d] = iso.split('-').map(Number);
  if (!y) return iso;
  return `Week of ${MONTHS[(m || 1) - 1]} ${d}, ${y}`;
}

function ChampCover({ c, size }: { c: Champion; size: number }) {
  const [err, setErr] = React.useState(false);
  if (c.has_cover && !err) {
    return <Image source={{ uri: `${BACKEND}/api/playable/${c.playable_id}/cover.png` }} style={{ width: size, height: size, borderRadius: R.md, backgroundColor: '#141414' }} onError={() => setErr(true)} />;
  }
  return <View style={{ width: size, height: size, borderRadius: R.md, backgroundColor: '#16203a', alignItems: 'center', justifyContent: 'center' }}><Text style={{ fontSize: size * 0.42 }}>🎮</Text></View>;
}

export default function ChampionsScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [rows, setRows] = React.useState<Champion[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);

  const load = React.useCallback(async () => {
    const r = await api.get<{ champions: Champion[] }>('/api/playable/champions?limit=26', { timeoutMs: 15_000 });
    if (r.ok && r.data) setRows(r.data.champions || []);
    setLoading(false); setRefreshing(false);
  }, []);
  React.useEffect(() => { load(); }, [load]);
  const onRefresh = React.useCallback(() => { setRefreshing(true); load(); }, [load]);
  const play = React.useCallback((id: string) => { haptics.selection(); router.push(`/playable?id=${id}`); }, [haptics, router]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="champ-back" hitSlop={theme.hitSlop.md} onPress={() => { try { { if (router.canGoBack()) router.back(); else router.replace('/top'); } } catch { router.replace('/top'); } }} style={{ width: 70 }}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>🏛️ Hall of Champions</Text>
        <View style={{ width: 70 }} />
      </View>
      <Text style={styles.subtitle}>Every week&apos;s #1 game, immortalized. 👑</Text>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={C.accentGold} size="large" /></View>
      ) : (
        <ScrollView
          contentContainerStyle={{ paddingHorizontal: S.base, paddingBottom: 48 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.accentGold} />}
        >
          {rows.length === 0 ? (
            <Text testID="champ-empty" style={styles.empty}>No champions crowned yet.{'\n'}Be the first to top the weekly board!</Text>
          ) : rows.map((c) => (
            <TouchableOpacity key={c.week_start} testID={`champ-${c.week_start}`} activeOpacity={0.9} style={[styles.card, c.is_current && styles.cardLive]} onPress={() => play(c.playable_id)}>
              <View style={styles.coverWrap}>
                <ChampCover c={c} size={72} />
                <Text style={styles.crown}>👑</Text>
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={styles.weekRow}>
                  <Text style={styles.week}>{weekLabel(c.week_start)}</Text>
                  {c.is_current ? <View style={styles.liveBadge}><Text style={styles.liveTxt}>LIVE</Text></View> : null}
                </View>
                <Text style={styles.champTitle} numberOfLines={1}>{c.title}</Text>
                <Text style={styles.meta}>{c.genre || 'arcade'}{c.derive_mode ? ` · ${c.derive_mode}` : ''} · ⭐ {c.overall ?? '–'} · ⚔️ {c.wins}/{c.matches}</Text>
              </View>
              <View style={styles.scorePill}><Text style={styles.scoreTxt}>{c.score}</Text></View>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: S.base, paddingTop: Platform.OS === 'ios' ? S.sm : S.base, paddingBottom: S.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.border,
  },
  backTxt: { color: C.accentGold, ...theme.typography.h4 },
  title: { color: C.text, ...theme.typography.h3 },
  subtitle: { color: C.textMuted, ...theme.typography.body, paddingHorizontal: S.base, marginTop: S.md, marginBottom: S.sm },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { color: C.textDim, ...theme.typography.bodyLg, textAlign: 'center', marginTop: 60, lineHeight: 24 },
  card: {
    flexDirection: 'row', alignItems: 'center', gap: S.md, backgroundColor: '#1a160a',
    borderRadius: R.xl, padding: S.base, marginTop: S.md, borderWidth: 1.5, borderColor: '#854d0e',
  },
  cardLive: { borderColor: C.accentGold, backgroundColor: 'rgba(251,191,36,0.10)' },
  coverWrap: { width: 72, height: 72, position: 'relative' },
  crown: { position: 'absolute', top: -12, left: -6, fontSize: 24, transform: [{ rotate: '-18deg' }] },
  weekRow: { flexDirection: 'row', alignItems: 'center', gap: S.sm },
  week: { color: C.accentGold, ...theme.typography.micro, fontWeight: '800' },
  liveBadge: { backgroundColor: '#16a34a', borderRadius: R.sm, paddingHorizontal: 6, paddingVertical: 1 },
  liveTxt: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  champTitle: { color: C.text, ...theme.typography.h4, fontWeight: '800', marginTop: 3 },
  meta: { color: C.textMuted, ...theme.typography.caption, marginTop: 3 },
  scorePill: { backgroundColor: '#3a2e10', borderRadius: R.md, paddingHorizontal: S.md, paddingVertical: 7 },
  scoreTxt: { color: C.accentGold, ...theme.typography.h4, fontWeight: '900' },
});
