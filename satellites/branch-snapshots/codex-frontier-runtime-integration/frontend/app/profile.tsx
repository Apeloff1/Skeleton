/**
 * Profile screen — avatar (color picker), name, email, bio, goals, theme toggle,
 * achievement showcase, reset button.
 */
import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, Switch, Share, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useUser, setProfile, setGoals, setTheme, resetUser, getState, AVATAR_COLORS, ACHIEVEMENT_CATALOG } from '../utils/userStore';
import { openModalFromRoute } from '../utils/openModalFromRoute';
import AsyncStorage from '@react-native-async-storage/async-storage';
import theme from '../theme/tokens';
import { Screen, AppHeader } from '../components/ui';
import { toast } from '../components/Toast';
import { actionSheet, promptSheet } from '../components/ActionSheet';

export default function ProfileScreen() {
  const router = useRouter();
  const user = useUser();
  const [name, setName] = useState(user.profile.name);
  const [email, setEmail] = useState(user.profile.email);
  const [bio, setBio] = useState(user.profile.bio);
  const [color, setColor] = useState(user.profile.avatar_color);

  useEffect(() => {
    setName(user.profile.name);
    setEmail(user.profile.email);
    setBio(user.profile.bio);
    setColor(user.profile.avatar_color);
  }, [user.profile]);

  const save = async () => {
    await setProfile({ name: name.trim() || 'Explorer', email, bio, avatar_color: color });
    toast.success('Profile saved');
  };

  const reset = () => {
    actionSheet.show({
      title: 'Reset all data?',
      message: 'This deletes your profile, streaks, achievements, stats, and goals. Cannot be undone.',
      options: [
        { label: 'Cancel', kind: 'cancel' },
        { label: 'Reset everything', kind: 'destructive', onPress: () => {
          try {
            resetUser();
            toast.warn('Profile reset');
          } catch (e: any) {
            toast.error(`Reset failed: ${e?.message || 'unknown'}`);
          }
        }},
      ],
    });
  };

  const unlockedAchievements = ACHIEVEMENT_CATALOG.filter(a => user.unlocked_achievements.includes(a.id));
  const lockedAchievements = ACHIEVEMENT_CATALOG.filter(a => !user.unlocked_achievements.includes(a.id));

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={[color + '33', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[{ position: 'absolute', top: 0, left: 0, right: 0, height: 240 }, { pointerEvents: 'none' }]}
      />
      <AppHeader title="Profile" onBack={() => router.back()} />

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80 }}>
        {/* Avatar */}
        <View style={s.avatarWrap}>
          <View style={[s.avatar, { backgroundColor: color }]}>
            <Text style={s.avatarText}>{(name || 'X').charAt(0).toUpperCase()}</Text>
          </View>
          <View style={s.colorRow}>
            {AVATAR_COLORS.map(c => (
              <TouchableOpacity
                key={c}
                onPress={() => setColor(c)}
                style={[s.colorDot, { backgroundColor: c, borderColor: color === c ? '#fff' : 'transparent' }]}
              />
            ))}
          </View>
        </View>

        {/* Fields */}
        <Text style={s.label}>Display name</Text>
        <TextInput style={s.input} value={name} onChangeText={setName} placeholderTextColor="#475569" />
        <Text style={s.label}>Email (optional)</Text>
        <TextInput style={s.input} value={email} onChangeText={setEmail} placeholder="you@example.com" placeholderTextColor="#475569" keyboardType="email-address" autoCapitalize="none" />
        <Text style={s.label}>Bio</Text>
        <TextInput style={[s.input, { minHeight: 60, textAlignVertical: 'top' }]} value={bio} onChangeText={setBio} placeholder="Tell us about yourself…" placeholderTextColor="#475569" multiline />

        <TouchableOpacity style={s.saveBtn} onPress={save} activeOpacity={0.8}>
          <Ionicons name="checkmark" size={16} color="#fff" />
          <Text style={s.saveBtnText}>Save Profile</Text>
        </TouchableOpacity>

        {/* Theme */}
        <Text style={s.sectionTitle}>Appearance</Text>
        <View style={s.card}>
          <View style={s.row}>
            <Ionicons name={user.theme === 'dark' ? 'moon' : 'sunny'} size={16} color="#F5C451" />
            <Text style={s.rowLabel}>Theme</Text>
            <Switch
              value={user.theme === 'dark'}
              onValueChange={(v) => setTheme(v ? 'dark' : 'light')}
              trackColor={{ false: '#404040', true: '#F5C451AA' }}
              thumbColor={user.theme === 'dark' ? '#F5C451' : '#94A3B8'}
            />
            <Text style={s.rowValue}>{user.theme === 'dark' ? 'Dark' : 'Light'}</Text>
          </View>
        </View>

        {/* Goals */}
        <Text style={s.sectionTitle}>Daily Goals</Text>
        <View style={s.card}>
          <GoalRow icon="book" color="#3B82F6" label="Reading minutes" value={user.goals.daily_reading_minutes} onChange={(v: number) => setGoals({ daily_reading_minutes: v })} step={10} />
          <GoalRow icon="time" color="#8B5CF6" label="Focus minutes" value={user.goals.daily_focus_minutes} onChange={(v: number) => setGoals({ daily_focus_minutes: v })} step={15} />
          <GoalRow icon="school" color="#10B981" label="Class weeks / day" value={user.goals.daily_classes_progress} onChange={(v: number) => setGoals({ daily_classes_progress: v })} step={1} />
        </View>

        {/* Stats summary */}
        <Text style={s.sectionTitle}>Lifetime Stats</Text>
        <View style={s.statGrid}>
          <Stat label="Chapters" value={user.stats.reading_chapters_completed} />
          <Stat label="Weeks done" value={user.stats.classes_weeks_completed} />
          <Stat label="Builds" value={user.stats.galaxy_builds} />
          <Stat label="Best streak" value={user.stats.streak_best} />
          <Stat label="Focus mins" value={user.stats.pomodoro_focus_minutes} />
          <Stat label="Total XP" value={user.stats.total_xp.toLocaleString()} />
        </View>

        {/* Achievements */}
        <Text style={s.sectionTitle}>Achievements ({unlockedAchievements.length}/{ACHIEVEMENT_CATALOG.length})</Text>
        <View style={s.card}>
          <Text style={s.subLabel}>Unlocked</Text>
          <View style={s.badgeWrap}>
            {unlockedAchievements.length === 0 ? (
              <Text style={s.empty}>No achievements yet. Start reading or building to earn your first badge.</Text>
            ) : unlockedAchievements.map(a => (
              <View key={a.id} style={[s.badge, { borderColor: a.color, backgroundColor: a.color + '22' }]}>
                <Ionicons name={a.icon as any} size={14} color={a.color} />
                <Text style={[s.badgeText, { color: a.color }]}>{a.title}</Text>
              </View>
            ))}
          </View>
          <Text style={[s.subLabel, { marginTop: 16 }]}>Locked</Text>
          <View style={s.badgeWrap}>
            {lockedAchievements.slice(0, 12).map(a => (
              <View key={a.id} style={[s.badge, { borderColor: '#404040', backgroundColor: '#141414' }]}>
                <Ionicons name="lock-closed" size={12} color="#64748B" />
                <Text style={[s.badgeText, { color: '#64748B' }]}>{a.title}</Text>
              </View>
            ))}
          </View>
        </View>

        <TouchableOpacity style={s.dangerBtn} onPress={reset} activeOpacity={0.8}>
          <Ionicons name="trash" size={14} color="#EF4444" />
          <Text style={s.dangerBtnText}>Reset All Data</Text>
        </TouchableOpacity>

        {/* Export / Import data — share JSON snapshot for backup */}
        <View style={s.ioRow}>
          <TouchableOpacity
            style={s.ioBtn}
            onPress={async () => {
              try {
                const state = await getState();
                const json = JSON.stringify(state, null, 2);
                if (Platform.OS === 'web') {
                  await navigator.clipboard.writeText(json);
                  toast.success('Snapshot copied to clipboard');
                } else {
                  await Share.share({ message: json, title: 'CodeDock user snapshot' });
                }
              } catch (e: any) {
                toast.error(`Export failed: ${e.message || 'unknown'}`);
              }
            }}
            activeOpacity={0.85}
          >
            <Ionicons name="cloud-upload" size={14} color="#10B981" />
            <Text style={s.ioBtnText}>Export JSON</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={s.ioBtn}
            onPress={() => {
              promptSheet.show({
                title: 'Paste user JSON',
                message: 'Paste a previously-exported user snapshot. Works on every platform.',
                placeholder: '{ "profile": { ... }, "stats": { ... } }',
                multiline: true,
                submitLabel: 'Import',
                onSubmit: async (txt) => {
                  if (!txt?.trim()) { toast.warn('Nothing pasted'); return; }
                  try {
                    const parsed = JSON.parse(txt);
                    await AsyncStorage.setItem('@codedock:user', JSON.stringify(parsed));
                    toast.success('Imported · reload to apply', {
                      durationMs: 4500,
                      action: { label: 'Reload', onPress: () => {
                        try {
                          if (typeof window !== 'undefined') (window as any).location?.reload?.();
                        } catch { /* swallow */ }
                      }},
                    });
                  } catch {
                    toast.error('Invalid JSON · check formatting');
                  }
                },
              });
            }}
            activeOpacity={0.85}
          >
            <Ionicons name="cloud-download" size={14} color="#3B82F6" />
            <Text style={[s.ioBtnText, { color: '#3B82F6' }]}>Import JSON</Text>
          </TouchableOpacity>
        </View>

        {/* P3 modal launcher — full Achievements modal with badges history */}
        <TouchableOpacity
          style={s.modalLauncher}
          onPress={() => openModalFromRoute(router, 'achievements')}
          activeOpacity={0.85}
        >
          <Ionicons name="medal" size={16} color="#F5C451" />
          <Text style={s.modalLauncherText}>Open full Achievements gallery →</Text>
        </TouchableOpacity>
      </ScrollView>
    </Screen>
  );
}

function GoalRow({ icon, color, label, value, onChange, step }: any) {
  return (
    <View style={s.goalRow}>
      <Ionicons name={icon} size={16} color={color} />
      <Text style={s.goalLabel}>{label}</Text>
      <View style={s.goalControls}>
        <TouchableOpacity onPress={() => onChange(Math.max(0, value - step))} style={s.goalBtn}>
          <Ionicons name="remove" size={14} color="#94A3B8" />
        </TouchableOpacity>
        <Text style={s.goalValue}>{value}</Text>
        <TouchableOpacity onPress={() => onChange(value + step)} style={s.goalBtn}>
          <Ionicons name="add" size={14} color="#94A3B8" />
        </TouchableOpacity>
      </View>
    </View>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <View style={s.statCard}>
      <Text style={s.statValue}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: theme.colors.bgElevated, borderBottomWidth: 1, borderBottomColor: theme.colors.border },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: theme.colors.text },
  avatarWrap: { alignItems: 'center', marginBottom: theme.spacing.lg },
  avatar: { width: 96, height: 96, borderRadius: 48, justifyContent: 'center', alignItems: 'center', borderWidth: 3, borderColor: theme.colors.bgElevated, ...theme.elevation.lg },
  avatarText: { color: '#fff', fontSize: 42, fontWeight: '800' },
  colorRow: { flexDirection: 'row', gap: 8, marginTop: 16, flexWrap: 'wrap', justifyContent: 'center' },
  colorDot: { width: 32, height: 32, borderRadius: 16, borderWidth: 2 },
  label: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginTop: theme.spacing.md, marginBottom: 6, letterSpacing: 0.8 },
  input: { backgroundColor: theme.colors.surface, borderRadius: theme.radii.md, padding: 14, color: theme.colors.text, fontSize: 14, borderWidth: 1, borderColor: theme.colors.border },
  saveBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.primary, borderRadius: theme.radii.md, paddingVertical: 14, gap: 8, marginTop: theme.spacing.base, ...theme.elevation.glow },
  saveBtnText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  sectionTitle: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginTop: theme.spacing.xl, marginBottom: theme.spacing.sm, letterSpacing: 1 },
  card: { backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: theme.spacing.md, borderWidth: 1, borderColor: theme.colors.border, ...theme.elevation.xs },
  row: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm },
  rowLabel: { color: theme.colors.text, fontSize: 13, flex: 1, fontWeight: '600' },
  rowValue: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '700', width: 50, textAlign: 'right' },
  goalRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 10 },
  goalLabel: { color: theme.colors.text, fontSize: 13, flex: 1, fontWeight: '600' },
  goalControls: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm },
  goalBtn: { width: 32, height: 32, borderRadius: theme.radii.sm, backgroundColor: theme.colors.bgSubtle, borderWidth: 1, borderColor: theme.colors.border, justifyContent: 'center', alignItems: 'center' },
  goalValue: { color: theme.colors.text, fontSize: 14, fontWeight: '800', minWidth: 40, textAlign: 'center' },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  statCard: { width: '31%', backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: theme.spacing.md, alignItems: 'center', borderWidth: 1, borderColor: theme.colors.border },
  statValue: { fontSize: 22, color: theme.colors.text, fontWeight: '800', letterSpacing: -0.4 },
  statLabel: { color: theme.colors.textMuted, fontSize: 10, marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: '700' },
  badgeWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  badge: { flexDirection: 'row', alignItems: 'center', borderRadius: theme.radii.full, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, gap: 5 },
  badgeText: { fontSize: 11, fontWeight: '700' },
  subLabel: { color: theme.colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', marginBottom: 6, letterSpacing: 0.6 },
  empty: { color: theme.colors.textDim, fontSize: 12, fontStyle: 'italic' },
  dangerBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#7F1D1D', borderRadius: 10, paddingVertical: 12, gap: 6, marginTop: 24 },
  dangerBtnText: { color: '#EF4444', fontWeight: '700', fontSize: 12 },
  ioRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  ioBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.surface, borderWidth: 1, borderColor: theme.colors.border, borderRadius: 10, paddingVertical: 11, gap: 6 },
  ioBtnText: { color: '#10B981', fontWeight: '700', fontSize: 11 },
  modalLauncher: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 12, paddingVertical: 12, paddingHorizontal: 16, borderRadius: 10, borderWidth: 1, borderColor: '#F5C45155', backgroundColor: '#F5C45115' },
  modalLauncherText: { color: '#F5C451', fontSize: 12, fontWeight: '700' },
});
