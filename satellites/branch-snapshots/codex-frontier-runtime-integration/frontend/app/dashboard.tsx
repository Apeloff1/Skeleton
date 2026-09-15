/**
 * Dashboard — home tab summarising the user's life across the app.
 * Shows: greeting + streak fire, daily progress rings (reading / focus / class),
 * recent achievements, today's scheduler events, continue-reading, recent builds.
 */
import { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LinearGradient } from 'expo-linear-gradient';
import { useUser, ACHIEVEMENT_CATALOG } from '../utils/userStore';
import { api } from '../utils/apiController';
import { openModalFromRoute } from '../utils/openModalFromRoute';
import { jeevesSpeak } from '../features/Academy/jeevesTts';
import { Screen, AppHeader } from '../components/ui';
import Skeleton from '../components/ui/Skeleton';
import RetryBanner from '../components/ui/RetryBanner';

const greetings = ['Welcome back', 'Good to see you', 'Ready to learn', 'Let’s keep going'];

export default function Dashboard() {
  const router = useRouter();
  const user = useUser();
  const [todayEvents, setTodayEvents] = useState<any[]>([]);
  const [continueReading, setContinueReading] = useState<any[]>([]);
  const [recentBuilds, setRecentBuilds] = useState<any[]>([]);
  /** Per-fetch loading + error so dashboard cards can self-skeleton / self-retry. */
  const [readingState, setReadingState] = useState<'idle' | 'loading' | 'error' | 'ok'>('loading');
  const [buildsState, setBuildsState] = useState<'idle' | 'loading' | 'error' | 'ok'>('loading');

  // Load scheduler events for today
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem('@codedock:scheduler:events');
        if (!raw) return;
        const all = JSON.parse(raw);
        const td = new Date();
        const tk = `${td.getFullYear()}-${String(td.getMonth() + 1).padStart(2, '0')}-${String(td.getDate()).padStart(2, '0')}`;
        setTodayEvents(all.filter((e: any) => e.date === tk).slice(0, 5));
      } catch {}
    })();
  }, []);

  // Continue reading from server — with skeleton + retry banner support.
  const loadContinue = useCallback(() => {
    setReadingState('loading');
    api.get<any>('/api/academy/class-progress/default_user/continue', { tag: 'dashboard.continue', cacheTtlMs: 60_000 })
      .then(d => { if (d?.items) setContinueReading(d.items.slice(0, 5)); setReadingState('ok'); })
      .catch(() => setReadingState('error'));
  }, []);
  useEffect(() => { loadContinue(); }, [loadContinue]);

  // Recent galaxy builds — use the canonical `/my-builds` endpoint.
  const loadBuilds = useCallback(() => {
    setBuildsState('loading');
    api.get<any>('/api/galaxy-studio/my-builds', { params: { limit: 5 }, tag: 'dashboard.builds', cacheTtlMs: 30_000 })
      .then(d => { if (d?.builds) setRecentBuilds(d.builds.slice(0, 5)); setBuildsState('ok'); })
      .catch(() => setBuildsState('error'));
  }, []);
  useEffect(() => { loadBuilds(); }, [loadBuilds]);

  const greeting = greetings[Math.floor(Math.random() * greetings.length)];
  const xp = user.stats.total_xp;
  const level = Math.floor(Math.sqrt(xp / 100)) + 1;
  const xpToNext = (level * level) * 100;
  const xpInLevel = xp - ((level - 1) * (level - 1) * 100);
  const xpProgress = xpToNext > 0 ? xpInLevel / (xpToNext - ((level - 1) * (level - 1) * 100)) : 0;

  const recentAchievements = user.unlocked_achievements
    .slice(-3)
    .map(id => ACHIEVEMENT_CATALOG.find(a => a.id === id))
    .filter(Boolean);

  // Today progress (use today vs last activity)

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#F5C45122', '#8B5CF622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[{ position: 'absolute', top: 0, left: 0, right: 0, height: 280 }, { pointerEvents: 'none' }]}
      />
      <AppHeader
        title="Dashboard"
        subtitle={`Level ${level} · ${xp.toLocaleString()} XP`}
        onBack={() => router.back()}
        right={
          <TouchableOpacity onPress={() => router.push('/profile' as any)} style={s.hdrBtn}>
            <View style={[s.avatar, { backgroundColor: user.profile.avatar_color }]}>
              <Text style={s.avatarText}>{user.profile.name.charAt(0).toUpperCase()}</Text>
            </View>
          </TouchableOpacity>
        }
      />

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80 }}>
        {/* Hero */}
        <View style={s.hero}>
          <Text style={s.greeting}>{greeting}, {user.profile.name}.</Text>
          <Text style={s.tagline}>
            {user.stats.streak_current > 0
              ? `🔥 ${user.stats.streak_current}-day streak. Don't break it.`
              : 'Today is a great day to start a streak.'}
          </Text>
          <View style={s.levelBar}>
            <View style={[s.levelFill, { width: `${Math.min(100, xpProgress * 100)}%` }]} />
          </View>
          <View style={s.levelRow}>
            <Text style={s.levelText}>Level {level}  ·  {xp.toLocaleString()} XP</Text>
            <Text style={s.levelTextDim}>{Math.max(0, xpToNext - xp)} XP to next</Text>
          </View>
        </View>

        {/* Stats grid */}
        <View style={s.statGrid}>
          <StatCard icon="book" color="#3B82F6" label="Chapters" value={user.stats.reading_chapters_completed} />
          <StatCard icon="school" color="#10B981" label="Weeks done" value={user.stats.classes_weeks_completed} />
          <StatCard icon="planet" color="#8B5CF6" label="Builds" value={user.stats.galaxy_builds} />
          <StatCard icon="flame" color="#F97316" label="Best streak" value={user.stats.streak_best} />
          <StatCard icon="time" color="#8B5CF6" label="Focus mins" value={user.stats.pomodoro_focus_minutes} />
          <StatCard icon="ribbon" color="#F5C451" label="Achievements" value={user.unlocked_achievements.length} />
        </View>

        {/* Quick actions */}
        <Text style={s.sectionTitle}>Quick Actions</Text>
        <View style={s.quickGrid}>
          <QuickBtn icon="book" label="Read" color="#3B82F6" onPress={() => router.push('/readingLibrary' as any)} />
          <QuickBtn icon="time" label="Focus" color="#8B5CF6" onPress={() => router.push('/pomodoro' as any)} />
          <QuickBtn icon="calendar" label="Plan" color="#10B981" onPress={() => router.push('/scheduler' as any)} />
          <QuickBtn icon="planet" label="Build" color="#8B5CF6" onPress={() => router.push('/gallery' as any)} />
        </View>

        {/* Jeeves greeting — taps trigger persona TTS with appropriate
            mannerism. Long-press opens the full Jeeves modal. */}
        <TouchableOpacity
          style={s.jeevesGreet}
          onPress={async () => {
            try {
              const streakLine = user.stats.streak_current > 0
                ? `Streak: ${user.stats.streak_current} days.`
                : 'Ready to begin?';
              jeevesSpeak(
                `Today you have earned ${xp.toLocaleString()} XP at level ${level}. ${streakLine}`,
                { context: 'greeting', prependCatchphrase: true },
              );
            } catch {}
          }}
          onLongPress={() => openModalFromRoute(router, 'jeeves')}
          activeOpacity={0.85}
        >
          <View style={s.jeevesAvatar}>
            <Ionicons name="happy" size={20} color="#A78BFA" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.jeevesGreetTitle}>Tap to hear Jeeves</Text>
            <Text style={s.jeevesGreetSub}>Persona-flavoured greeting · long-press for full chat</Text>
          </View>
          <Ionicons name="volume-high" size={18} color="#A78BFA" />
        </TouchableOpacity>

        {/* Today's events */}
        {todayEvents.length > 0 && (
          <View style={s.card}>
            <View style={s.cardHead}>
              <Ionicons name="calendar" size={16} color="#10B981" />
              <Text style={s.cardTitle}>Today</Text>
              <TouchableOpacity onPress={() => router.push('/scheduler' as any)}>
                <Text style={s.cardLink}>View all</Text>
              </TouchableOpacity>
            </View>
            {todayEvents.map((e: any) => (
              <View key={e.id} style={s.eventRow}>
                <View style={[s.eventDot, { backgroundColor: e.color || '#3B82F6' }]} />
                <Text style={s.eventTitle}>{e.title}</Text>
                {e.time ? <Text style={s.eventTime}>{e.time}</Text> : null}
              </View>
            ))}
          </View>
        )}

        {/* Recent achievements */}
        {recentAchievements.length > 0 && (
          <View style={s.card}>
            <View style={s.cardHead}>
              <Ionicons name="trophy" size={16} color="#F5C451" />
              <Text style={s.cardTitle}>Recent Achievements</Text>
            </View>
            <View style={s.achGrid}>
              {recentAchievements.map((a: any) => (
                <View key={a.id} style={[s.achPill, { borderColor: a.color }]}>
                  <Ionicons name={a.icon as any} size={14} color={a.color} />
                  <Text style={[s.achPillText, { color: a.color }]}>{a.title}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Continue reading — skeleton during load, banner on error,
            silent when no rows are returned to keep the dashboard sparse. */}
        {readingState === 'loading' ? (
          <View style={s.card}>
            <View style={s.cardHead}>
              <Ionicons name="bookmark" size={16} color="#3B82F6" />
              <Text style={s.cardTitle}>Continue Reading</Text>
            </View>
            <Skeleton.Block rows={3} gap={10} lastWidth="40%" />
          </View>
        ) : readingState === 'error' ? (
          <RetryBanner
            error="Couldn't load your continue-reading shelf."
            onRetry={loadContinue}
          />
        ) : continueReading.length > 0 ? (
          <View style={s.card}>
            <View style={s.cardHead}>
              <Ionicons name="bookmark" size={16} color="#3B82F6" />
              <Text style={s.cardTitle}>Continue Reading</Text>
            </View>
            {continueReading.map((c: any, i: number) => (
              <View key={i} style={s.contRow}>
                <Text style={s.contTitle} numberOfLines={1}>{c.title || c.book_title || 'Untitled'}</Text>
                {c.last_position !== undefined && <Text style={s.contSub}>Chapter {c.last_position + 1}</Text>}
              </View>
            ))}
          </View>
        ) : null}

        {/* Recent builds — same skeleton / retry / silent pattern. */}
        {buildsState === 'loading' ? (
          <View style={s.card}>
            <View style={s.cardHead}>
              <Ionicons name="planet" size={16} color="#8B5CF6" />
              <Text style={s.cardTitle}>Recent Builds</Text>
            </View>
            <Skeleton.Block rows={3} gap={10} lastWidth="55%" />
          </View>
        ) : buildsState === 'error' ? (
          <RetryBanner
            error="Couldn't load your Galaxy Studio builds."
            onRetry={loadBuilds}
          />
        ) : recentBuilds.length > 0 ? (
          <View style={s.card}>
            <View style={s.cardHead}>
              <Ionicons name="planet" size={16} color="#8B5CF6" />
              <Text style={s.cardTitle}>Recent Builds</Text>
              <TouchableOpacity onPress={() => router.push('/gallery' as any)}>
                <Text style={s.cardLink}>View gallery</Text>
              </TouchableOpacity>
            </View>
            {recentBuilds.map((b: any) => (
              <View key={b.build_id} style={s.contRow}>
                <Text style={s.contTitle} numberOfLines={1}>{b.title || b.build_id}</Text>
                <Text style={s.contSub}>{b.genre || ''}  ·  {b.file_count || 0} files</Text>
              </View>
            ))}
          </View>
        ) : null}

        {/* Achievement progress */}
        <Text style={s.sectionTitle}>Achievement Progress</Text>
        <View style={s.card}>
          {ACHIEVEMENT_CATALOG.slice(0, 8).map(a => {
            const unlocked = user.unlocked_achievements.includes(a.id);
            const val = Number((user.stats as any)[a.metric] || 0);
            const pct = Math.min(100, (val / a.threshold) * 100);
            return (
              <View key={a.id} style={s.achRow}>
                <View style={[s.achIcon, { backgroundColor: a.color + (unlocked ? 'AA' : '22') }]}>
                  <Ionicons name={a.icon as any} size={16} color={unlocked ? '#fff' : a.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={s.achHead}>
                    <Text style={[s.achTitle, unlocked && { color: a.color }]}>{a.title}</Text>
                    <Text style={s.achVal}>{val}/{a.threshold}</Text>
                  </View>
                  <Text style={s.achDesc}>{a.description}</Text>
                  <View style={s.achBar}>
                    <View style={[s.achFill, { width: `${pct}%`, backgroundColor: a.color }]} />
                  </View>
                </View>
              </View>
            );
          })}
        </View>
      </ScrollView>
    </Screen>
  );
}

function StatCard({ icon, color, label, value }: any) {
  return (
    <View style={s.statCard}>
      <Ionicons name={icon} size={18} color={color} />
      <Text style={[s.statValue, { color }]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function QuickBtn({ icon, label, color, onPress }: any) {
  // ★ 2026-05 polish — unified border (semantic divider) so the 4 quick-
  // action cards line up cleanly. The accent color is still expressed
  // via the icon halo + glyph, no need to also tint the border.
  return (
    <TouchableOpacity style={s.quickBtn} onPress={onPress} activeOpacity={0.7}>
      <View style={[s.quickIcon, { backgroundColor: color + '22' }]}>
        <Ionicons name={icon} size={18} color={color} />
      </View>
      <Text style={s.quickLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#141414' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: '#262626', borderBottomWidth: 1, borderBottomColor: '#404040' },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: '#F8FAFC' },
  avatar: { width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center' },
  avatarText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  hero: { backgroundColor: '#262626', borderRadius: 14, padding: 18, marginBottom: 12, borderWidth: 1, borderColor: '#404040' },
  greeting: { color: '#F8FAFC', fontSize: 22, fontWeight: '800' },
  tagline: { color: '#94A3B8', fontSize: 13, marginTop: 6 },
  levelBar: { height: 8, backgroundColor: '#141414', borderRadius: 4, overflow: 'hidden', marginTop: 14 },
  levelFill: { height: '100%', backgroundColor: '#F5C451', borderRadius: 4 },
  levelRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  levelText: { color: '#F5C451', fontSize: 11, fontWeight: '700' },
  levelTextDim: { color: '#64748B', fontSize: 11 },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  statCard: { width: '31%', backgroundColor: '#262626', borderRadius: 10, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: '#404040' },
  statValue: { fontSize: 20, fontWeight: '800', marginTop: 4 },
  statLabel: { color: '#94A3B8', fontSize: 10, marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.3 },
  sectionTitle: { color: '#CBD5E1', fontSize: 13, fontWeight: '700', marginTop: 16, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  quickGrid: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  quickBtn: { flex: 1, backgroundColor: '#262626', borderRadius: 10, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: '#404040' },
  quickIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', marginBottom: 6 },
  quickLabel: { color: '#F8FAFC', fontSize: 11, fontWeight: '700' },
  card: { backgroundColor: '#262626', borderRadius: 10, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#404040' },
  cardHead: { flexDirection: 'row', alignItems: 'center', marginBottom: 10, gap: 6 },
  cardTitle: { color: '#F8FAFC', fontSize: 13, fontWeight: '700', flex: 1 },
  cardLink: { color: '#3B82F6', fontSize: 11, fontWeight: '700' },
  eventRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, gap: 8 },
  eventDot: { width: 8, height: 8, borderRadius: 4 },
  eventTitle: { color: '#CBD5E1', fontSize: 13, flex: 1 },
  eventTime: { color: '#94A3B8', fontSize: 11 },
  contRow: { paddingVertical: 6 },
  contTitle: { color: '#F8FAFC', fontSize: 13, fontWeight: '600' },
  contSub: { color: '#94A3B8', fontSize: 11, marginTop: 2 },
  achGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  achPill: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, gap: 4 },
  achPillText: { fontSize: 11, fontWeight: '700' },
  achRow: { flexDirection: 'row', paddingVertical: 8, gap: 10, alignItems: 'center' },
  achIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  achHead: { flexDirection: 'row', justifyContent: 'space-between' },
  achTitle: { color: '#F8FAFC', fontSize: 12, fontWeight: '700' },
  achVal: { color: '#94A3B8', fontSize: 10, fontWeight: '700' },
  achDesc: { color: '#94A3B8', fontSize: 10, marginTop: 1 },
  achBar: { height: 4, backgroundColor: '#141414', borderRadius: 2, overflow: 'hidden', marginTop: 4 },
  achFill: { height: '100%', borderRadius: 2 },
  jeevesGreet: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#A78BFA1A', borderColor: '#A78BFA55', borderWidth: 1, borderRadius: 12, padding: 12, gap: 12, marginBottom: 12 },
  jeevesAvatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#A78BFA22', justifyContent: 'center', alignItems: 'center' },
  jeevesGreetTitle: { color: '#F8FAFC', fontSize: 13, fontWeight: '700' },
  jeevesGreetSub: { color: '#94A3B8', fontSize: 11, marginTop: 2 },
});
