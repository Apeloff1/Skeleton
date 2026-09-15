/**
 * Pomodoro — Focus / Short break / Long break timer.
 * Persists completed sessions to userStore.
 */
import { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Animated, { useSharedValue, useAnimatedStyle, withTiming } from 'react-native-reanimated';
import { bumpStat, useUser } from '../utils/userStore';
import { jeevesSpeak } from '../features/Academy/jeevesTts';
import { openModalFromRoute } from '../utils/openModalFromRoute';
import theme from '../theme/tokens';
import { Screen, AppHeader } from '../components/ui';
import * as haptics from '../utils/haptics';
import { toast } from '../components/Toast';

const DURATIONS = { focus: 25 * 60, short: 5 * 60, long: 15 * 60 };
type Mode = 'focus' | 'short' | 'long';
interface PomodoroLog { id: string; mode: Mode; minutes: number; finishedAt: number; }
const HISTORY_KEY = '@codedock:pomodoro:history:v1';
const AUTOCYCLE_KEY = '@codedock:pomodoro:autocycle:v1';

export default function PomodoroScreen() {
  const router = useRouter();
  const user = useUser();
  const [mode, setMode] = useState<Mode>('focus');
  /** Hydrate the last-selected mode so users alternating between long-break
   *  Sundays and short-break weekdays don't have to re-pick each session. */
  const MODE_KEY = '@codedock/pomodoro:lastMode';
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(MODE_KEY);
        if (raw === 'focus' || raw === 'short' || raw === 'long') {
          setMode(raw);
          setSecondsLeft(DURATIONS[raw]);
        }
      } catch { /* swallow */ }
    })();
  }, []);
  /** Persist on every mode change. */
  useEffect(() => { AsyncStorage.setItem(MODE_KEY, mode).catch(() => {}); }, [mode]);
  const [secondsLeft, setSecondsLeft] = useState(DURATIONS.focus);
  const [running, setRunning] = useState(false);
  const [completedToday, setCompletedToday] = useState(0);
  const [history, setHistory] = useState<PomodoroLog[]>([]);
  const [autoCycle, setAutoCycle] = useState(false);
  const tickRef = useRef<any>(null);
  const startedAtRef = useRef<number>(0);
  const sessionsSinceLongBreakRef = useRef<number>(0);
  // Animated ring fill rotation — smoothly tracks `pct`. Reduce-Motion
  // collapses this to zero-duration jumps for accessibility.
  const ringRot = useSharedValue(-90);
  const ringStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${ringRot.value}deg` }] }));

  // Load persisted history + auto-cycle pref on mount.
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(HISTORY_KEY);
        if (raw) {
          const arr: PomodoroLog[] = JSON.parse(raw);
          setHistory(arr);
          const todayMs = new Date().setHours(0, 0, 0, 0);
          setCompletedToday(arr.filter(l => l.mode === 'focus' && l.finishedAt >= todayMs).length);
        }
      } catch {}
      try {
        const ac = await AsyncStorage.getItem(AUTOCYCLE_KEY);
        if (ac === '1') setAutoCycle(true);
      } catch {}
    })();
  }, []);

  const _persistHistory = async (next: PomodoroLog[]) => {
    setHistory(next);
    try { await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(next.slice(-200))); } catch {}
  };

  const _onSessionDone = async (m: Mode) => {
    const minutes = Math.round(DURATIONS[m] / 60);
    const log: PomodoroLog = { id: `p_${Date.now()}`, mode: m, minutes, finishedAt: Date.now() };
    const next = [...history, log];
    await _persistHistory(next);
    if (m === 'focus') {
      bumpStat('pomodoro_sessions', 1, 50);
      bumpStat('pomodoro_focus_minutes', minutes, 0);
      setCompletedToday(c => c + 1);
      sessionsSinceLongBreakRef.current += 1;
      // Jeeves cheer on completion
      try {
        jeevesSpeak(
          `Magnificent work! ${minutes} minutes of pure focus secured. ${sessionsSinceLongBreakRef.current >= 4 ? 'A long break is in order.' : 'Onward to the next round.'}`,
          { context: 'celebration', prependCatchphrase: true },
        );
      } catch {}
      if (autoCycle) {
        const nextMode: Mode = sessionsSinceLongBreakRef.current >= 4 ? 'long' : 'short';
        if (nextMode === 'long') sessionsSinceLongBreakRef.current = 0;
        setTimeout(() => {
          setMode(nextMode);
          setSecondsLeft(DURATIONS[nextMode]);
          setRunning(true);
        }, 1200);
      }
    } else {
      // Break ended — auto-resume focus if cycling
      try {
        jeevesSpeak('Break complete. Ready for the next focus session?', { context: 'transition', prependCatchphrase: false });
      } catch {}
      if (autoCycle) {
        setTimeout(() => {
          setMode('focus');
          setSecondsLeft(DURATIONS.focus);
          setRunning(true);
        }, 1200);
      }
    }
  };

  useEffect(() => {
    if (!running) return;
    tickRef.current = setInterval(() => {
      setSecondsLeft(prev => {
        if (prev <= 1) {
          clearInterval(tickRef.current);
          setRunning(false);
          _onSessionDone(mode);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(tickRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, mode]);

  const switchMode = (m: Mode) => {
    setMode(m);
    setSecondsLeft(DURATIONS[m]);
    setRunning(false);
  };

  const toggle = () => {
    if (!running && secondsLeft === 0) setSecondsLeft(DURATIONS[mode]);
    if (!running) startedAtRef.current = Date.now();
    setRunning(r => !r);
  };

  const reset = () => {
    setSecondsLeft(DURATIONS[mode]);
    setRunning(false);
  };

  const m = Math.floor(secondsLeft / 60);
  const s2 = secondsLeft % 60;
  const total = DURATIONS[mode];
  const pct = total > 0 ? (1 - secondsLeft / total) * 100 : 0;
  const color = mode === 'focus' ? '#8B5CF6' : mode === 'short' ? '#10B981' : '#3B82F6';

  // Smooth ring transition — clamps to 0 ms when Reduce-Motion is on.
  useEffect(() => {
    const target = -90 + (pct * 3.6);
    const dur = haptics.isReduceMotionOn() ? 0 : 600;
    ringRot.value = withTiming(target, { duration: dur });
  }, [pct, ringRot]);

  /** ± minute helper. Clamps so we never run below 0 or above 99 minutes. */
  const adjustMinutes = (delta: number) => {
    haptics.tap();
    setSecondsLeft(prev => {
      const next = Math.max(0, Math.min(99 * 60, prev + delta * 60));
      return next;
    });
    if (delta > 0) toast.info(`+${delta} min`);
    else           toast.info(`${delta} min`);
  };

  /** Long-press repeat-fire — holds ± for power users.
   *  Fires every 150 ms while the press is active; first tap is
   *  immediate via onPress, subsequent fires kick in after 400 ms hold. */
  const repeatRef = useRef<any>(null);
  const startRepeat = (delta: number) => {
    haptics.tap();
    let count = 0;
    repeatRef.current = setInterval(() => {
      setSecondsLeft(prev => Math.max(0, Math.min(99 * 60, prev + delta * 60)));
      count++;
      if (count % 5 === 0) haptics.tap(); // gentle reassurance every ~5 increments
    }, 150);
  };
  const stopRepeat = () => {
    if (repeatRef.current) { clearInterval(repeatRef.current); repeatRef.current = null; }
  };
  // Failsafe: clear repeat-fire interval if the component unmounts mid-hold.
  useEffect(() => () => stopRepeat(), []);

  // ── Rotating tip carousel ───────────────────────────────────
  // Cycles through 4 productivity tips every ~25 s (default focus length),
  // crossfaded so the screen always feels alive but never demands attention.
  // tipIdx is persisted so each session opens on a NEW tip rather than tip[0].
  const TIPS = [
    'Tip: after 4 focus sessions, take a long break. Streaks compound — most deep work happens after the 25th uninterrupted minute.',
    'Tip: hold the ± buttons to fast-adjust by minute. Useful when prepping a quick 5-min spike.',
    'Tip: skipping ahead with ⏩ logs the session as completed — perfect for closing out early when the work is genuinely done.',
    'Tip: enable Auto-cycle below to slip seamlessly between focus and break without touching the screen.',
  ];
  const TIP_KEY = '@codedock/pomodoro:lastTipIdx';
  const [tipIdx, setTipIdx] = useState(0);

  // Hydrate the persisted tip index on mount, then immediately ADVANCE to
  // the next tip so each fresh session leads with novel content. We also
  // re-save *that* incremented value so reload→reload always cycles.
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(TIP_KEY);
        const last = Math.max(0, Number(raw) || 0);
        const next = (last + 1) % TIPS.length;
        setTipIdx(next);
        await AsyncStorage.setItem(TIP_KEY, String(next));
      } catch { /* swallow */ }
    })();
  }, [TIPS.length]);

  // Continue cycling while the screen is open. Each tick also persists so a
  // long session naturally lands on a fresh tip even if the user reopens.
  useEffect(() => {
    const i = setInterval(() => {
      setTipIdx(prev => {
        const next = (prev + 1) % TIPS.length;
        AsyncStorage.setItem(TIP_KEY, String(next)).catch(() => {});
        return next;
      });
    }, 25_000);
    return () => clearInterval(i);
  }, [TIPS.length]);

  // Stop the repeat-fire interval on unmount too — failsafe for any
  // edge case where onPressOut never fires (e.g. modal interruption).
  useEffect(() => () => stopRepeat(), []);

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={[color + '22', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[{ position: 'absolute', top: 0, left: 0, right: 0, height: 280 }, { pointerEvents: 'none' }]}
      />
      <AppHeader title="Pomodoro" onBack={() => router.back()} />

      <ScrollView contentContainerStyle={st.body}>
        <View style={st.modeRow}>
          {(['focus', 'short', 'long'] as Mode[]).map(mm => (
            <TouchableOpacity
              key={mm}
              onPress={() => switchMode(mm)}
              style={[st.modeBtn, mode === mm && { backgroundColor: color + '22', borderColor: color }]}
            >
              <Text style={[st.modeBtnText, mode === mm && { color }]}>
                {mm === 'focus' ? 'Focus 25' : mm === 'short' ? 'Short 5' : 'Long 15'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={st.ringWrap}>
          <View style={[st.ringBg, { borderColor: color + '33' }]}>
            <Animated.View style={[st.ringFill, { borderColor: color }, ringStyle]} />
            <View style={st.ringInner}>
              <Text style={[st.time, { color }]}>{String(m).padStart(2, '0')}:{String(s2).padStart(2, '0')}</Text>
              <Text style={st.timeSub}>{mode.toUpperCase()}</Text>
            </View>
          </View>
        </View>

        <View style={st.controls}>
          <TouchableOpacity
            onPress={() => adjustMinutes(-1)}
            onLongPress={() => startRepeat(-1)}
            onPressOut={stopRepeat}
            delayLongPress={400}
            style={[st.circBtn, { borderColor: color + '55' }]}
            activeOpacity={0.7}
            accessibilityLabel="Subtract one minute · hold to repeat"
          >
            <Ionicons name="remove" size={20} color={color} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { haptics.tap(); reset(); }} style={st.iconBtn} activeOpacity={0.7} accessibilityLabel="Reset timer">
            <Ionicons name="refresh" size={20} color="#94A3B8" />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { haptics.impact(); toggle(); }} style={[st.playBtn, { backgroundColor: color }]} activeOpacity={0.7} accessibilityLabel={running ? 'Pause timer' : 'Start timer'}>
            <Ionicons name={running ? 'pause' : 'play'} size={28} color="#fff" />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { haptics.tap(); setSecondsLeft(Math.max(0, secondsLeft - 60)); toast.info('-1 min skipped'); }} style={st.iconBtn} activeOpacity={0.7} accessibilityLabel="Skip one minute">
            <Ionicons name="play-forward" size={20} color="#94A3B8" />
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => adjustMinutes(+1)}
            onLongPress={() => startRepeat(+1)}
            onPressOut={stopRepeat}
            delayLongPress={400}
            style={[st.circBtn, { borderColor: color + '55' }]}
            activeOpacity={0.7}
            accessibilityLabel="Add one minute · hold to repeat"
          >
            <Ionicons name="add" size={20} color={color} />
          </TouchableOpacity>
        </View>

        <View style={st.statRow}>
          <View style={st.statCard}>
            <Text style={st.statValue}>{completedToday}</Text>
            <Text style={st.statLabel}>Today</Text>
          </View>
          <View style={st.statCard}>
            <Text style={st.statValue}>{user.stats.pomodoro_sessions}</Text>
            <Text style={st.statLabel}>Sessions</Text>
          </View>
          <View style={st.statCard}>
            <Text style={st.statValue}>{Math.floor(user.stats.pomodoro_focus_minutes / 60)}h</Text>
            <Text style={st.statLabel}>Focus time</Text>
          </View>
        </View>

        <Text style={st.tip} key={tipIdx}>
          {TIPS[tipIdx]}
        </Text>

        {/* Auto-cycle toggle */}
        <View style={st.toggleRow}>
          <Ionicons name="repeat" size={16} color="#94A3B8" />
          <Text style={st.toggleLabel}>Auto-cycle focus ↔ break</Text>
          <Switch
            value={autoCycle}
            onValueChange={async (v) => {
              setAutoCycle(v);
              try { await AsyncStorage.setItem(AUTOCYCLE_KEY, v ? '1' : '0'); } catch {}
            }}
            trackColor={{ false: '#404040', true: color + 'AA' }}
            thumbColor={autoCycle ? color : '#94A3B8'}
          />
        </View>

        {/* Recent sessions strip */}
        {history.length > 0 && (
          <View style={st.historyBlock}>
            <View style={st.historyHead}>
              <Ionicons name="time-outline" size={14} color="#94A3B8" />
              <Text style={st.historyTitle}>Last sessions</Text>
              <Text style={st.historyCount}>{history.length} total</Text>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {history.slice(-12).reverse().map(l => (
                <View
                  key={l.id}
                  style={[
                    st.historyChip,
                    { borderColor: l.mode === 'focus' ? '#8B5CF6' : l.mode === 'short' ? '#10B981' : '#3B82F6' },
                  ]}
                >
                  <Text style={st.historyChipVal}>{l.minutes}m</Text>
                  <Text style={st.historyChipLabel}>{l.mode}</Text>
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* P3 modal launcher — full Gamification dashboard for streaks/XP */}
        <TouchableOpacity
          style={st.modalLauncher}
          onPress={() => openModalFromRoute(router, 'gamification')}
          activeOpacity={0.7}
        >
          <Ionicons name="game-controller" size={16} color="#A78BFA" />
          <Text style={st.modalLauncherText}>Open Gamification dashboard →</Text>
        </TouchableOpacity>
      </ScrollView>
    </Screen>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: theme.colors.bgElevated, borderBottomWidth: 1, borderBottomColor: theme.colors.border },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: theme.colors.text },
  body: { padding: 20, alignItems: 'center', paddingBottom: 60 },
  modeRow: { flexDirection: 'row', backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: 4, borderWidth: 1, borderColor: theme.colors.border, marginBottom: 40, gap: 4 },
  modeBtn: { paddingHorizontal: 18, paddingVertical: 10, borderRadius: theme.radii.md, borderWidth: 1, borderColor: 'transparent', marginHorizontal: 2 },
  modeBtnText: { color: theme.colors.textMuted, fontSize: 12, fontWeight: '700' },
  ringWrap: { marginVertical: 30 },
  ringBg: { width: 260, height: 260, borderRadius: 130, borderWidth: 14, justifyContent: 'center', alignItems: 'center', position: 'relative' },
  ringFill: { position: 'absolute', width: 260, height: 260, borderRadius: 130, borderWidth: 14, borderColor: 'transparent', borderTopColor: 'transparent', borderRightColor: 'transparent' },
  ringInner: { alignItems: 'center' },
  time: { fontSize: 76, fontWeight: '200', fontVariant: ['tabular-nums'], letterSpacing: 1 },
  timeSub: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 2, marginTop: 6 },
  controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 24, flexWrap: 'wrap' },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: theme.colors.surface, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: theme.colors.border },
  circBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: 'transparent', justifyContent: 'center', alignItems: 'center', borderWidth: 1 },
  playBtn: { width: 76, height: 76, borderRadius: 38, justifyContent: 'center', alignItems: 'center', marginHorizontal: 4, ...theme.elevation.lg },
  statRow: { flexDirection: 'row', gap: theme.spacing.sm, marginTop: 30, width: '100%' },
  statCard: { flex: 1, backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: theme.spacing.md, alignItems: 'center', borderWidth: 1, borderColor: theme.colors.border },
  statValue: { color: theme.colors.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.4 },
  statLabel: { color: theme.colors.textMuted, fontSize: 10, marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: '700' },
  tip: { color: theme.colors.textDim, fontSize: 11, fontStyle: 'italic', textAlign: 'center', marginTop: 20, paddingHorizontal: 20, lineHeight: 17 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 22, paddingHorizontal: 8, width: '100%' },
  toggleLabel: { color: theme.colors.text, fontSize: 13, fontWeight: '600', flex: 1 },
  historyBlock: { width: '100%', marginTop: 20, paddingHorizontal: 4 },
  historyHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  historyTitle: { color: theme.colors.text, fontSize: 12, fontWeight: '700', flex: 1 },
  historyCount: { color: theme.colors.textMuted, fontSize: 10, fontWeight: '700' },
  historyChip: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, marginRight: 6, alignItems: 'center', minWidth: 50, backgroundColor: theme.colors.surface },
  historyChipVal: { color: theme.colors.text, fontSize: 13, fontWeight: '800' },
  historyChipLabel: { color: theme.colors.textMuted, fontSize: 9, marginTop: 1, textTransform: 'uppercase', letterSpacing: 0.4, fontWeight: '700' },
  modalLauncher: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 24, paddingVertical: 12, paddingHorizontal: 16, borderRadius: 10, borderWidth: 1, borderColor: '#A78BFA55', backgroundColor: '#A78BFA15' },
  modalLauncherText: { color: '#A78BFA', fontSize: 12, fontWeight: '700' },
});
