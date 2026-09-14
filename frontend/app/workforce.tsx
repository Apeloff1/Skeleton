import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { AppHeader, Button, Screen, SectionHeader } from '../components/UI';
import theme from '../theme/tokens';
import {
  WorkState,
  WorkforceSnapshot,
  closeActiveSession,
  coinsForSeconds,
  durationSeconds,
  emptyWorkforceSnapshot,
  formatDuration,
  getNextMilestone,
  loadWorkforce,
  saveWorkforce,
  transitionWorkState,
} from '../src/workspaces/workforceStore';

const STATE_META: Record<WorkState, { label: string; icon: string; color: string }> = {
  idle: { label: 'Idle', icon: 'stop-circle', color: theme.colors.textMuted },
  working: { label: 'Working', icon: 'briefcase', color: theme.colors.success },
  break: { label: 'Break', icon: 'cafe', color: theme.colors.info },
  food: { label: 'Food', icon: 'restaurant', color: theme.colors.warning },
  smoke: { label: 'Smoke', icon: 'cloud', color: theme.colors.textMuted },
};

const EMPTY: WorkforceSnapshot = emptyWorkforceSnapshot();

export default function WorkforceScreen() {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<WorkforceSnapshot>(EMPTY);
  const [now, setNow] = useState(Date.now());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    loadWorkforce()
      .then(data => { if (mounted) setSnapshot(data); })
      .finally(() => { if (mounted) setReady(true); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!snapshot.activeSince) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [snapshot.activeSince]);

  const activeSeconds = useMemo(
    () => durationSeconds(snapshot.activeSince, now),
    [snapshot.activeSince, now],
  );
  const activeIsProductive = snapshot.activeState === 'working';
  const projectedTotal = snapshot.totalSeconds + activeSeconds;
  const projectedProductive = snapshot.productiveSeconds + (activeIsProductive ? activeSeconds : 0);
  const projectedPause = snapshot.pauseSeconds + (snapshot.activeState !== 'idle' && !activeIsProductive ? activeSeconds : 0);
  const projectedCoins = Math.max(snapshot.coinsEarned, coinsForSeconds(projectedProductive));
  const nextMilestone = getNextMilestone(projectedCoins);
  const milestoneProgress = nextMilestone
    ? Math.min(1, projectedCoins / nextMilestone)
    : 1;

  const persist = useCallback(async (next: WorkforceSnapshot) => {
    setSnapshot(next);
    setNow(Date.now());
    await saveWorkforce(next);
  }, []);

  const transition = useCallback((state: WorkState) => {
    const next = transitionWorkState(snapshot, state);
    persist(next).catch(() => {});
  }, [persist, snapshot]);

  const stop = useCallback(() => {
    const next = closeActiveSession(snapshot);
    persist(next).catch(() => {});
  }, [persist, snapshot]);

  const currentMeta = STATE_META[snapshot.activeState];
  const isClockedIn = snapshot.activeState !== 'idle';

  return (
    <Screen edges={['top', 'left', 'right']}>
      <AppHeader
        title="Work OS"
        subtitle="Time · focus · value · durable session ledger"
        onBack={() => router.back()}
      />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.timerCard}>
          <View style={styles.stateRow}>
            <View style={[styles.stateDot, { backgroundColor: currentMeta.color }]} />
            <Text style={[styles.stateLabel, { color: currentMeta.color }]}>{ready ? currentMeta.label : 'Loading'}</Text>
          </View>
          <Text style={styles.timer}>{formatDuration(activeSeconds)}</Text>
          <Text style={styles.timerCaption}>
            {snapshot.activeSince ? `Started ${new Date(snapshot.activeSince).toLocaleTimeString()}` : 'No active session'}
          </Text>

          <View style={styles.primaryActions}>
            {!isClockedIn ? (
              <Button title="Clock In" icon="play" onPress={() => transition('working')} style={styles.flexButton} />
            ) : (
              <Button title="Clock Out" icon="stop" onPress={stop} style={styles.flexButton} />
            )}
          </View>

          <View style={styles.breakRow}>
            <StateButton state="break" current={snapshot.activeState} onPress={transition} disabled={!isClockedIn} />
            <StateButton state="food" current={snapshot.activeState} onPress={transition} disabled={!isClockedIn} />
            <StateButton state="smoke" current={snapshot.activeState} onPress={transition} disabled={!isClockedIn} />
          </View>
          <Text style={styles.breakHint}>
            {isClockedIn ? 'Pause states stop productive-time coin accrual until you resume work.' : 'Clock in before starting a pause state.'}
          </Text>
        </View>

        <View style={styles.metricGrid}>
          <Metric icon="briefcase" label="Productive" value={formatDuration(projectedProductive)} color={theme.colors.success} />
          <Metric icon="pause-circle" label="Paused" value={formatDuration(projectedPause)} color={theme.colors.info} />
          <Metric icon="time" label="Tracked" value={formatDuration(projectedTotal)} color={theme.colors.primaryHover} />
          <Metric icon="diamond" label="Coins" value={projectedCoins.toLocaleString()} color={theme.colors.warning} />
        </View>

        <SectionHeader title="Value Progression" subtitle="200 coins per productive hour · pause time excluded" />
        <View style={styles.progressCard}>
          <View style={styles.progressHeader}>
            <Text style={styles.progressValue}>{projectedCoins.toLocaleString()} coins</Text>
            <Text style={styles.progressTarget}>{nextMilestone ? `${nextMilestone.toLocaleString()} target` : 'Max milestone reached'}</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.max(2, milestoneProgress * 100)}%` }]} />
          </View>
          <Text style={styles.progressHint}>
            {nextMilestone
              ? `${Math.max(0, nextMilestone - projectedCoins).toLocaleString()} coins until the next milestone.`
              : 'All configured milestones completed.'}
          </Text>
        </View>

        <SectionHeader title="Recent Sessions" subtitle="Newest first · local-first persistence · schema v3" />
        <View style={styles.ledger}>
          {snapshot.sessions.length === 0 ? (
            <View style={styles.emptyLedger}>
              <Ionicons name="receipt-outline" size={24} color={theme.colors.textDim} />
              <Text style={styles.emptyTitle}>No completed sessions yet</Text>
              <Text style={styles.emptyText}>Clock in, switch states as needed, then clock out to create the first ledger entry.</Text>
            </View>
          ) : snapshot.sessions.slice(0, 20).map(session => {
            const meta = STATE_META[session.state];
            const productive = session.state === 'working';
            return (
              <View key={session.id} style={styles.sessionRow}>
                <View style={[styles.sessionIcon, { backgroundColor: `${meta.color}22` }]}>
                  <Ionicons name={meta.icon as any} size={16} color={meta.color} />
                </View>
                <View style={styles.sessionBody}>
                  <Text style={styles.sessionTitle}>{meta.label}</Text>
                  <Text style={styles.sessionSub}>
                    {new Date(session.startedAt).toLocaleString()} · {formatDuration(session.seconds)}
                  </Text>
                </View>
                <Text style={[styles.sessionCoins, !productive && styles.pauseSessionLabel]}>
                  {productive ? `+${coinsForSeconds(session.seconds)}` : 'pause'}
                </Text>
              </View>
            );
          })}
        </View>
      </ScrollView>
    </Screen>
  );
}

function StateButton({
  state,
  current,
  onPress,
  disabled,
}: {
  state: WorkState;
  current: WorkState;
  onPress: (state: WorkState) => void;
  disabled: boolean;
}) {
  const meta = STATE_META[state];
  const active = current === state;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled, selected: active }}
      disabled={disabled}
      onPress={() => onPress(active ? 'working' : state)}
      style={[
        styles.stateButton,
        active && { borderColor: meta.color, backgroundColor: `${meta.color}18` },
        disabled && styles.stateButtonDisabled,
      ]}
    >
      <Ionicons name={meta.icon as any} size={16} color={active ? meta.color : theme.colors.textMuted} />
      <Text style={[styles.stateButtonText, active && { color: meta.color }]}>{meta.label}</Text>
    </Pressable>
  );
}

function Metric({ icon, label, value, color }: { icon: string; label: string; value: string; color: string }) {
  return (
    <View style={styles.metric}>
      <Ionicons name={icon as any} size={18} color={color} />
      <Text style={[styles.metricValue, { color }]} numberOfLines={1}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: theme.spacing.base, paddingBottom: 80, gap: theme.spacing.md },
  timerCard: {
    borderRadius: theme.radii['2xl'],
    padding: theme.spacing.xl,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
  },
  stateRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  stateDot: { width: 8, height: 8, borderRadius: 4 },
  stateLabel: { ...theme.typography.caption, textTransform: 'uppercase', letterSpacing: 0.8 },
  timer: { ...theme.typography.display, color: theme.colors.text, fontFamily: theme.typography.fontFamily.mono, fontSize: 44, lineHeight: 54, marginTop: 12 },
  timerCaption: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 4 },
  primaryActions: { flexDirection: 'row', width: '100%', marginTop: theme.spacing.xl },
  flexButton: { flex: 1, minHeight: 48 },
  breakRow: { flexDirection: 'row', width: '100%', gap: 8, marginTop: 10 },
  breakHint: { ...theme.typography.caption, color: theme.colors.textDim, textAlign: 'center', marginTop: 8 },
  stateButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surfaceAlt,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  stateButtonDisabled: { opacity: 0.4 },
  stateButtonText: { ...theme.typography.buttonSm, color: theme.colors.textMuted },
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  metric: {
    width: '48%',
    flexGrow: 1,
    minHeight: 92,
    padding: theme.spacing.md,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  metricValue: { ...theme.typography.h3, marginTop: 8 },
  metricLabel: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  progressCard: {
    padding: theme.spacing.base,
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  progressHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  progressValue: { ...theme.typography.h4, color: theme.colors.text },
  progressTarget: { ...theme.typography.caption, color: theme.colors.textMuted },
  progressTrack: { height: 10, borderRadius: 5, backgroundColor: theme.colors.bgMuted, overflow: 'hidden', marginTop: 14 },
  progressFill: { height: '100%', borderRadius: 5, backgroundColor: theme.colors.warning },
  progressHint: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 10 },
  ledger: {
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: 'hidden',
  },
  sessionRow: { flexDirection: 'row', alignItems: 'center', padding: theme.spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.border },
  sessionIcon: { width: 34, height: 34, borderRadius: theme.radii.md, alignItems: 'center', justifyContent: 'center' },
  sessionBody: { flex: 1, paddingHorizontal: 10 },
  sessionTitle: { ...theme.typography.body, color: theme.colors.text },
  sessionSub: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  sessionCoins: { ...theme.typography.monoSm, color: theme.colors.warning },
  pauseSessionLabel: { color: theme.colors.textDim },
  emptyLedger: { padding: theme.spacing.xl, alignItems: 'center' },
  emptyTitle: { ...theme.typography.h4, color: theme.colors.text, marginTop: 10 },
  emptyText: { ...theme.typography.body, color: theme.colors.textMuted, textAlign: 'center', marginTop: 6 },
});
