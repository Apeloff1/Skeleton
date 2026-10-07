/**
 * /anti-cheat — Anti-Cheat Dashboard.
 *
 * Surfaces the server-side anti-cheat audit feed (collection: anticheat_log):
 * total adjustments/blocks, top clamp reasons, most-flagged users, a per-action
 * breakdown, and a live recent-violations list. Read-only admin view.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, Platform, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

interface Stats {
  total_violations: number;
  flagged_users: number;
  rate_limit_blocks: number;
  top_flags: { flag: string; count: number }[];
  top_users: { user_id: string; count: number; actions: string[] }[];
  by_action: { action: string; count: number }[];
}
interface Violation {
  user_id: string; action: string; flags: string[];
  raw?: Record<string, unknown>; timestamp: string;
}

const FLAG_LABELS: Record<string, string> = {
  rate_limited: 'Rate limited (grind block)',
  amount_capped: 'XP amount capped',
  nonpositive_amount: 'Non-positive XP rejected',
  invalid_amount_type: 'Invalid XP type',
  score_capped: 'Score capped',
  correct_clamped: 'Correct > total clamped',
  total_clamped: 'Question count clamped',
  negative_score: 'Negative score zeroed',
};
const flagLabel = (f: string) => FLAG_LABELS[f] || f.replace(/_/g, ' ');

export default function AntiCheatScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [violations, setViolations] = React.useState<Violation[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    const [s, v] = await Promise.all([
      api.get<Stats>('/api/anticheat/stats'),
      api.get<{ violations: Violation[] }>('/api/anticheat/violations?limit=50'),
    ]);
    if (s.ok && s.data) setStats(s.data);
    else setError(s.error || `HTTP ${s.status}`);
    if (v.ok && v.data?.violations) setViolations(v.data.violations);
    setLoading(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const onRefresh = React.useCallback(() => {
    haptics.selection();
    setLoading(true);
    load();
  }, [haptics, load]);

  const maxFlag = stats?.top_flags?.[0]?.count || 1;

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header} testID="anti-cheat-header">
        <TouchableOpacity testID="anti-cheat-back" onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Anti-Cheat</Text>
        <TouchableOpacity testID="anti-cheat-refresh" onPress={onRefresh} style={styles.backBtn}>
          <Text style={[styles.backTxt, { textAlign: 'right' }]}>↻</Text>
        </TouchableOpacity>
      </View>

      {stats ? (
        <View style={styles.statsRow}>
          <Stat testID="stat-total" label="Adjustments" value={String(stats.total_violations)} color="#f59e0b" />
          <Stat testID="stat-users" label="Flagged users" value={String(stats.flagged_users)} color="#3B82F6" />
          <Stat testID="stat-blocks" label="RL blocks" value={String(stats.rate_limit_blocks)} color="#ef4444" />
        </View>
      ) : null}

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={{ paddingBottom: 28 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={onRefresh} tintColor="#8B5CF6" />}
      >
        {loading && !stats ? (
          <View style={styles.center}>
            <ActivityIndicator color="#8B5CF6" size="large" />
            <Text style={styles.hint}>Loading audit feed…</Text>
          </View>
        ) : null}

        {error ? (
          <View style={styles.center}>
            <Text style={styles.errTitle}>Could not load stats</Text>
            <Text style={styles.errSub}>{error}</Text>
          </View>
        ) : null}

        {stats && stats.total_violations === 0 ? (
          <View style={styles.center}>
            <Text style={styles.cleanTitle}>No cheating detected 🛡️</Text>
            <Text style={styles.hint}>All score & XP submissions have been within legitimate bounds.</Text>
          </View>
        ) : null}

        {stats && stats.top_flags.length > 0 ? (
          <Section title="Top flag reasons">
            {stats.top_flags.map((f) => (
              <View key={f.flag} style={styles.barRow} testID={`flag-${f.flag}`}>
                <View style={styles.barLabelWrap}>
                  <Text style={styles.barLabel} numberOfLines={1}>{flagLabel(f.flag)}</Text>
                  <Text style={styles.barCount}>{f.count}</Text>
                </View>
                <View style={styles.barTrack}>
                  <View style={[styles.barFill, { width: `${Math.max(6, (f.count / maxFlag) * 100)}%` }]} />
                </View>
              </View>
            ))}
          </Section>
        ) : null}

        {stats && stats.top_users.length > 0 ? (
          <Section title="Most-flagged users">
            {stats.top_users.map((u, i) => (
              <View key={u.user_id} style={styles.userRow} testID={`user-${u.user_id}`}>
                <Text style={styles.userRank}>{i + 1}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.userId} numberOfLines={1}>{u.user_id}</Text>
                  <Text style={styles.userActions} numberOfLines={1}>{u.actions.join(' · ')}</Text>
                </View>
                <Text style={styles.userCount}>{u.count}</Text>
              </View>
            ))}
          </Section>
        ) : null}

        {stats && stats.by_action.length > 0 ? (
          <Section title="By endpoint">
            <View style={styles.chipsWrap}>
              {stats.by_action.map((a) => (
                <View key={a.action} style={styles.chip} testID={`action-${a.action}`}>
                  <Text style={styles.chipTxt}>{a.action}</Text>
                  <Text style={styles.chipCount}>{a.count}</Text>
                </View>
              ))}
            </View>
          </Section>
        ) : null}

        {violations.length > 0 ? (
          <Section title={`Recent activity (${violations.length})`}>
            {violations.map((v, i) => (
              <View key={`${v.timestamp}-${i}`} style={styles.vRow} testID={`violation-${i}`}>
                <View style={[styles.vDot, { backgroundColor: v.flags.includes('rate_limited') ? '#ef4444' : '#f59e0b' }]} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.vTop}>
                    <Text style={styles.vUser}>{v.user_id}</Text>
                    <Text style={styles.vAction}>  ·  {v.action}</Text>
                  </Text>
                  <Text style={styles.vFlags} numberOfLines={2}>{v.flags.map(flagLabel).join(', ')}</Text>
                </View>
                <Text style={styles.vTime}>{relTime(v.timestamp)}</Text>
              </View>
            ))}
          </Section>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function relTime(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    return `${Math.floor(s / 86400)}d`;
  } catch { return ''; }
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Stat({ label, value, color, testID }: { label: string; value: string; color: string; testID?: string }) {
  return (
    <View style={styles.stat} testID={testID}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 8 : 16, paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F',
  },
  backBtn: { paddingVertical: 6, paddingHorizontal: 10, width: 56 },
  backTxt: { color: '#93c5fd', fontSize: 16 },
  title: { color: '#fff', fontSize: 18, fontWeight: '700' },
  statsRow: { flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 12, gap: 8 },
  stat: { flex: 1, backgroundColor: '#0A0A0A', borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  statValue: { fontSize: 20, fontWeight: '800' },
  statLabel: { color: '#64748b', fontSize: 11, marginTop: 2 },
  scroll: { flex: 1 },
  center: { padding: 40, alignItems: 'center', gap: 12 },
  hint: { color: '#94a3b8', fontSize: 13, textAlign: 'center' },
  cleanTitle: { color: '#10B981', fontSize: 16, fontWeight: '700' },
  errTitle: { color: '#e2e8f0', fontSize: 15, fontWeight: '600' },
  errSub: { color: '#64748b', fontSize: 12 },
  section: { marginHorizontal: 12, marginTop: 12 },
  sectionTitle: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginBottom: 8 },
  barRow: { marginBottom: 10 },
  barLabelWrap: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  barLabel: { color: '#e2e8f0', fontSize: 12, flex: 1, marginRight: 8 },
  barCount: { color: '#f59e0b', fontSize: 12, fontWeight: '800' },
  barTrack: { height: 8, backgroundColor: '#262626', borderRadius: 4, overflow: 'hidden' },
  barFill: { height: 8, backgroundColor: '#f59e0b', borderRadius: 4 },
  userRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#0A0A0A',
    borderRadius: 10, padding: 12, marginBottom: 8, gap: 12,
  },
  userRank: { color: '#64748b', fontSize: 14, fontWeight: '800', width: 18, textAlign: 'center' },
  userId: { color: '#fff', fontSize: 14, fontWeight: '600' },
  userActions: { color: '#64748b', fontSize: 11, marginTop: 2 },
  userCount: { color: '#ef4444', fontSize: 16, fontWeight: '800' },
  chipsWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#0A0A0A',
    borderWidth: 1, borderColor: '#1F1F1F', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6,
  },
  chipTxt: { color: '#cbd5e1', fontSize: 12, fontWeight: '600' },
  chipCount: { color: '#8B5CF6', fontSize: 12, fontWeight: '800' },
  vRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#0A0A0A',
    borderRadius: 10, padding: 12, marginBottom: 8, gap: 10,
  },
  vDot: { width: 8, height: 8, borderRadius: 4 },
  vTop: { fontSize: 13 },
  vUser: { color: '#fff', fontWeight: '700' },
  vAction: { color: '#94a3b8', fontWeight: '500' },
  vFlags: { color: '#fbbf24', fontSize: 11, marginTop: 2 },
  vTime: { color: '#64748b', fontSize: 11, fontWeight: '600' },
});
