import React, { useState, useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useSettings } from '../../state/settingsStore';
import theme from '../../theme/tokens';
import { Screen, AppHeader, Button } from '../../components/ui';
import { actionSheet } from '../../components/ActionSheet';
import { toast } from '../../components/Toast';
import { getHapticsLevel, setHapticsLevel } from '../../utils/haptics';
import { getMenuPrefs, resetMenuPrefs } from '../../utils/menuPrefs';
import api from '../../src/utils/apiClient';
import * as Clipboard from 'expo-clipboard';

export default function SettingsHome() {
  const router = useRouter();
  const jeeves = useSettings(s => s.jeeves);
  const academy = useSettings(s => s.academy);
  const galaxy = useSettings(s => s.galaxyStudio);
  const coding = useSettings(s => s.coding);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const allSubmenus = [
    { key: 'jeeves', title: 'Jeeves', subtitle: 'Directives, blurbs, bulk orders, persona, creativity', icon: 'person-circle', color: '#8B5CF6', badge: jeeves.enforceOnEveryRequest ? 'ENFORCING' : 'Default', onPress: () => router.push('/settings/jeeves' as any) },
    { key: 'jeeves-voice', title: 'Jeeves Voice Lab', subtitle: 'Cinematic HD voice, 12 expressive tones, audition & immersion', icon: 'mic', color: '#c026d3', badge: academy.cinematicVoice !== false ? 'CINEMATIC' : 'OFF', onPress: () => router.push('/settings/jeeves-voice' as any) },
    { key: 'coding', title: 'Coding', subtitle: 'Metronome, bracket-pair colors, snippets, AI explain', icon: 'musical-notes', color: '#3B82F6', badge: coding.metronomeEnabled ? `♩ ${coding.metronomeBpm} BPM` : 'NEW', onPress: () => router.push('/settings/coding' as any) },
    { key: 'api', title: 'API Controller', subtitle: 'Live request stats, cache, retries, rate-limit health', icon: 'pulse', color: '#10B981', badge: 'SOTA', onPress: () => router.push('/settings/api' as any) },
    { key: 'academy', title: 'Academy', subtitle: 'Text-to-speech, reading ergonomics, audiobook mode', icon: 'school', color: '#8B5CF6', badge: academy.ttsEnabled ? 'TTS ON' : 'TTS Off', onPress: () => router.push('/settings/academy' as any) },
    { key: 'galaxy-studio', title: 'Galaxy Studio', subtitle: 'Per-category emphasis sliders, file-size preferences', icon: 'planet', color: '#3B82F6', badge: getGalaxyBadge(galaxy.phaseWeights), onPress: () => router.push('/settings/galaxy-studio' as any) },
    { key: 'haptics', title: 'Haptics', subtitle: 'Feedback intensity — off / light / full · saves per-device', icon: 'pulse-outline', color: '#A78BFA', badge: getHapticsLevel().toUpperCase(), onPress: () => router.push('/settings/haptics' as any) },
    { key: 'appearance', title: 'App Skin', subtitle: '30 reskins — recolor the whole app · default Hyperwave', icon: 'color-palette', color: '#c026d3', badge: 'NEW', onPress: () => router.push('/settings/appearance' as any) },
    { key: 'offline', title: 'Sync for Offline', subtitle: 'Download books, bibles & tracks for offline reading', icon: 'cloud-download', color: '#F472B6', badge: 'OFFLINE', onPress: () => router.push('/settings/offline' as any) },
    { key: 'scheduler', title: 'Calendar & Scheduler', subtitle: 'Live clock • monthly calendar • event scheduler', icon: 'calendar', color: '#10B981', badge: 'NEW', onPress: () => router.push('/scheduler' as any) },
    { key: 'dashboard', title: 'Dashboard', subtitle: 'Streaks, daily progress, achievements at a glance', icon: 'speedometer', color: '#F5C451', badge: 'NEW', onPress: () => router.push('/dashboard' as any) },
    { key: 'profile', title: 'Profile & Goals', subtitle: 'Avatar, daily goals, lifetime stats, achievements', icon: 'person-circle', color: '#3B82F6', badge: 'NEW', onPress: () => router.push('/profile' as any) },
    { key: 'pomodoro', title: 'Pomodoro Timer', subtitle: 'Focus 25 / break 5 / long 15 with session log', icon: 'timer', color: '#8B5CF6', badge: 'NEW', onPress: () => router.push('/pomodoro' as any) },
    { key: 'gallery', title: 'Build Gallery', subtitle: 'Browse every Galaxy Studio build you have created', icon: 'images', color: '#8B5CF6', badge: 'NEW', onPress: () => router.push('/gallery' as any) },
    { key: 'classes', title: 'My Classes', subtitle: 'Enrol, track progress, take quizzes, earn certificates', icon: 'school', color: '#10B981', badge: 'NEW', onPress: () => router.push('/my-classes' as any) },
    { key: 'search', title: 'Search', subtitle: 'Find books, bibles, tracks, and classes', icon: 'search', color: '#3B82F6', badge: 'NEW', onPress: () => router.push('/search' as any) },
    { key: 'flashcards', title: 'Flashcards', subtitle: 'Spaced-repetition study from any class glossary', icon: 'card', color: '#F472B6', badge: 'NEW', onPress: () => router.push('/flashcards' as any) },
  ];

  const [query, setQuery] = useState('');
  const submenus = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allSubmenus;
    return allSubmenus.filter(m =>
      m.title.toLowerCase().includes(q) ||
      m.subtitle.toLowerCase().includes(q) ||
      m.key.toLowerCase().includes(q),
    );
  }, [query, allSubmenus]);

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#2E1B5B33', '#3B82F622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[s.aurora, { pointerEvents: 'none' }]}
      />

      <AppHeader title="Settings" subtitle="Tune every surface of the app" onBack={() => router.back()} />

      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <Text style={s.intro}>
          Control how Jeeves, the Academy, and Galaxy Studio behave. Every setting persists locally and applies immediately.
        </Text>

        {/* "What's customised" glance row — surfaces totals from every
            persistent prefs surface so users can spot drift at a glance.
            Tapping opens an ActionSheet with a one-tap reset per surface. */}
        {(() => {
          const mp = getMenuPrefs();
          const hapticsTier = getHapticsLevel();
          const isCustom = hapticsTier !== 'full' || (mp.pinned.length + mp.hidden.length) > 0;
          if (!isCustom) return null;
          const openCustomisedSheet = () => {
            const options: any[] = [];
            if (hapticsTier !== 'full') {
              options.push({
                label: `Reset Haptics tier (currently ${hapticsTier.toUpperCase()})`,
                onPress: async () => {
                  await setHapticsLevel('full');
                  toast.success('Haptics returned to FULL');
                },
              });
            }
            if (mp.hidden.length > 0) {
              // Deep-link straight to the hidden-only view of /menu so users
              // can long-press to un-hide what they previously dismissed.
              options.push({
                label: `Show ${mp.hidden.length} hidden card${mp.hidden.length === 1 ? '' : 's'} on /menu`,
                onPress: () => router.push('/menu?showHidden=true' as any),
              });
            }
            if (mp.pinned.length > 0 || mp.hidden.length > 0) {
              options.push({
                label: `Reset menu curation (${mp.pinned.length} pinned · ${mp.hidden.length} hidden)`,
                onPress: async () => {
                  await resetMenuPrefs();
                  toast.success('Menu curation reset');
                },
              });
            }
            if (options.length > 1) {
              options.push({
                label: 'Reset everything customised',
                kind: 'destructive',
                onPress: async () => {
                  if (hapticsTier !== 'full') await setHapticsLevel('full');
                  if (mp.pinned.length + mp.hidden.length > 0) await resetMenuPrefs();
                  toast.success('All drifted preferences reset');
                },
              });
            }
            options.push({ label: 'Cancel', kind: 'cancel' });
            actionSheet.show({
              title: 'Customised surfaces',
              message: 'Review or reset each slice of your persisted prefs. Other content (notes, profile, classes) is untouched.',
              options,
            });
          };
          return (
            <Pressable
              onPress={openCustomisedSheet}
              style={s.customisedRow}
              testID="settings-customised-row"
              accessibilityLabel="Open customised settings reset sheet"
            >
              <Ionicons name="options-outline" size={14} color="#A78BFA" />
              <Text style={s.customisedLabel}>Customised:</Text>
              <View style={s.customisedChips}>
                {hapticsTier !== 'full' && (
                  <View style={s.miniChip}>
                    <Text style={s.miniChipText}>Haptics · {hapticsTier.toUpperCase()}</Text>
                  </View>
                )}
                {mp.pinned.length > 0 && (
                  <View style={s.miniChip}>
                    <Text style={s.miniChipText}>{mp.pinned.length} pinned</Text>
                  </View>
                )}
                {mp.hidden.length > 0 && (
                  <View style={s.miniChip}>
                    <Text style={s.miniChipText}>{mp.hidden.length} hidden</Text>
                  </View>
                )}
              </View>
              <Ionicons name="chevron-forward" size={14} color="#A78BFA" />
            </Pressable>
          );
        })()}

        {submenus.length === 0 && (
          <View style={s.emptyState}>
            <Ionicons name="search-outline" size={36} color="#475569" />
            <Text style={s.emptyTitle}>No matches for &quot;{query}&quot;</Text>
            <Text style={s.emptySub}>Try a different keyword like &quot;jeeves&quot;, &quot;haptics&quot;, or &quot;offline&quot;.</Text>
          </View>
        )}

        {submenus.map(m => (
          <Pressable
            key={m.key}
            onPress={m.onPress}
            style={({ pressed }) => [
              s.tile,
              { borderColor: m.color + '33' },
              pressed && { transform: [{ scale: 0.99 }], opacity: 0.9 },
            ]}
            accessibilityRole="button"
            accessibilityLabel={m.title}
          >
            <LinearGradient
              colors={[m.color + '14', 'transparent'] as any}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0.6 }}
              style={[StyleSheet.absoluteFillObject, { pointerEvents: 'none' }]}
            />
            <View style={[s.iconBubble, { backgroundColor: m.color + '22', borderColor: m.color + '44' }]}>
              <Ionicons name={m.icon as any} size={22} color={m.color} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.tileTitle}>{m.title}</Text>
              <Text style={s.tileSub}>{m.subtitle}</Text>
              <View style={[s.badge, { backgroundColor: m.color + '22', borderColor: m.color + '44' }]}>
                <Text style={[s.badgeText, { color: m.color }]}>{m.badge}</Text>
              </View>
            </View>
            <Ionicons name="chevron-forward" size={18} color={theme.colors.textDim} />
          </Pressable>
        ))}

        <View style={{ height: theme.spacing.lg }} />

        {/* Reset menu curation — only surfaces if the user has actually
            pinned or hidden something, so casual users never see it. */}
        {(() => {
          const mp = getMenuPrefs();
          const total = mp.pinned.length + mp.hidden.length;
          if (total === 0) return null;
          return (
            <Button
              label={`Reset menu curation (${total})`}
              icon="apps-outline"
              variant="secondary"
              onPress={() => actionSheet.show({
                title: 'Reset menu pins & hidden cards?',
                message: `${mp.pinned.length} pinned and ${mp.hidden.length} hidden feature${(mp.pinned.length + mp.hidden.length) === 1 ? '' : 's'} will be restored to their default position in /menu.`,
                options: [
                  { label: 'Cancel', kind: 'cancel' },
                  { label: 'Reset curation', kind: 'destructive', onPress: async () => {
                    await resetMenuPrefs();
                    toast.success('Menu curation reset');
                  }},
                ],
              })}
              fullWidth
            />
          );
        })()}

        <View style={{ height: theme.spacing.sm }} />
        <Button
          label="Reset all settings to defaults"
          icon="refresh"
          variant="secondary"
          onPress={() => actionSheet.show({
            title: 'Reset every setting?',
            message: 'Jeeves, Coding, API, Academy, Galaxy Studio, Haptics and more will return to defaults. Stored content (notes, profiles) is preserved.',
            options: [
              { label: 'Cancel', kind: 'cancel' },
              { label: 'Reset everything', kind: 'destructive', onPress: () => {
                useSettings.getState().resetAll();
                toast.warn('All settings reset');
              }},
            ],
          })}
          fullWidth
          textStyle={{ color: theme.colors.danger }}
        />

        <View style={{ height: theme.spacing.lg }} />
        <VaultCard />
      </ScrollView>

      <View style={s.searchRow}>
        <Ionicons name="search" size={16} color="#94a3b8" />
        <TextInput
          style={s.searchInput}
          placeholder="Search settings…"
          placeholderTextColor="#64748b"
          value={query}
          onChangeText={setQuery}
          autoCorrect={false}
          testID="settings-search"
        />
        {query.length > 0 && (
          <Pressable onPress={() => setQuery('')} hitSlop={10}>
            <Ionicons name="close-circle" size={16} color="#64748b" />
          </Pressable>
        )}
      </View>
    </Screen>
  );
}

function VaultCard() {
  const [stats, setStats] = React.useState<{ disk_mb: number; raw_mb: number; saved_mb: number; compression_ratio: number; zstd_level: number; builds: number; total_files: number; keep_target: number } | null>(null);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    const r = await api.get<any>('/api/galaxy-studio/admin/vault/stats');
    if (r.ok && r.data?.ok) setStats(r.data);
  }, []);
  React.useEffect(() => { load(); }, [load]);

  const reclaim = React.useCallback(async () => {
    setBusy(true);
    const r = await api.post<any>('/api/galaxy-studio/admin/vault/prune?keep=12', {});
    setBusy(false);
    if (r.ok && r.data?.ok) {
      toast.success(`Reclaimed ${r.data.reclaimed_mb} MB`);
      load();
    } else {
      toast.warn('Could not reclaim space');
    }
  }, [load]);

  const buildUrl = React.useCallback(() => {
    const id = stats?.newest_build_id;
    if (!id) return null;
    const base = process.env.EXPO_PUBLIC_BACKEND_URL || '';
    return `${base}/api/galaxy-studio/download/${id}`;
  }, [stats]);

  const copyLink = React.useCallback(async () => {
    const url = buildUrl();
    if (!url) { toast.warn('No build to share yet'); return; }
    try {
      await Clipboard.setStringAsync(url);
      toast.success('Share link copied');
    } catch {
      toast.warn('Could not copy link');
    }
  }, [buildUrl]);

  // Live disk-usage badge: green → amber → red as the vault grows.
  const mb = stats?.disk_mb ?? 0;
  const usageColor = mb >= 2000 ? '#ef4444' : mb >= 500 ? '#f59e0b' : '#10B981';
  const usageLabel = mb >= 2000 ? 'HIGH' : mb >= 500 ? 'WATCH' : 'OK';

  return (
    <View style={vstyles.card}>
      <View style={vstyles.row}>
        <Ionicons name="server" size={18} color={usageColor} />
        <Text style={vstyles.title}>Build Vault</Text>
        {stats ? (
          <View style={[vstyles.pill, { backgroundColor: usageColor + '22', borderColor: usageColor + '55' }]}>
            <View style={[vstyles.dot, { backgroundColor: usageColor }]} />
            <Text style={[vstyles.pillTxt, { color: usageColor }]}>{usageLabel}</Text>
          </View>
        ) : null}
        <Text style={[vstyles.usage, { color: usageColor }]}>{stats ? `${stats.disk_mb} MB` : '—'}</Text>
      </View>
      <Text style={vstyles.sub}>
        {stats
          ? `${stats.builds} build${stats.builds === 1 ? '' : 's'} · ${stats.total_files.toLocaleString()} files · keeps ${stats.keep_target} newest`
          : 'Loading vault usage…'}
      </Text>
      {stats ? (
        <Text style={vstyles.compress}>
          ⚡ zstd-{stats.zstd_level} · {stats.compression_ratio}:1 · saved {stats.saved_mb.toLocaleString()} MB (raw {stats.raw_mb.toLocaleString()} MB)
        </Text>
      ) : null}
      <View style={vstyles.btnRow}>
        <Pressable
          onPress={reclaim}
          disabled={busy}
          style={({ pressed }) => [vstyles.btn, vstyles.btnFlex, (pressed || busy) && { opacity: 0.6 }]}
        >
          <Ionicons name="trash-bin-outline" size={15} color="#fff" />
          <Text style={vstyles.btnTxt}>{busy ? 'Reclaiming…' : 'Reclaim space'}</Text>
        </Pressable>
        <Pressable
          onPress={() => {
            const id = stats?.newest_build_id;
            if (!id) { toast.warn('No build to export yet'); return; }
            const base = process.env.EXPO_PUBLIC_BACKEND_URL || '';
            Linking.openURL(`${base}/api/galaxy-studio/download/${id}`).catch(() => toast.warn('Could not open export'));
          }}
          disabled={!stats?.newest_build_id}
          style={({ pressed }) => [vstyles.btn, vstyles.btnAlt, vstyles.btnFlex, (pressed || !stats?.newest_build_id) && { opacity: 0.6 }]}
        >
          <Ionicons name="download-outline" size={15} color="#fff" />
          <Text style={vstyles.btnTxt}>Export .zip</Text>
        </Pressable>
        <Pressable
          onPress={copyLink}
          disabled={!stats?.newest_build_id}
          style={({ pressed }) => [vstyles.btn, vstyles.btnCopy, vstyles.btnFlex, (pressed || !stats?.newest_build_id) && { opacity: 0.6 }]}
        >
          <Ionicons name="link-outline" size={15} color="#fff" />
          <Text style={vstyles.btnTxt}>Copy link</Text>
        </Pressable>
      </View>
    </View>
  );
}

const vstyles = StyleSheet.create({
  card: { backgroundColor: '#141414', borderRadius: 14, borderWidth: 1, borderColor: '#262626', padding: 14, gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { color: '#e2e8f0', fontSize: 15, fontWeight: '700', flex: 1 },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, borderWidth: 1 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  pillTxt: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  usage: { fontSize: 15, fontWeight: '800' },
  sub: { color: '#94a3b8', fontSize: 12 },
  compress: { color: '#3B82F6', fontSize: 11, fontWeight: '600' },
  btnRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
  btnFlex: { flex: 1, marginTop: 0 },
  btnAlt: { backgroundColor: '#8B5CF6' },
  btnCopy: { backgroundColor: '#404040' },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#3B82F6', borderRadius: 10, paddingVertical: 10, marginTop: 4 },
  btnTxt: { color: '#fff', fontWeight: '700', fontSize: 13 },
});

function getGalaxyBadge(pw: any) {
  const vals = Object.values(pw) as number[];
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  if (avg === 1.0 && vals.every(v => v === 1.0)) return 'Default';
  return `AVG ${avg.toFixed(1)}×`;
}

const s = StyleSheet.create({
  aurora: { position: 'absolute', top: 0, left: 0, right: 0, height: 240 },
  scroll: { padding: theme.spacing.base, paddingBottom: theme.spacing['2xl'] },
  intro: {
    ...theme.typography.body,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.base,
    paddingHorizontal: theme.spacing.xs,
    lineHeight: 20,
  },
  searchRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: theme.colors.surfaceAlt || '#141414',
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: 12, paddingVertical: 10,
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  searchInput: { flex: 1, color: theme.colors.text, fontSize: 13 },
  customisedRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: '#A78BFA12',
    borderRadius: theme.radii.md,
    borderWidth: 1, borderColor: '#A78BFA33',
    marginBottom: theme.spacing.md,
  },
  customisedLabel: { color: '#A78BFA', fontSize: 11, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase' },
  customisedChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, flex: 1 },
  miniChip: {
    paddingHorizontal: 8, paddingVertical: 3,
    backgroundColor: '#A78BFA22',
    borderRadius: theme.radii.full,
    borderWidth: 1, borderColor: '#A78BFA55',
  },
  miniChipText: { color: '#C4B5FD', fontSize: 10, fontWeight: '700' },
  emptyState: { alignItems: 'center', paddingVertical: 40, paddingHorizontal: 24 },
  emptyTitle: { color: theme.colors.text, fontSize: 14, fontWeight: '700', marginTop: 10 },
  emptySub:   { color: theme.colors.textDim, fontSize: 12, marginTop: 4, textAlign: 'center', lineHeight: 16 },
  tile: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: theme.spacing.md,
    gap: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    overflow: 'hidden',
    ...theme.elevation.xs,
  },
  iconBubble: {
    width: 44, height: 44,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    justifyContent: 'center', alignItems: 'center',
  },
  tileTitle: {
    ...theme.typography.h4,
    color: theme.colors.text,
  },
  tileSub: {
    ...theme.typography.caption,
    color: theme.colors.textMuted,
    marginTop: 2,
    fontWeight: '500',
  },
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: theme.radii.full,
    marginTop: 6,
    borderWidth: 1,
  },
  badgeText: {
    fontSize: 10, fontWeight: '800', letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
});
