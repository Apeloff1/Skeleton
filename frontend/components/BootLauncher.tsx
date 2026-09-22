/**
 * BootLauncher — local-first startup orchestrator.
 *
 * Phase 0 contains only the work required to make the app interactive.
 * Network/prewarm work continues in later phases and never blocks entry.
 */
import { NATIVE_DRIVER } from '../src/utils/platformStyles';
import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Platform,
  Animated,
  Easing,
  ScrollView,
  AccessibilityInfo,
} from 'react-native';


const requestIdleTask = (callback: () => void) => {
  const id = setTimeout(callback, 0);
  return { cancel: () => clearTimeout(id) };
};import { safeGetItem, safeSetItem } from '../utils/safeStorage';
import { traceStep, getMemoryTrace, clearCrashes } from '../utils/bootTracer';
import { STAGES, BootRunner, RunnerSnapshot, readBootCache, writeBootCache } from '../src/boot';
import api from '../src/utils/apiClient';
import { onMemoryPressure, getMemTier } from '../utils/memoryGuard';

const WELCOME_FLAG_KEY = '@codedock:welcome_seen:v1';
const WARM_BOOT_MAX_AGE_MS = 90_000;
const WARM_BOOT_MIN_SCORE = 95;
const BOOT_WATCHDOG_NORMAL_MS = 6_000;
const BOOT_WATCHDOG_LOW_MEM_MS = 4_500;

type CheckResult = {
  id: string;
  label: string;
  ok: boolean;
  ms: number;
  note?: string;
};

interface Props {
  onReady: () => void;
  onEscalate: (reason: string) => void;
}

const BOOT_T0 = Date.now();

function blog(message: string, data?: unknown) {
  const elapsed = Date.now() - BOOT_T0;
  try {
    if (data !== undefined) console.log(`[BootLauncher +${elapsed}ms] ${message}`, data);
    else console.log(`[BootLauncher +${elapsed}ms] ${message}`);
  } catch {}
}

function durable(step: string, data?: Record<string, unknown>) {
  blog(step, data);
  try { traceStep(`bl:${step}`, data).catch(() => {}); } catch {}
}

function DecorativeStarfall({ enabled }: { enabled: boolean }) {
  const [Component, setComponent] = React.useState<React.ComponentType<any> | null>(null);

  React.useEffect(() => {
    if (!enabled) return;
    const handle = requestIdleTask(() => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const module = require('../src/components/StarfallBackground');
        setComponent(() => module.StarfallBackground);
      } catch {
        blog('starfall_load_failed');
      }
    });
    return () => { try { (handle as any)?.cancel?.(); } catch {} };
  }, [enabled]);

  if (!enabled || !Component) return null;
  return <Component count={10} colorBase="#a78bfa" speedMs={[2400, 5200]} />;
}

function ProgressBar({ pct }: { pct: number }) {
  const value = React.useRef(new Animated.Value(0)).current;

  React.useEffect(() => {
    Animated.timing(value, {
      toValue: Math.max(0, Math.min(1, pct / 100)),
      duration: 280,
      easing: Easing.out(Easing.quad),
      useNativeDriver: false,
    }).start();
  }, [pct, value]);

  return (
    <View style={styles.barOuter}>
      <Animated.View
        style={[
          styles.barInner,
          { width: value.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }) },
        ]}
      />
    </View>
  );
}

export default function BootLauncher({ onReady, onEscalate }: Props) {
  const [progress, setProgress] = React.useState(0);
  const [phase1Pct, setPhase1Pct] = React.useState(0);
  const [activeLabel, setActiveLabel] = React.useState('Starting up…');
  const [results, setResults] = React.useState<CheckResult[]>([]);
  const [phase, setPhase] = React.useState<'running' | 'ready' | 'failed'>('running');
  const [welcomeSeen, setWelcomeSeen] = React.useState<boolean | null>(null);
  const [showDiag, setShowDiag] = React.useState(false);
  const [, setLongPressCount] = React.useState(0);
  const [reduceMotion, setReduceMotion] = React.useState(false);
  const [retryKey, setRetryKey] = React.useState(0);
  const [failedStages, setFailedStages] = React.useState<CheckResult[]>([]);
  const [warmBoot, setWarmBoot] = React.useState(false);

  const runnerRef = React.useRef<BootRunner | null>(null);
  const stageStatusRef = React.useRef<Record<string, string>>({});
  const phaseLockedRef = React.useRef(false);
  const phase0DoneRef = React.useRef(false);
  const shedRef = React.useRef(false);
  const memTier = React.useRef(getMemTier()).current;
  const fadeIn = React.useRef(new Animated.Value(0)).current;

  const commitPhase = React.useCallback((next: 'running' | 'ready' | 'failed') => {
    if (phaseLockedRef.current) {
      blog(`commitPhase(${next}) ignored`);
      return;
    }
    if (next === 'ready' || next === 'failed') phaseLockedRef.current = true;
    durable(`commit_phase_${next}`);
    setPhase(next);
  }, []);

  React.useEffect(() => {
    durable('mount');
    safeGetItem(WELCOME_FLAG_KEY, null, 400).then(value => {
      durable(`welcome_flag_${!!value}`);
      setWelcomeSeen(!!value);
    });
    return () => { durable('unmount'); };
  }, []);

  React.useEffect(() => {
    let mounted = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then(value => { if (mounted) setReduceMotion(!!value); })
      .catch(() => {});
    const subscription = AccessibilityInfo.addEventListener?.(
      'reduceMotionChanged',
      (value: boolean) => { if (mounted) setReduceMotion(!!value); },
    );
    return () => {
      mounted = false;
      try { (subscription as any)?.remove?.(); } catch {}
    };
  }, []);

  React.useEffect(() => {
    Animated.timing(fadeIn, {
      toValue: 1,
      duration: reduceMotion ? 0 : 380,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: NATIVE_DRIVER,
    }).start();
  }, [fadeIn, reduceMotion]);

  React.useEffect(() => {
    const mountedAt = Date.now();
    const minimumVisibleMs = reduceMotion ? 200 : (memTier === 'low' ? 400 : 800);
    let cancelled = false;

    phase0DoneRef.current = false;
    shedRef.current = false;
    stageStatusRef.current = {};

    if (memTier === 'low') {
      durable('boot_low_tier_preclean');
      try {
        import('../utils/selfCleaner')
          .then(module => module.runSelfCleaner('boot_low_tier'))
          .catch(() => {});
      } catch {}
    }

    const offMemoryPressure = onMemoryPressure(() => {
      if (cancelled) return;
      shedRef.current = true;
      durable('boot_mem_pressure_shed', { phase0: phase0DoneRef.current });
      if (phase0DoneRef.current && !phaseLockedRef.current) {
        clearCrashes().catch(() => {});
        commitPhase('ready');
      }
    });

    void (async () => {
      try {
        const cache = await readBootCache();
        const age = cache ? Date.now() - cache.ts : -1;
        durable('warm_cache_read', {
          hit: !!cache,
          score: cache?.score,
          runtimeOk: cache?.runtimeOk ?? cache?.backendOk,
          age,
        });
        if (
          cache &&
          (cache.runtimeOk ?? cache.backendOk ?? false) &&
          cache.score >= WARM_BOOT_MIN_SCORE &&
          age >= 0 &&
          age < WARM_BOOT_MAX_AGE_MS
        ) {
          if (cancelled) return;
          setWarmBoot(true);
          setProgress(100);
          setActiveLabel('Resuming session');
          commitPhase('ready');
          clearCrashes().catch(() => {});
          await traceStep(`bootlauncher_warm_score${cache.score}_age${age}ms`);
        }
      } catch {}
    })();

    const runner = new BootRunner(STAGES);
    runnerRef.current = runner;
    void runner.run();

    const unsubscribe = runner.on((snapshot: RunnerSnapshot) => {
      if (cancelled) return;

      // The primary progress bar represents only work that blocks entry.
      // Once phase 0 is terminal and its critical stages are healthy, the
      // local-start contract is complete regardless of network state.
      const localProgress = snapshot.phaseDone[0] && snapshot.criticalOk
        ? 100
        : Math.min(100, Math.round(snapshot.phaseProgress[0] || 0));
      setProgress(localProgress);

      // Background prep represents completion, not only successful weight.
      // A soft-failed optional stage must not leave this chip stuck forever.
      setPhase1Pct(
        snapshot.phaseDone[1]
          ? 100
          : Math.min(100, Math.round(snapshot.phaseProgress[1] || 0)),
      );

      const localRunning = Object.values(snapshot.stages)
        .filter(stage => stage.status === 'running' && stage.phase === 0);
      if (localRunning.length) setActiveLabel(localRunning[localRunning.length - 1].label);

      blog(
        `snapshot local=${localProgress} score=${Math.round(snapshot.bootScore)} ` +
        `criticalOk=${snapshot.criticalOk} ok=${snapshot.counts.ok}/${snapshot.counts.total}`,
      );

      Object.values(snapshot.stages).forEach(stage => {
        const previous = stageStatusRef.current[stage.id];
        const terminal = ['ok', 'failed', 'timed_out', 'skipped'].includes(stage.status);
        if (previous !== stage.status && terminal) {
          durable(`stage_${stage.id}_${stage.status}`, {
            ms: stage.durationMs,
            err: stage.error,
          });
        }
        stageStatusRef.current[stage.id] = stage.status;
      });

      const completed: CheckResult[] = Object.values(snapshot.stages)
        .filter(stage => stage.status !== 'pending' && stage.status !== 'running')
        .map(stage => ({
          id: stage.id,
          label: stage.label,
          ok: stage.status === 'ok',
          ms: stage.durationMs || 0,
          note: stage.error || (stage.status !== 'ok' ? stage.status : undefined),
        }));
      setResults(completed);
      setFailedStages(completed.filter(result => !result.ok));
    });

    void (async () => {
      try {
        durable('boot_start');
        await runner.waitForPhase(0);
        const localSnapshot = runner.snapshot();
        phase0DoneRef.current = true;
        setProgress(localSnapshot.criticalOk ? 100 : Math.round(localSnapshot.phaseProgress[0] || 0));
        durable('phase0_done', {
          phase0: localSnapshot.phaseProgress[0],
          score: localSnapshot.bootScore,
          criticalOk: localSnapshot.criticalOk,
          elapsed: localSnapshot.elapsedMs,
        });

        if (!localSnapshot.criticalOk) {
          if (cancelled) return;
          commitPhase('failed');
          await traceStep('bootlauncher_critical_fail');
          try {
            api.post('/api/telemetry/boot', {
              boot_score: localSnapshot.bootScore,
              counts: localSnapshot.counts,
              elapsed_ms: localSnapshot.elapsedMs,
              stages: localSnapshot.stages,
              ok: false,
            }, { timeoutMs: 3000, retries: 0 }).catch(() => {});
          } catch {}
          return;
        }

        // Do not overwrite a previously healthy warm cache with a local-only
        // snapshot. Whole-application runtime health is not known until phase 1.
        const elapsed = Date.now() - mountedAt;
        if (elapsed < minimumVisibleMs) {
          await new Promise(resolve => setTimeout(resolve, minimumVisibleMs - elapsed));
        }
        if (cancelled) return;

        commitPhase('ready');
        clearCrashes().catch(() => {});
        await traceStep(
          `bootlauncher_ready_phase0_${Math.round(localSnapshot.phaseProgress[0] || 0)}_${localSnapshot.elapsedMs}ms`,
        );

        if (shedRef.current) {
          durable('boot_shed_background_phases');
          try { runner.cancel(); } catch {}
          return;
        }

        runner.waitForPhase(2).then(finalSnapshot => {
          const runtimeOk = finalSnapshot.stages.app_runtime?.status === 'ok';
          writeBootCache({
            ts: Date.now(),
            score: finalSnapshot.bootScore,
            runtimeOk,
            backendOk: runtimeOk,
          }).catch(() => {});
          try {
            api.post('/api/telemetry/boot', {
              boot_score: finalSnapshot.bootScore,
              counts: finalSnapshot.counts,
              elapsed_ms: finalSnapshot.elapsedMs,
              stages: finalSnapshot.stages,
              ok: finalSnapshot.ok,
              runtime_ok: runtimeOk,
            }, { timeoutMs: 3000, retries: 0 }).catch(() => {});
          } catch {}
        }).catch(() => {});
      } catch (error: any) {
        await traceStep(`bootlauncher_exception_${String(error?.message || error).slice(0, 60)}`);
        if (!cancelled) commitPhase('failed');
      }
    })();

    const watchdogMs = memTier === 'low' ? BOOT_WATCHDOG_LOW_MEM_MS : BOOT_WATCHDOG_NORMAL_MS;
    durable('watchdog_scheduled', { ms: watchdogMs, tier: memTier });
    const watchdog = setTimeout(() => {
      if (cancelled || phaseLockedRef.current) return;
      durable('watchdog_fired_force_ready');
      clearCrashes().catch(() => {});
      commitPhase('ready');
    }, watchdogMs);

    return () => {
      cancelled = true;
      clearTimeout(watchdog);
      unsubscribe();
      try { offMemoryPressure(); } catch {}
      try { runner.cancel(); } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryKey, reduceMotion]);

  React.useEffect(() => {
    if (phase !== 'ready' || welcomeSeen === null || !welcomeSeen) return;
    const timer = setTimeout(() => {
      durable('auto_advance_onReady');
      onReady();
    }, 350);
    return () => clearTimeout(timer);
  }, [phase, welcomeSeen, onReady]);

  const handleEnterPress = React.useCallback(async () => {
    durable('user_enter_product_press');
    try { await safeSetItem(WELCOME_FLAG_KEY, '1'); } catch {}
    onReady();
  }, [onReady]);

  const handleLogoLongPress = React.useCallback(() => {
    setLongPressCount(count => {
      const next = count + 1;
      if (next >= 2) setShowDiag(true);
      return next;
    });
  }, []);

  const handleRetryBoot = React.useCallback(async () => {
    durable('user_retry');
    try { await safeSetItem('@boot/crash_count', '0'); } catch {}
    await traceStep('bootlauncher_user_retry');
    setProgress(0);
    setPhase1Pct(0);
    setActiveLabel('Starting up…');
    setResults([]);
    setFailedStages([]);
    setWarmBoot(false);
    phaseLockedRef.current = false;
    setPhase('running');
    setRetryKey(key => key + 1);
  }, []);

  return (
    <View style={styles.fill}>
      <View style={[styles.bg, { pointerEvents: 'none' }]}>
        <DecorativeStarfall enabled={!reduceMotion && memTier !== 'low'} />
      </View>

      <Animated.View style={[styles.center, { opacity: fadeIn, pointerEvents: 'box-none' }]}>
        <TouchableOpacity onLongPress={handleLogoLongPress} delayLongPress={500} activeOpacity={1}>
          <View style={styles.logoBubble}>
            <Text style={styles.logoGlyph}>{'</>'}</Text>
          </View>
        </TouchableOpacity>

        <Text style={styles.title}>CodeDock</Text>
        <Text style={styles.tagline}>Quantum Nexus</Text>

        {phase === 'running' && (
          <>
            <Text style={styles.subtitle}>{activeLabel}…</Text>
            <ProgressBar pct={progress} />
            <Text style={styles.pctLabel}>{progress}%</Text>
          </>
        )}

        {phase === 'ready' && welcomeSeen === false && (
          <>
            <Text style={styles.subtitle}>
              Hyperscale game-build factory · 600K+ knowledge assets · live RAG
            </Text>
            <TouchableOpacity style={styles.primaryBtn} onPress={handleEnterPress} activeOpacity={0.85}>
              <Text style={styles.primaryBtnText}>Enter Product</Text>
            </TouchableOpacity>
          </>
        )}

        {phase === 'ready' && welcomeSeen === true && (
          <>
            <ProgressBar pct={100} />
            <Text style={styles.pctLabel}>
              {warmBoot ? 'Resuming — launching…' : 'Ready — launching…'}
            </Text>
          </>
        )}

        {phase === 'failed' && (
          <>
            <Text style={[styles.subtitle, { color: '#fbbf24' }]}>
              We hit a snag while preparing the app.
            </Text>
            {failedStages.length > 0 && (
              <View style={styles.failList}>
                {failedStages.slice(0, 4).map(failure => (
                  <Text key={failure.id} style={styles.failRow}>
                    ✗ {failure.label}{failure.note ? ` — ${failure.note}` : ''}
                  </Text>
                ))}
              </View>
            )}
            <TouchableOpacity style={styles.primaryBtn} onPress={handleRetryBoot} activeOpacity={0.85}>
              <Text style={styles.primaryBtnText}>Retry boot</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryBtn, { marginTop: 10 }]}
              onPress={() => onEscalate('bootlauncher_user_continue')}
              activeOpacity={0.85}
            >
              <Text style={styles.secondaryBtnText}>Continue anyway</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryBtn, { marginTop: 10 }]}
              onPress={() => onEscalate('bootlauncher_user_safe_mode')}
              activeOpacity={0.85}
            >
              <Text style={styles.secondaryBtnText}>Open Safe Mode</Text>
            </TouchableOpacity>
          </>
        )}

        {phase === 'ready' && phase1Pct < 100 && (
          <View style={styles.phase1Chip}>
            <View style={styles.phase1Dot} />
            <Text style={styles.phase1Text}>Background prep · {phase1Pct}%</Text>
          </View>
        )}
      </Animated.View>

      {showDiag && (
        <View style={styles.diagSheet}>
          <Text style={styles.diagTitle}>Boot diagnostics</Text>
          <ScrollView style={styles.diagScroll}>
            {results.map(result => (
              <Text key={result.id} style={styles.diagRow}>
                {result.ok ? '✓' : '✗'} {result.label} ({result.ms}ms)
                {result.note ? ` — ${result.note}` : ''}
              </Text>
            ))}
            <Text style={[styles.diagRow, styles.traceHeading]}>Last trace:</Text>
            {getMemoryTrace().slice(-10).map((trace, index) => (
              <Text key={`${trace.ts}-${index}`} style={[styles.diagRow, styles.traceRow]}>
                {new Date(trace.ts).toISOString().slice(11, 19)} {trace.step}
              </Text>
            ))}
          </ScrollView>
          <TouchableOpacity onPress={() => setShowDiag(false)} style={[styles.secondaryBtn, { marginTop: 10 }]}>
            <Text style={styles.secondaryBtnText}>Close</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#0a0a14' },
  bg: { ...StyleSheet.absoluteFillObject },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 28,
  },
  logoBubble: {
    width: 84,
    height: 84,
    borderRadius: 22,
    backgroundColor: '#1f1733',
    borderColor: '#7c3aed55',
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
    ...(Platform.OS === 'ios'
      ? { shadowColor: '#7c3aed', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.5, shadowRadius: 14 }
      : { elevation: 6 }),
  },
  logoGlyph: { color: '#a78bfa', fontSize: 30, fontWeight: '900' },
  title: { color: '#fff', fontSize: 38, fontWeight: '900', letterSpacing: -1, textAlign: 'center' },
  tagline: {
    color: '#a78bfa',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 4,
    textTransform: 'uppercase',
    marginTop: 6,
    marginBottom: 28,
    textAlign: 'center',
  },
  subtitle: {
    color: '#d1d5db',
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 20,
    maxWidth: 320,
    marginBottom: 20,
  },
  barOuter: {
    width: 260,
    height: 8,
    backgroundColor: '#1f1733',
    borderRadius: 99,
    overflow: 'hidden',
    marginTop: 6,
  },
  barInner: { height: '100%', backgroundColor: '#a78bfa', borderRadius: 99 },
  pctLabel: { color: '#9ca3af', fontSize: 12, marginTop: 12, marginBottom: 20, fontWeight: '600' },
  primaryBtn: {
    backgroundColor: '#7c3aed',
    paddingHorizontal: 32,
    paddingVertical: 16,
    borderRadius: 999,
    alignItems: 'center',
    minHeight: 52,
    justifyContent: 'center',
    marginTop: 6,
  },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '800', letterSpacing: 0.5 },
  secondaryBtn: {
    borderColor: '#a78bfa55',
    borderWidth: 1,
    paddingHorizontal: 24,
    paddingVertical: 13,
    borderRadius: 999,
    alignItems: 'center',
    minHeight: 46,
    justifyContent: 'center',
  },
  secondaryBtnText: { color: '#a78bfa', fontSize: 13, fontWeight: '700' },
  diagSheet: {
    position: 'absolute',
    left: 12,
    right: 12,
    bottom: 24,
    backgroundColor: '#1c1330ee',
    borderRadius: 16,
    padding: 16,
    borderColor: '#7c3aed44',
    borderWidth: 1,
  },
  diagTitle: { color: '#fff', fontWeight: '800', fontSize: 14, marginBottom: 10 },
  diagScroll: { maxHeight: 260 },
  diagRow: {
    color: '#cbd5e1',
    fontSize: 11,
    marginVertical: 2,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  traceHeading: { marginTop: 10, opacity: 0.7 },
  traceRow: { opacity: 0.8 },
  failList: {
    alignSelf: 'stretch',
    marginHorizontal: 16,
    marginBottom: 18,
    paddingVertical: 10,
    paddingHorizontal: 14,
    backgroundColor: '#1c1330aa',
    borderColor: '#fbbf2433',
    borderWidth: 1,
    borderRadius: 12,
  },
  failRow: { color: '#fde68a', fontSize: 12, marginVertical: 2 },
  phase1Chip: {
    position: 'absolute',
    bottom: 28,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#1c1330cc',
    borderRadius: 999,
    borderColor: '#7c3aed33',
    borderWidth: 1,
  },
  phase1Dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#a78bfa',
    marginRight: 8,
  },
  phase1Text: { color: '#cbd5e1', fontSize: 11, fontWeight: '700' },
});
