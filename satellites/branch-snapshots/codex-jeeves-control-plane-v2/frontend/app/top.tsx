/**
 * /top — Public, shareable Top Games leaderboard (Creator Marketplace).
 *
 * Deluxe redesign: the top 3 get elevated gold/silver/bronze "podium" cards;
 * ranks 4+ are clean, scannable rows. Tapping a row deep-links into
 * /playable?id=<pid> to play; the "Remix" action opens it pre-focused on the
 * evolve box (/playable?id=<pid>&remix=1) — the marketplace remix flow.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, Platform, RefreshControl, Image, TextInput,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import theme from '../theme/tokens';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { colors: C, spacing: S, radii: R } = { colors: theme.colors, spacing: theme.spacing, radii: theme.radii };

const PODIUM = [
  { medal: '🥇', ring: '#fbbf24', glow: 'rgba(251,191,36,0.45)', tint: 'rgba(251,191,36,0.10)' },
  { medal: '🥈', ring: '#cbd5e1', glow: 'rgba(203,213,225,0.35)', tint: 'rgba(203,213,225,0.08)' },
  { medal: '🥉', ring: '#d97706', glow: 'rgba(217,119,6,0.40)', tint: 'rgba(217,119,6,0.10)' },
];

interface BoardRow {
  rank: number; playable_id: string; title: string; genre: string;
  derive_mode?: string; imported?: boolean; has_cover?: boolean;
  intricacy?: number; overall?: number; wins: number; matches: number; score: number;
  plays?: number; difficulty?: string; length?: string; velocity?: number; plays_window?: number;
  remix_count?: number; staff_pick?: boolean; champion_weeks?: number;
}
interface StaffPick {
  playable_id: string; title: string; genre: string; overall?: number;
  difficulty?: string; length?: string; plays?: number; remix_count?: number; has_cover?: boolean;
  reactions_total?: number;
}

function hashHue(s: string) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; }

/** Time remaining until the weekly board resets (next Monday 00:00 UTC). */
function weeklyResetIn(): string {
  const now = new Date();
  const mon = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const dow = (mon.getUTCDay() + 6) % 7;           // 0 = Monday
  mon.setUTCDate(mon.getUTCDate() - dow + 7);       // next Monday 00:00 UTC
  const ms = mon.getTime() - now.getTime();
  const d = Math.floor(ms / 86_400_000);
  const h = Math.floor((ms % 86_400_000) / 3_600_000);
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}

/** Game cover thumbnail — Nano-Banana art when available, else a tinted glyph placeholder. */
function Cover({ row, size }: { row: BoardRow; size: number }) {
  const [err, setErr] = React.useState(false);
  if (row.has_cover && !err) {
    return (
      <Image
        source={{ uri: `${BACKEND}/api/playable/${row.playable_id}/cover.png` }}
        style={{ width: size, height: size, borderRadius: R.md, backgroundColor: '#141414' }}
        onError={() => setErr(true)}
      />
    );
  }
  const hue = hashHue(row.title || row.playable_id);
  return (
    <View style={{ width: size, height: size, borderRadius: R.md, alignItems: 'center', justifyContent: 'center', backgroundColor: `hsl(${hue},45%,18%)` }}>
      <Text style={{ fontSize: size * 0.42 }}>🎮</Text>
    </View>
  );
}

export default function TopScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [rows, setRows] = React.useState<BoardRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [period, setPeriod] = React.useState<'all' | 'week' | 'trending'>('all');
  const [genre, setGenre] = React.useState<string | null>(null);
  const [daily, setDaily] = React.useState<{ theme: string; prompt: string; count: number } | null>(null);
  const [staffPicks, setStaffPicks] = React.useState<StaffPick[]>([]);
  const [mostLoved, setMostLoved] = React.useState<StaffPick[]>([]);
  const [spotlight, setSpotlight] = React.useState<StaffPick | null>(null);
  const [query, setQuery] = React.useState('');
  const [sort, setSort] = React.useState<'score' | 'plays' | 'newest' | 'remixed'>('score');
  const [illus, setIllus] = React.useState<{ active: boolean; done: number; total: number }>({ active: false, done: 0, total: 0 });

  const load = React.useCallback(async () => {
    if (period === 'trending') {
      const r = await api.get<{ trending: BoardRow[] }>('/api/playable/trending?limit=50&hours=24', { timeoutMs: 15_000 });
      if (r.ok && r.data) setRows((r.data.trending || []).map((t: any) => ({ ...t, score: t.velocity ?? 0, wins: 0, matches: 0 })));
    } else {
      const qs = `limit=50&period=${period}&sort=${sort}${query.trim() ? `&q=${encodeURIComponent(query.trim())}` : ''}`;
      const r = await api.get<{ leaderboard: BoardRow[] }>(`/api/playable/leaderboard?${qs}`, { timeoutMs: 15_000 });
      if (r.ok && r.data) setRows(r.data.leaderboard || []);
    }
    setLoading(false); setRefreshing(false);
  }, [period, sort, query]);

  const loadDaily = React.useCallback(async () => {
    const r = await api.get<{ theme: string; prompt: string; count: number }>('/api/playable/daily', { timeoutMs: 12_000 });
    if (r.ok && r.data) setDaily({ theme: r.data.theme, prompt: r.data.prompt, count: r.data.count });
  }, []);

  const loadStaffPicks = React.useCallback(async () => {
    const r = await api.get<{ staff_picks: StaffPick[] }>('/api/playable/staff-picks?limit=12', { timeoutMs: 12_000 });
    if (r.ok && r.data) setStaffPicks(r.data.staff_picks || []);
  }, []);

  const loadMostLoved = React.useCallback(async () => {
    const r = await api.get<{ most_loved: StaffPick[] }>('/api/playable/most-loved?limit=12', { timeoutMs: 12_000 });
    if (r.ok && r.data) setMostLoved(r.data.most_loved || []);
  }, []);

  const loadSpotlight = React.useCallback(async () => {
    const r = await api.get<{ spotlight: StaffPick | null }>('/api/playable/spotlight', { timeoutMs: 12_000 });
    if (r.ok && r.data) setSpotlight(r.data.spotlight);
  }, []);

  React.useEffect(() => { load(); }, [load]);
  React.useEffect(() => { loadDaily(); loadStaffPicks(); loadSpotlight(); loadMostLoved(); }, [loadDaily, loadStaffPicks, loadSpotlight, loadMostLoved]);
  const onRefresh = React.useCallback(() => { setRefreshing(true); load(); }, [load]);

  const play = React.useCallback((id: string) => { haptics.selection(); router.push(`/playable?id=${id}`); }, [haptics, router]);
  const remix = React.useCallback((id: string) => { haptics.selection(); router.push(`/playable?id=${id}&remix=1`); }, [haptics, router]);

  const shareBoard = React.useCallback(async () => {
    haptics.selection();
    const url = Platform.OS === 'web'
      ? (typeof window !== 'undefined' ? window.location.origin + '/top' : `${BACKEND}/top`)
      : 'codedock://top';
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any).clipboard) {
        await (navigator as any).clipboard.writeText(url);
      } else { await Clipboard.setStringAsync(url); }
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    } catch { /* noop */ }
  }, [haptics]);

  // 🎲 Surprise — open a random ranked game (discovery).
  const surprise = React.useCallback(() => {
    if (!rows.length) return;
    haptics.selection();
    const g = rows[Math.floor(Math.random() * rows.length)];
    router.push(`/playable?id=${g.playable_id}`);
  }, [rows, haptics, router]);

  // 🎨 Illustrate board — batch-mint covers for the top games missing them
  // (bounded to 10 to cap cost/time; sequential to avoid hammering the model).
  const illustrateBoard = React.useCallback(async () => {
    if (illus.active) return;
    const missing = rows.filter((r) => !r.has_cover).slice(0, 10);
    if (!missing.length) return;
    haptics.selection();
    setIllus({ active: true, done: 0, total: missing.length });
    for (let i = 0; i < missing.length; i++) {
      await api.post(`/api/playable/${missing[i].playable_id}/cover`, {}, { timeoutMs: 75_000, retries: 0 });
      setIllus({ active: true, done: i + 1, total: missing.length });
    }
    setIllus({ active: false, done: 0, total: 0 });
    haptics.notify('success');
    load();
  }, [rows, illus.active, haptics, load]);

  const missingCount = rows.filter((r) => !r.has_cover).length;

  const genres = React.useMemo(() => Array.from(new Set(rows.map((r) => r.genre).filter(Boolean))).slice(0, 8) as string[], [rows]);
  const champion = period === 'week' && rows.length ? rows[0] : null;
  const filtered = genre ? rows.filter((r) => r.genre === genre) : rows;
  const podium = filtered.slice(0, 3);
  const rest = filtered.slice(3);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="top-back" hitSlop={theme.hitSlop.md} onPress={() => { try { { if (router.canGoBack()) router.back(); else router.replace('/playable'); } } catch { router.replace('/playable'); } }} style={styles.headerBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>🏆 Top Games</Text>
        <TouchableOpacity testID="top-discover" hitSlop={theme.hitSlop.md} onPress={() => { haptics.selection(); router.push('/discover'); }} style={[styles.headerBtn, { alignItems: 'flex-end' }]}>
          <Text style={styles.shareTxt}>✨ Discover</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.subtitle}>Public board — ranked by votes, judge score & intricacy. Tap to play, or remix a hit.</Text>

      <View style={styles.tabs}>
        <TouchableOpacity testID="top-tab-all" style={[styles.tab, period === 'all' && styles.tabOn]} onPress={() => { haptics.selection(); setLoading(true); setPeriod('all'); }}>
          <Text style={[styles.tabTxt, period === 'all' && styles.tabTxtOn]}>🏆 All-Time</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="top-tab-week" style={[styles.tab, period === 'week' && styles.tabOn]} onPress={() => { haptics.selection(); setLoading(true); setPeriod('week'); }}>
          <Text style={[styles.tabTxt, period === 'week' && styles.tabTxtOn]}>🔥 This Week</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="top-tab-trending" style={[styles.tab, period === 'trending' && styles.tabOn]} onPress={() => { haptics.selection(); setLoading(true); setPeriod('trending'); }}>
          <Text style={[styles.tabTxt, period === 'trending' && styles.tabTxtOn]}>📈 Trending</Text>
        </TouchableOpacity>
      </View>

      {daily ? (
        <TouchableOpacity testID="top-daily" activeOpacity={0.9} style={styles.daily} onPress={() => { haptics.selection(); router.push(`/playable?brief=${encodeURIComponent(daily.prompt)}`); }}>
          <Text style={styles.dailyLabel}>📅 DAILY CHALLENGE · {daily.count} {daily.count === 1 ? 'entry' : 'entries'}</Text>
          <Text style={styles.dailyTheme} numberOfLines={2}>Build {daily.theme}</Text>
          <Text style={styles.dailyCta}>⚡ Tap to build today&apos;s challenge →</Text>
        </TouchableOpacity>
      ) : null}

      {spotlight ? (
        <TouchableOpacity testID="top-spotlight" activeOpacity={0.9} style={styles.spotlight} onPress={() => play(spotlight.playable_id)}>
          <View style={styles.spotCoverWrap}>
            <Cover row={spotlight as any} size={72} />
            <Text style={styles.spotStar}>🌟</Text>
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.spotLabel}>🌟 SPOTLIGHT · featured today</Text>
            <Text style={styles.spotTitle} numberOfLines={1}>{spotlight.title}</Text>
            <Text style={styles.spotMeta} numberOfLines={1}>{spotlight.genre} · ⭐{spotlight.overall ?? '–'} · ▶{spotlight.plays ?? 0}{spotlight.difficulty ? ` · 🎯${spotlight.difficulty}` : ''}</Text>
          </View>
          <Text style={styles.spotPlay}>▶</Text>
        </TouchableOpacity>
      ) : null}

      {champion ? (
        <TouchableOpacity testID="top-champion" activeOpacity={0.9} style={styles.champ} onPress={() => play(champion.playable_id)}>
          <View style={styles.champCoverWrap}>
            <Cover row={champion} size={66} />
            <Text style={styles.crown}>👑</Text>
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.champLabel}>👑 CHAMPION OF THE WEEK · resets in {weeklyResetIn()}</Text>
            <Text style={styles.champTitle} numberOfLines={1}>{champion.title}</Text>
            <Text style={styles.champMeta}>⭐ {champion.overall ?? '–'} · score {champion.score} · ⚔️ {champion.wins}/{champion.matches}</Text>
          </View>
        </TouchableOpacity>
      ) : null}

      {period === 'all' && staffPicks.length ? (
        <View testID="top-staff-picks">
          <Text style={styles.railLabel}>⭐ STAFF PICKS</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.railRow}>
            {staffPicks.map((g) => (
              <TouchableOpacity key={g.playable_id} testID={`top-staff-${g.playable_id}`} style={styles.railCard} activeOpacity={0.85} onPress={() => play(g.playable_id)}>
                <Cover row={g as any} size={120} />
                <Text style={styles.railTitle} numberOfLines={1}>{g.title}</Text>
                <Text style={styles.railSub} numberOfLines={1}>⭐{g.overall ?? '–'} · ▶{g.plays ?? 0}{g.remix_count ? ` · 🔱${g.remix_count}` : ''}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {period === 'all' && mostLoved.length ? (
        <View testID="top-most-loved">
          <Text style={styles.railLabel}>❤️ MOST LOVED</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.railRow}>
            {mostLoved.map((g) => (
              <TouchableOpacity key={g.playable_id} testID={`top-loved-${g.playable_id}`} style={styles.railCard} activeOpacity={0.85} onPress={() => play(g.playable_id)}>
                <Cover row={g as any} size={120} />
                <Text style={styles.railTitle} numberOfLines={1}>{g.title}</Text>
                <Text style={styles.railSub} numberOfLines={1}>❤️{g.reactions_total ?? 0} · ⭐{g.overall ?? '–'} · ▶{g.plays ?? 0}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {genres.length ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.genreRow}>
          <TouchableOpacity testID="top-genre-all" style={[styles.genreChip, !genre && styles.genreChipOn]} onPress={() => { haptics.selection(); setGenre(null); }}>
            <Text style={[styles.genreTxt, !genre && styles.genreTxtOn]}>All</Text>
          </TouchableOpacity>
          {genres.map((g) => (
            <TouchableOpacity key={g} testID={`top-genre-${g}`} style={[styles.genreChip, genre === g && styles.genreChipOn]} onPress={() => { haptics.selection(); setGenre(genre === g ? null : g); }}>
              <Text style={[styles.genreTxt, genre === g && styles.genreTxtOn]} numberOfLines={1}>{g}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      ) : null}

      {period !== 'trending' ? (
        <View testID="top-search-sort">
          <TextInput
            testID="top-search"
            style={styles.search}
            placeholder="🔍 Search games by title or genre…"
            placeholderTextColor={C.textDim}
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => { setLoading(true); load(); }}
            returnKeyType="search"
          />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.sortRow}>
            {([['score', '🏆 Top'], ['plays', '▶ Most played'], ['newest', '🆕 Newest'], ['remixed', '🔱 Most remixed']] as const).map(([key, label]) => (
              <TouchableOpacity key={key} testID={`top-sort-${key}`} style={[styles.sortChip, sort === key && styles.sortChipOn]} onPress={() => { haptics.selection(); setLoading(true); setSort(key); }}>
                <Text style={[styles.sortTxt, sort === key && styles.sortTxtOn]}>{label}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {!loading && rows.length ? (
        <View style={styles.actionBar}>
          <TouchableOpacity testID="top-surprise" style={[styles.barBtn, styles.surpriseBtn]} onPress={surprise}>
            <Text style={styles.barBtnTxt}>🎲 Surprise</Text>
          </TouchableOpacity>
          <TouchableOpacity
            testID="top-illustrate"
            style={[styles.barBtn, styles.illusBtn, (illus.active || missingCount === 0) && { opacity: 0.5 }]}
            disabled={illus.active || missingCount === 0}
            onPress={illustrateBoard}
          >
            <Text style={styles.barBtnTxt}>
              {illus.active ? `🎨 Illustrating ${illus.done}/${illus.total}…` : missingCount ? `🎨 Illustrate (${Math.min(missingCount, 10)})` : '🎨 All illustrated ✓'}
            </Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={C.accentGold} size="large" /></View>
      ) : (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={{ paddingBottom: 48, paddingHorizontal: S.base }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.accentGold} />}
        >
          {rows.length === 0 ? (
            <Text testID="top-empty" style={styles.empty}>No ranked games yet.{'\n'}Generate one in Playable Export!</Text>
          ) : (
            <>
              {/* ── Podium: top 3 elevated cards ── */}
              {podium.map((g, i) => {
                const p = PODIUM[i];
                return (
                  <TouchableOpacity
                    key={g.playable_id}
                    testID={`top-row-${g.playable_id}`}
                    activeOpacity={0.85}
                    style={[styles.podiumCard, { borderColor: p.ring, backgroundColor: p.tint, boxShadow: `0px 0px 16px ${p.glow}` }]}
                    onPress={() => play(g.playable_id)}
                  >
                    <View style={styles.coverWrap}>
                      <Cover row={g} size={58} />
                      <View style={[styles.medalBadge, { borderColor: p.ring }]}><Text style={styles.medalBadgeTxt}>{p.medal}</Text></View>
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={[styles.podiumTitle, { color: p.ring }]} numberOfLines={1}>{g.title}{g.imported ? ' 📦' : ''}</Text>
                      <Text style={styles.rowSub} numberOfLines={1}>
                        {g.genre}{g.derive_mode ? ` · ${g.derive_mode}` : ''} · ⭐{g.overall ?? '–'} · ▶{g.plays ?? 0}{g.difficulty ? ` · 🎯${g.difficulty}` : ''}{g.length ? ` · ⏱️${g.length}` : ''}{g.remix_count ? ` · 🔱${g.remix_count}` : ''}{g.champion_weeks ? ` · 🏆${g.champion_weeks}` : ''}
                      </Text>
                      <View style={styles.podiumActions}>
                        <View style={[styles.scorePill, { borderColor: p.ring }]}><Text style={[styles.scoreTxt, { color: p.ring }]}>{g.score}</Text></View>
                        <TouchableOpacity testID={`top-remix-${g.playable_id}`} style={styles.remixBtn} onPress={() => remix(g.playable_id)}>
                          <Text style={styles.remixTxt}>🔱 Remix</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  </TouchableOpacity>
                );
              })}

              {rest.length ? <Text style={styles.sectionLabel}>RANKS 4–{rows.length}</Text> : null}

              {/* ── Clean rows for ranks 4+ ── */}
              {rest.map((g) => (
                <View key={g.playable_id} style={styles.row}>
                  <TouchableOpacity testID={`top-row-${g.playable_id}`} style={styles.rowMain} activeOpacity={0.8} onPress={() => play(g.playable_id)}>
                    <Text style={styles.rank}>#{g.rank}</Text>
                    <Cover row={g} size={42} />
                    <View style={{ flex: 1, minWidth: 0, marginLeft: S.md }}>
                      <Text style={styles.rowTitle} numberOfLines={1}>{g.title}{g.imported ? ' 📦' : ''}</Text>
                      <Text style={styles.rowSub} numberOfLines={1}>
                        {g.genre}{g.derive_mode ? ` · ${g.derive_mode}` : ''} · ⭐{g.overall ?? '–'} · ▶{g.plays ?? 0}{g.difficulty ? ` · 🎯${g.difficulty}` : ''}{g.length ? ` · ⏱️${g.length}` : ''}{g.remix_count ? ` · 🔱${g.remix_count}` : ''}{g.champion_weeks ? ` · 🏆${g.champion_weeks}` : ''}
                      </Text>
                    </View>
                    <View style={styles.scorePillSm}><Text style={styles.scoreTxtSm}>{g.score}</Text></View>
                  </TouchableOpacity>
                  <TouchableOpacity testID={`top-remix-${g.playable_id}`} style={styles.remixBtnSm} onPress={() => remix(g.playable_id)} hitSlop={theme.hitSlop.sm}>
                    <Text style={styles.remixTxtSm}>🔱</Text>
                  </TouchableOpacity>
                </View>
              ))}

              <View style={styles.footerLinks}>
                <TouchableOpacity testID="top-hall-link" style={styles.healthLink} onPress={() => { haptics.selection(); router.push('/champions'); }}>
                  <Text style={styles.hallTxt}>🏛️ Hall of Champions</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="top-collections-link" style={styles.healthLink} onPress={() => { haptics.selection(); router.push('/collections'); }}>
                  <Text style={styles.hallTxt}>📚 Collections</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="top-share" style={styles.healthLink} onPress={shareBoard}>
                  <Text style={styles.hallTxt}>{copied ? '✓ Copied' : '🔗 Share board'}</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="top-health-link" style={styles.healthLink} onPress={() => { haptics.selection(); router.push('/health'); }}>
                  <Text style={styles.healthTxt}>⚙ System health</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
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
  headerBtn: { width: 88, paddingVertical: 6 },
  backTxt: { color: C.accentGold, ...theme.typography.h4 },
  title: { color: C.text, ...theme.typography.h3 },
  shareTxt: { color: C.accentGold, ...theme.typography.button, textAlign: 'right' },
  subtitle: { color: C.textMuted, ...theme.typography.body, paddingHorizontal: S.base, marginTop: S.md, marginBottom: S.sm },
  actionBar: { flexDirection: 'row', gap: S.sm, paddingHorizontal: S.base, marginBottom: S.sm },
  tabs: { flexDirection: 'row', gap: S.sm, paddingHorizontal: S.base, marginBottom: S.sm },
  tab: { flex: 1, paddingVertical: 9, borderRadius: R.md, alignItems: 'center', borderWidth: 1, borderColor: C.border, backgroundColor: C.surface },
  tabOn: { backgroundColor: 'rgba(251,191,36,0.14)', borderColor: C.accentGold },
  tabTxt: { color: C.textMuted, ...theme.typography.buttonSm },
  tabTxtOn: { color: C.accentGold },
  champ: { flexDirection: 'row', alignItems: 'center', gap: S.md, marginHorizontal: S.base, marginBottom: S.sm, padding: S.md, borderRadius: R.xl, borderWidth: 1.5, borderColor: C.accentGold, backgroundColor: 'rgba(251,191,36,0.10)' },
  daily: { marginHorizontal: S.base, marginBottom: S.sm, padding: S.md, borderRadius: R.xl, borderWidth: 1.5, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.10)' },
  dailyLabel: { color: '#4ade80', ...theme.typography.micro, fontWeight: '800', marginBottom: 3 },
  dailyTheme: { color: C.text, ...theme.typography.h4, fontWeight: '800' },
  dailyCta: { color: '#86efac', ...theme.typography.caption, marginTop: 4, fontWeight: '700' },
  railLabel: { color: '#fbbf24', ...theme.typography.micro, fontWeight: '800', marginLeft: S.base, marginBottom: 6 },
  railRow: { paddingHorizontal: S.base, gap: S.sm },
  railCard: { width: 120, marginRight: S.sm },
  railTitle: { color: C.text, ...theme.typography.caption, fontWeight: '700', marginTop: 5 },
  railSub: { color: C.textDim, ...theme.typography.micro, marginTop: 1 },
  spotlight: { flexDirection: 'row', alignItems: 'center', gap: S.md, marginHorizontal: S.base, marginBottom: S.sm, padding: S.md, borderRadius: R.xl, borderWidth: 1.5, borderColor: '#8B5CF6', backgroundColor: 'rgba(168,85,247,0.12)' },
  spotCoverWrap: { position: 'relative' },
  spotStar: { position: 'absolute', top: -8, left: -8, fontSize: 22 },
  spotLabel: { color: '#d8b4fe', ...theme.typography.micro, fontWeight: '800', marginBottom: 2 },
  spotTitle: { color: C.text, ...theme.typography.h4, fontWeight: '800' },
  spotMeta: { color: C.textDim, ...theme.typography.caption, marginTop: 2 },
  spotPlay: { color: '#d8b4fe', fontSize: 22, fontWeight: '800' },
  search: { marginHorizontal: S.base, marginBottom: S.sm, backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, color: C.text, paddingHorizontal: S.md, paddingVertical: 10, ...theme.typography.body },
  sortRow: { paddingHorizontal: S.base, gap: S.sm, paddingBottom: S.sm },
  sortChip: { paddingHorizontal: S.md, paddingVertical: 7, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface, marginRight: 6 },
  sortChipOn: { borderColor: C.accentGold, backgroundColor: 'rgba(251,191,36,0.14)' },
  sortTxt: { color: C.textDim, ...theme.typography.caption, fontWeight: '700' },
  sortTxtOn: { color: C.accentGold },
  champCoverWrap: { width: 66, height: 66, position: 'relative' },
  crown: { position: 'absolute', top: -12, left: -6, fontSize: 22, transform: [{ rotate: '-18deg' }] },
  champLabel: { color: C.accentGold, ...theme.typography.micro, fontWeight: '800', marginBottom: 2 },
  champTitle: { color: C.text, ...theme.typography.h4, fontWeight: '800' },
  champMeta: { color: C.textMuted, ...theme.typography.caption, marginTop: 2 },
  genreRow: { flexDirection: 'row', gap: S.sm, paddingHorizontal: S.base, paddingBottom: S.sm },
  genreChip: { paddingHorizontal: S.md, paddingVertical: 6, borderRadius: R.full, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface, maxWidth: 130 },
  genreChipOn: { backgroundColor: C.primarySoft, borderColor: C.primary },
  genreTxt: { color: C.textMuted, ...theme.typography.caption, fontWeight: '700' },
  genreTxtOn: { color: C.primaryHover },
  barBtn: { flex: 1, borderRadius: R.md, paddingVertical: 10, alignItems: 'center', borderWidth: 1 },
  surpriseBtn: { backgroundColor: C.surface, borderColor: C.border },
  illusBtn: { backgroundColor: 'rgba(126,34,206,0.15)', borderColor: '#7e22ce' },
  barBtnTxt: { color: C.text, ...theme.typography.buttonSm },
  scroll: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { color: C.textDim, ...theme.typography.bodyLg, textAlign: 'center', marginTop: 60, lineHeight: 24 },

  // Podium cards
  podiumCard: {
    flexDirection: 'row', alignItems: 'center', borderRadius: R.xl, padding: S.base, marginTop: S.md,
    borderWidth: 1.5, gap: S.md,
    ...Platform.select({ ios: { shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.5, shadowRadius: 16 }, android: { elevation: 6 }, default: {} }),
  },
  coverWrap: { width: 58, height: 58, position: 'relative' },
  medalBadge: { position: 'absolute', bottom: -4, right: -4, borderRadius: R.full, backgroundColor: '#0A0A0A', borderWidth: 1.5, paddingHorizontal: 3, paddingVertical: 1 },
  medalBadgeTxt: { fontSize: 15 },
  podiumTitle: { ...theme.typography.h4, fontWeight: '800' },
  podiumActions: { flexDirection: 'row', alignItems: 'center', gap: S.sm, marginTop: S.sm },
  scorePill: { borderWidth: 1.5, borderRadius: R.md, paddingHorizontal: S.md, paddingVertical: 5 },
  scoreTxt: { ...theme.typography.h4, fontWeight: '900' },

  sectionLabel: { color: C.textDim, ...theme.typography.micro, marginTop: S.xl, marginBottom: S.xs, marginLeft: S.xs },

  // Standard rows
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: R.lg, marginTop: S.sm, borderWidth: 1, borderColor: C.border },
  rowMain: { flex: 1, flexDirection: 'row', alignItems: 'center', padding: S.md },
  rank: { color: C.textMuted, ...theme.typography.h4, fontWeight: '900', width: 40 },
  rowTitle: { color: C.text, ...theme.typography.body, fontWeight: '700' },
  rowSub: { color: C.textMuted, ...theme.typography.caption, marginTop: 3, fontWeight: '500' },
  scorePillSm: { backgroundColor: C.bgElevated, borderRadius: R.sm, paddingHorizontal: S.sm, paddingVertical: 4, marginLeft: S.sm },
  scoreTxtSm: { color: C.accentGold, ...theme.typography.h4, fontWeight: '900' },

  remixBtn: { backgroundColor: C.primarySoft, borderRadius: R.md, paddingHorizontal: S.md, paddingVertical: 6, borderWidth: 1, borderColor: C.primary },
  remixTxt: { color: C.primaryHover, ...theme.typography.buttonSm },
  remixBtnSm: { paddingHorizontal: S.md, paddingVertical: S.md, alignSelf: 'stretch', justifyContent: 'center', borderLeftWidth: 1, borderLeftColor: C.border },
  remixTxtSm: { fontSize: 18 },

  healthLink: { alignSelf: 'center', marginTop: S.xl, padding: S.md },
  footerLinks: { flexDirection: 'row', justifyContent: 'center', gap: S.xl, marginTop: S.md },
  hallTxt: { color: C.accentGold, ...theme.typography.caption, fontWeight: '700' },
  healthTxt: { color: C.textDim, ...theme.typography.caption },
});
