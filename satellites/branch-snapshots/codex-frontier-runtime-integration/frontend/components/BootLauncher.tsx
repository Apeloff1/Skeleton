/**
 * BootLauncher — First-boot orchestrator with progress bar + readiness checks.
 *
 * Design goals (Feb 2026):
 *   1. SOLIDIFY launch — every step has a hard timeout and a graceful fallback.
 *      The user always reaches an interactive state, no matter what fails.
 *   2. NON-BLOCKING visuals — Starfall plays as pure decoration; animations
 *      are deferred via InteractionManager so they NEVER compete with React
 *      mount work for JS-thread time.
 *   3. HONEST progress — the progress bar reflects ACTUAL readiness checks
 *      (storage, bootGuard, backend, hub-preload), not a fake timer. Users
 *      see what's happening; if a step stalls, the UI says so.
 *   4. AUTO-ADVANCE — once all checks pass, navigate to /hub. Returning
 *      users (welcome_seen flag set) skip the welcome copy entirely.
 *   5. DIAGNOSTICS — long-press the logo on any boot screen to see the last
 *      10 trace steps for crash investigation.
 *
 * Public API: <BootLauncher onReady={() => void} onEscalate={(why: string) => void} />
 *
 * - onReady is called when ALL checks succeed and the user is ready to enter.
 *   The parent typically routes to /hub at this point.
 * - onEscalate is called when a check hard-fails or the user explicitly
 *   requests safe mode. The parent should swap to a simpler layer.
 */
import { NATIVE_DRIVER } from '../src/utils/platformStyles';
import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Platform,
  InteractionManager, Animated, Easing, ScrollView, AccessibilityInfo,
} from 'react-native';
import { safeGetItem, safeSetItem } from '../utils/safeStorage';
import { traceStep, getMemoryTrace, clearCrashes } from '../utils/bootTracer';
import { STAGES, BootRunner, RunnerSnapshot, readBootCache, writeBootCache } from '../src/boot';
import api from '../src/utils/apiClient';
import { onMemoryPressure, getMemTier } from '../utils/memoryGuard';

const WELCOME_FLAG_KEY = '@codedock:welcome_seen:v1';
const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// ─────────────────────────────────────────────────────────────────────
//  Exhaustive boot logging (2026-06)
//  --------------------------------------------------------------------
//  `blog()` logs to the JS console ALWAYS (visible in `adb logcat` /
//  Metro / Flipper) with a high-visibility tag + monotonic timestamp, so
//  even a hard native close on a physical device leaves a breadcrumb in
//  logcat right up to the last frame before the crash.
//
//  `bdurable()` ALSO persists the step to AsyncStorage via traceStep so
//  it survives a process kill and shows up on the in-app boot-log screen.
//  Use bdurable() only for milestones (not per-frame ticks) to avoid
//  thrashing AsyncStorage.
// ─────────────────────────────────────────────────────────────────────
const _BOOT_T0 = Date.now();
function blog(msg: string, data?: any) {
  const dt = Date.now() - _BOOT_T0;
  try {
    if (data !== undefined) {
      console.log(`[BootLauncher +${dt}ms] ${msg}`, data);
    } else {
      console.log(`[BootLauncher +${dt}ms] ${msg}`);
    }
  } catch {}
}
function bdurable(step: string, data?: any) {
  blog(step, data);
  try { traceStep(`bl:${step}`, data).catch(() => {}); } catch {}
}
/**
 * Warm-boot fast path: if the previous successful boot happened within
 * this window, skip the full check battery and go straight to "Ready".
 * Tuned conservatively — long enough to feel instant on rapid app
 * switches, short enough that a stale backend/auth state still gets
 * caught on the next boot.
 */
const WARM_BOOT_MAX_AGE_MS = 90_000;       // 90 seconds
const WARM_BOOT_MIN_SCORE  = 95;           // require near-perfect previous score

/** Each check returns true if it succeeded. False = soft fail (continue). */
type CheckResult = { id: string; label: string; ok: boolean; ms: number; note?: string };
type CheckFn = () => Promise<{ ok: boolean; note?: string }>;

interface BootCheck { id: string; label: string; weight: number; fn: CheckFn; timeoutMs: number; critical?: boolean }

// ─────────────────────────────────────────────────────────────────────
//  Lightweight, lazy-loaded Starfall — runs ONLY after the UI mounts.
//  Respects user's Reduce Motion preference (skips Starfall entirely).
// ─────────────────────────────────────────────────────────────────────
function DecorativeStarfall({ enabled }: { enabled: boolean }) {
  const [mounted, setMounted] = React.useState(false);
  const [Comp, setComp] = React.useState<any>(null);

  React.useEffect(() => {
    if (!enabled) { blog('starfall skipped (reduce-motion)'); return; }
    // Defer ALL starfall work until after the launcher has painted.
    const handle = InteractionManager.runAfterInteractions(() => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const mod = require('../src/components/StarfallBackground');
        setComp(() => mod.StarfallBackground);
        setMounted(true);
        blog('starfall mounted');
      } catch {
        blog('starfall load failed (decorative — ignored)');
      }
    });
    return () => { try { (handle as any)?.cancel?.(); } catch {} };
  }, [enabled]);

  if (!enabled || !mounted || !Comp) return null;
  // Reduced streak count to 10 (was 18) — purely decorative, low cost.
  return <Comp count={10} colorBase="#a78bfa" speedMs={[2400, 5200]} />;
}

// ─────────────────────────────────────────────────────────────────────
//  Animated progress bar (native-driver scaleX, single frame budget)
// ─────────────────────────────────────────────────────────────────────
function ProgressBar({ pct }: { pct: number }) {
  const w = React.useRef(new Animated.Value(0)).current;
  React.useEffect(() => {
    Animated.timing(w, {
      toValue: Math.max(0, Math.min(1, pct / 100)),
      duration: 280,
      easing: Easing.out(Easing.quad),
      useNativeDriver: false, // width interpolation can't use native driver
    }).start();
  }, [pct, w]);

  return (
    <View style={styles.barOuter}>
      <Animated.View
        style={[
          styles.barInner,
          { width: w.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }) },
        ]}
      />
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────
//  Boot checks — each one has a hard timeout and is best-effort.
// ─────────────────────────────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function timeoutWrap<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise(resolve => {
    let done = false;
    const t = setTimeout(() => { if (!done) { done = true; resolve(fallback); } }, ms);
    p.then(v => { if (!done) { done = true; clearTimeout(t); resolve(v); } })
     .catch(() => { if (!done) { done = true; clearTimeout(t); resolve(fallback); } });
  });
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const CHECKS: BootCheck[] = [
  {
    id: 'storage',
    label: 'Local storage',
    weight: 20,
    timeoutMs: 900,
    fn: async () => {
      // Read-back round-trip on a throwaway key.
      const probe = `__boot_probe_${Date.now() % 1e6}`;
      await safeSetItem(probe, '1', 600);
      const v = await safeGetItem(probe, null, 600);
      return { ok: v === '1', note: v === '1' ? undefined : 'read-back failed' };
    },
  },
  {
    id: 'crash_guard',
    label: 'Crash-loop guard',
    weight: 10,
    timeoutMs: 700,
    fn: async () => {
      const raw = await safeGetItem('@boot/crash_count', '0', 500);
      const n = parseInt(raw || '0', 10) || 0;
      return { ok: n < 3, note: n >= 3 ? `count=${n}` : undefined };
    },
  },
  {
    id: 'backend',
    label: 'Backend connection',
    weight: 30,
    timeoutMs: 2500,
    fn: async () => {
      if (!BACKEND) return { ok: false, note: 'no URL' };
      try {
        const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        const t = setTimeout(() => { try { ctrl?.abort(); } catch {} }, 2300);
        const res = await fetch(`${BACKEND}/api/health`, { signal: ctrl?.signal as any });
        clearTimeout(t);
        return { ok: res.ok, note: res.ok ? undefined : `HTTP ${res.status}` };
      } catch (e: any) {
        return { ok: false, note: e?.message?.slice(0, 32) || 'fetch failed' };
      }
    },
  },
  {
    id: 'preload_hub',
    label: 'Workspace assets',
    weight: 25,
    timeoutMs: 1500,
    fn: async () => {
      // Touch a cheap manifest endpoint so the hub feels instant on click.
      if (!BACKEND) return { ok: true }; // no backend = skip
      try {
        const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        const t = setTimeout(() => { try { ctrl?.abort(); } catch {} }, 1300);
        const res = await fetch(`${BACKEND}/api/languages`, { signal: ctrl?.signal as any });
        clearTimeout(t);
        return { ok: res.ok, note: res.ok ? undefined : `HTTP ${res.status}` };
      } catch {
        // Non-critical — skipping preload doesn't block boot.
        return { ok: true, note: 'skipped' };
      }
    },
  },
  {
    id: 'finalize',
    label: 'Finalizing',
    weight: 15,
    timeoutMs: 400,
    fn: async () => {
      await new Promise(r => setTimeout(r, 250)); // visual breather
      return { ok: true };
    },
  },
];

// ─────────────────────────────────────────────────────────────────────
//  Main component
// ─────────────────────────────────────────────────────────────────────
interface Props {
  onReady: () => void;
  onEscalate: (reason: string) => void;
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
  const [retryKey, setRetryKey] = React.useState(0);          // bump to remount boot effect
  const [failedStages, setFailedStages] = React.useState<CheckResult[]>([]);
  const [warmBoot, setWarmBoot] = React.useState(false);
  const runnerRef = React.useRef<BootRunner | null>(null);
  // Tracks last-seen status per stage so we only DURABLY log transitions.
  const stageStatusRef = React.useRef<Record<string, string>>({});
  // Single-shot guard so the warm-boot fast path AND the cold-boot
  // completion path can never both set phase='ready' (which used to be
  // a benign re-render but, with the new failure UI + retryKey, could
  // briefly flicker stages back on screen).
  const phaseLockedRef = React.useRef(false);
  // OOM guardrails: track primary readiness, whether we've been asked to shed
  // non-critical boot work, and the device RAM tier (drives up-front caps).
  const phase0DoneRef = React.useRef(false);
  const shedRef = React.useRef(false);
  const memTier = React.useRef(getMemTier()).current;

  const fadeIn = React.useRef(new Animated.Value(0)).current;

  // Safe phase setter — first writer wins for 'ready'/'failed', so once
  // the launcher commits to an outcome it cannot be flipped back to
  // 'running'.
  const commitPhase = React.useCallback((p: 'running' | 'ready' | 'failed') => {
    if (phaseLockedRef.current) {
      blog(`commitPhase(${p}) IGNORED — already locked`);
      return;
    }
    if (p === 'ready' || p === 'failed') phaseLockedRef.current = true;
    bdurable(`commit_phase_${p}`);
    setPhase(p);
  }, []);

  // Read welcome flag (parallel with checks, doesn't block boot)
  React.useEffect(() => {
    bdurable('mount');
    safeGetItem(WELCOME_FLAG_KEY, null, 400).then(v => {
      bdurable(`welcome_flag_${!!v}`);
      setWelcomeSeen(!!v);
    });
    return () => { bdurable('unmount'); };
  }, []);

  // Detect Reduce Motion preference (accessibility + low-end devices).
  React.useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const rm = await AccessibilityInfo.isReduceMotionEnabled();
        if (mounted) { bdurable(`reduce_motion_${!!rm}`); setReduceMotion(!!rm); }
      } catch { /* not all platforms */ }
    })();
    const sub = AccessibilityInfo.addEventListener?.(
      'reduceMotionChanged',
      (v: boolean) => { if (mounted) setReduceMotion(!!v); },
    );
    return () => {
      mounted = false;
      try { (sub as any)?.remove?.(); } catch {}
    };
  }, []);

  // Fade in the launcher chrome once mounted.
  React.useEffect(() => {
    Animated.timing(fadeIn, {
      toValue: 1,
      duration: reduceMotion ? 0 : 380,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: NATIVE_DRIVER,
    }).start();
  }, [fadeIn, reduceMotion]);

  // SOTA boot — parallel DAG runner over the declarative STAGES.
  // Each stage emits live progress via the runner's pub/sub, so the
  // progress bar reflects ACTUAL parallel work, not a fake serial timer.
  //
  // 2026-05 upgrades:
  //   • Warm-boot fast path: if previous boot was healthy < 90s ago,
  //     skip the full check battery (the cache implies the world is ok).
  //   • Cancellation on unmount: aborts in-flight stages via the runner's
  //     internal AbortController.
  //   • Tracks `failedStages` separately so the failure UI can list them.
  //   • `retryKey` is a dependency — bumping it restarts the whole boot.
  React.useEffect(() => {
    const mountTs = Date.now();
    const MIN_VISIBLE_MS = reduceMotion ? 200 : (memTier === 'low' ? 400 : 800);
    let cancelled = false;

    // ── OOM guardrail (boot) ───────────────────────────────────────
    // On a low-RAM device, proactively free disk/cache BEFORE the heavy boot
    // stages run so the JS-thread eval spikes have more headroom.
    if (memTier === 'low') {
      bdurable('boot_low_tier_preclean');
      try { import('../utils/selfCleaner').then(m => m.runSelfCleaner('boot_low_tier')).catch(() => {}); } catch {}
    }
    // Subscribe to OS memory-pressure for the duration of boot. If pressure
    // hits while we're still cranking through stages, SHED all non-critical
    // background work; and if primary readiness is already done, get the user
    // into the (offline-capable) Hub immediately rather than risk a hard OOM.
    const offMem = onMemoryPressure(() => {
      if (cancelled) return;
      shedRef.current = true;
      bdurable('boot_mem_pressure_shed', { phase0: phase0DoneRef.current });
      if (phase0DoneRef.current && !phaseLockedRef.current) {
        clearCrashes().catch(() => {});
        commitPhase('ready');
      }
    });

    // ── Warm-boot fast path ────────────────────────────────────────
    (async () => {
      try {
        const cache = await readBootCache();
        const age = cache ? Date.now() - cache.ts : -1;
        bdurable('warm_cache_read', { hit: !!cache, score: cache?.score, backendOk: cache?.backendOk, age });
        if (
          cache &&
          cache.backendOk &&
          cache.score >= WARM_BOOT_MIN_SCORE &&
          (Date.now() - cache.ts) < WARM_BOOT_MAX_AGE_MS
        ) {
          if (cancelled) return;
          bdurable('warm_boot_fastpath');
          setWarmBoot(true);
          setProgress(100);
          setActiveLabel('Resuming session');
          commitPhase('ready');
          // BOOT-LOOP FIX: clear the crash counter the moment boot
          // orchestration succeeds — do NOT wait for the Hub to finish
          // loading data (a cold-start/unreachable backend must never trip
          // safe-mode once we've successfully reached 'ready').
          clearCrashes().catch(() => {});
          await traceStep(`bootlauncher_warm_score${cache.score}_age${Date.now() - cache.ts}ms`);
          // Still kick the full runner in the BACKGROUND so phase-1 work
          // (feature-flag refresh etc.) happens; user just doesn't wait.
        }
      } catch { /* fall through to cold boot */ }
    })();

    const runner = new BootRunner(STAGES);
    runnerRef.current = runner;

    // Kick off the parallel DAG IMMEDIATELY, before subscribing or awaiting
    // any phase. `waitForPhase()` reads `resolvedTasks`, which is only
    // populated by `run()`; calling run() first removes a fatal ordering
    // race where waitForPhase(0) saw an empty task map and resolved
    // instantly with criticalOk=false → a false "failed" boot.
    runner.run();

    const off = runner.on((snap: RunnerSnapshot) => {
      if (cancelled) return;
      // Drive the progress bar off the boot-score (weighted).
      setProgress(Math.min(100, Math.round(snap.bootScore)));
      setPhase1Pct(Math.min(100, Math.round(snap.phaseProgress[1] || 0)));
      // Surface the most-recently-started running label.
      const running = Object.values(snap.stages).filter(s => s.status === 'running');
      if (running.length) setActiveLabel(running[running.length - 1].label);
      // Durable log on stage status TRANSITIONS only (avoids AsyncStorage
      // thrash from per-frame progress ticks). Console gets every tick.
      blog(`snapshot score=${Math.round(snap.bootScore)} criticalOk=${snap.criticalOk} ok=${snap.counts.ok}/${snap.counts.total}`);
      Object.values(snap.stages).forEach(s => {
        const prev = stageStatusRef.current[s.id];
        if (prev !== s.status && (s.status === 'ok' || s.status === 'failed' || s.status === 'timed_out' || s.status === 'skipped')) {
          stageStatusRef.current[s.id] = s.status;
          bdurable(`stage_${s.id}_${s.status}`, { ms: s.durationMs, err: s.error });
        } else {
          stageStatusRef.current[s.id] = s.status;
        }
      });
      // Mirror into the diagnostics list (for long-press debug).
      const newResults: CheckResult[] = Object.values(snap.stages)
        .filter(s => s.status !== 'pending' && s.status !== 'running')
        .map(s => ({
          id: s.id, label: s.label,
          ok: s.status === 'ok',
          ms: s.durationMs || 0,
          note: s.error || (s.status !== 'ok' ? s.status : undefined),
        }));
      setResults(newResults);
      // Build failure list for the failure UI (critical-fail stages first).
      const fails = newResults
        .filter(r => !r.ok)
        .sort((a, b) => Number(b.ok === false) - Number(a.ok === false));
      setFailedStages(fails);
    });

    (async () => {
      try {
        bdurable('boot_start');
        // Phase 0 = block-on-ready. Phase 1+ continues in the background.
        await runner.waitForPhase(0);
        const snap = runner.snapshot();
        phase0DoneRef.current = true;
        bdurable('phase0_done', { score: snap.bootScore, criticalOk: snap.criticalOk, elapsed: snap.elapsedMs });

        if (!snap.criticalOk) {
          if (cancelled) return;
          commitPhase('failed');
          await traceStep('bootlauncher_critical_fail');
          // Fire-and-forget: ship the trail so we can debug
          try {
            api.post('/api/telemetry/boot', {
              boot_score: snap.bootScore, counts: snap.counts,
              elapsed_ms: snap.elapsedMs, stages: snap.stages, ok: false,
            }, { timeoutMs: 3000, retries: 0 }).catch(() => {});
          } catch {}
          return;
        }

        // Cache the warm-boot snapshot for next launch.
        writeBootCache({ ts: Date.now(), score: snap.bootScore, backendOk: true }).catch(() => {});

        const elapsed = Date.now() - mountTs;
        if (elapsed < MIN_VISIBLE_MS) {
          await new Promise(r => setTimeout(r, MIN_VISIBLE_MS - elapsed));
        }
        if (cancelled) return;
        commitPhase('ready');
        // BOOT-LOOP FIX: clear crash counter on successful boot orchestration
        // (independent of Hub data load — see warm-boot path above).
        clearCrashes().catch(() => {});
        await traceStep(`bootlauncher_ready_score${snap.bootScore}_${snap.elapsedMs}ms`);
        // Phase 1+ runs in the background — but we still report when complete.
        // Under memory pressure we SHED this: abort the runner so background
        // stages stop competing for RAM the instant the user is interactive.
        if (shedRef.current) {
          bdurable('boot_shed_background_phases');
          try { runner.cancel(); } catch {}
          return;
        }
        runner.waitForPhase(2).then(final => {
          // Refresh the cache with the final score (includes phase 1+).
          writeBootCache({
            ts: Date.now(), score: final.bootScore, backendOk: final.criticalOk,
          }).catch(() => {});
          try {
            api.post('/api/telemetry/boot', {
              boot_score: final.bootScore, counts: final.counts,
              elapsed_ms: final.elapsedMs, stages: final.stages, ok: final.ok,
            }, { timeoutMs: 3000, retries: 0 }).catch(() => {});
          } catch {}
        }).catch(() => {});
      } catch (e: any) {
        await traceStep(`bootlauncher_exception_${String(e?.message || e).slice(0, 60)}`);
        if (!cancelled) commitPhase('failed');
      }
    })();

    // ── Hard watchdog ────────────────────────────────────────────────
    // The runner has per-stage timeouts AND a layer timeout in the
    // cascade above us, but those rely on individual code paths firing
    // their callbacks. If for ANY reason (busy main thread, runaway
    // sleep, etc.) the launcher is still 'running' after this budget,
    // declare a fatal escalation so the user is never stuck.
    // 2026-06: lowered 9s → 6s. With the recursive Starfall loop removed
    // the JS thread is no longer starved, so the watchdog timer fires
    // reliably and the user reaches the Hub (offline/degraded) far sooner.
    const WATCHDOG_MS = memTier === 'low' ? 4_500 : 6_000;
    bdurable('watchdog_scheduled', { ms: WATCHDOG_MS, tier: memTier });
    const wd = setTimeout(() => {
      if (cancelled || phaseLockedRef.current) {
        blog(`watchdog skipped (cancelled=${cancelled} locked=${phaseLockedRef.current})`);
        return;
      }
      bdurable('watchdog_fired_force_ready');
      // The backend / health probe is NON-CRITICAL. If an unreachable or 520
      // backend is the only thing keeping us from 'ready', do NOT dead-end in
      // safe-mode — clear crashes and advance into the Hub in OFFLINE/degraded
      // mode so the app is always usable. (Hub + boot-log handle offline.)
      clearCrashes().catch(() => {});
      commitPhase('ready');
    }, WATCHDOG_MS);

    return () => {
      cancelled = true;
      clearTimeout(wd);
      off();
      try { offMem(); } catch {}
      // Abort any in-flight stages so they don't keep hammering the
      // network after the user navigated away or hit Retry.
      try { runner.cancel(); } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryKey, reduceMotion]);

  // Auto-advance returning users as soon as ready.
  React.useEffect(() => {
    if (phase !== 'ready') return;
    if (welcomeSeen === null) return; // still loading flag
    if (welcomeSeen) {
      // Small delay so user sees 100% land before transition.
      const t = setTimeout(() => { bdurable('auto_advance_onReady'); onReady(); }, 350);
      return () => clearTimeout(t);
    }
    // First-timer: stay on launcher; show Enter the Hub button.
  }, [phase, welcomeSeen, onReady]);

  const handleEnterPress = React.useCallback(async () => {
    bdurable('user_enter_hub_press');
    try { await safeSetItem(WELCOME_FLAG_KEY, '1'); } catch {}
    onReady();
  }, [onReady]);

  const handleLogoLongPress = React.useCallback(() => {
    setLongPressCount(c => {
      const next = c + 1;
      if (next >= 2) setShowDiag(true);
      return next;
    });
  }, []);

  const handleRetryBoot = React.useCallback(async () => {
    bdurable('user_retry');
    try { await safeSetItem('@boot/crash_count', '0'); } catch {}
    await traceStep('bootlauncher_user_retry');
    // Reset visible state then bump retryKey to remount the boot effect.
    setProgress(0); setPhase1Pct(0); setActiveLabel('Starting up…');
    setResults([]); setFailedStages([]);
    setWarmBoot(false);
    phaseLockedRef.current = false;   // unlock so commitPhase can fire again
    setPhase('running');
    setRetryKey(k => k + 1);
  }, []);

  // ──────────────────────────────────────────────────────────────────
  //  Render
  // ──────────────────────────────────────────────────────────────────
  return (
    <View style={styles.fill}>
      <View style={[styles.bg, { pointerEvents: 'none' }]}>
        <DecorativeStarfall enabled={!reduceMotion && memTier !== 'low'} />
      </View>

      <Animated.View style={[[styles.center, { opacity: fadeIn }], { pointerEvents: 'box-none' }]}>
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
              <Text style={styles.primaryBtnText}>Enter the Hub</Text>
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
                {failedStages.slice(0, 4).map((f, i) => (
                  <Text key={i} style={styles.failRow}>
                    ✗ {f.label}{f.note ? ` — ${f.note}` : ''}
                  </Text>
                ))}
              </View>
            )}
            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={handleRetryBoot}
              activeOpacity={0.85}>
              <Text style={styles.primaryBtnText}>Retry boot</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryBtn, { marginTop: 10 }]}
              onPress={() => onEscalate('bootlauncher_user_continue')}
              activeOpacity={0.85}>
              <Text style={styles.secondaryBtnText}>Continue anyway</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.secondaryBtn, { marginTop: 10 }]}
              onPress={() => onEscalate('bootlauncher_user_safe_mode')}
              activeOpacity={0.85}>
              <Text style={styles.secondaryBtnText}>Open Safe Mode</Text>
            </TouchableOpacity>
          </>
        )}

        {/* Background-prep chip — only visible while phase-1 work is still
            in flight after primary readiness is achieved. */}
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
          <ScrollView style={{ maxHeight: 260 }}>
            {results.map((r, i) => (
              <Text key={i} style={styles.diagRow}>
                {r.ok ? '✓' : '✗'} {r.label}  ({r.ms}ms){r.note ? `  — ${r.note}` : ''}
              </Text>
            ))}
            <Text style={[styles.diagRow, { marginTop: 10, opacity: 0.7 }]}>Last trace:</Text>
            {getMemoryTrace().slice(-10).map((t, i) => (
              <Text key={`tr-${i}`} style={[styles.diagRow, { opacity: 0.8 }]}>
                {new Date(t.ts).toISOString().slice(11, 19)}  {t.step}
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

// ─────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#0a0a14' },
  bg:   { ...StyleSheet.absoluteFillObject },
  center: {
    flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28,
  },
  logoBubble: {
    width: 84, height: 84, borderRadius: 22,
    backgroundColor: '#1f1733', borderColor: '#7c3aed55', borderWidth: 1,
    alignItems: 'center', justifyContent: 'center', marginBottom: 18,
    ...(Platform.OS === 'ios'
      ? { shadowColor: '#7c3aed', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.5, shadowRadius: 14 }
      : { elevation: 6 }),
  },
  logoGlyph: { color: '#a78bfa', fontSize: 30, fontWeight: '900' },
  title: {
    color: '#fff', fontSize: 38, fontWeight: '900', letterSpacing: -1, textAlign: 'center',
  },
  tagline: {
    color: '#a78bfa', fontSize: 12, fontWeight: '700', letterSpacing: 4,
    textTransform: 'uppercase', marginTop: 6, marginBottom: 28, textAlign: 'center',
  },
  subtitle: {
    color: '#d1d5db', fontSize: 13, textAlign: 'center', lineHeight: 20,
    maxWidth: 320, marginBottom: 20,
  },
  barOuter: {
    width: 260, height: 8, backgroundColor: '#1f1733', borderRadius: 99,
    overflow: 'hidden', marginTop: 6,
  },
  barInner: {
    height: '100%', backgroundColor: '#a78bfa', borderRadius: 99,
  },
  pctLabel: { color: '#9ca3af', fontSize: 12, marginTop: 12, marginBottom: 20, fontWeight: '600' },
  primaryBtn: {
    backgroundColor: '#7c3aed', paddingHorizontal: 32, paddingVertical: 16,
    borderRadius: 999, alignItems: 'center', minHeight: 52, justifyContent: 'center',
    marginTop: 6,
  },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '800', letterSpacing: 0.5 },
  secondaryBtn: {
    borderColor: '#a78bfa55', borderWidth: 1, paddingHorizontal: 24, paddingVertical: 13,
    borderRadius: 999, alignItems: 'center', minHeight: 46, justifyContent: 'center',
  },
  secondaryBtnText: { color: '#a78bfa', fontSize: 13, fontWeight: '700' },
  diagSheet: {
    position: 'absolute', left: 12, right: 12, bottom: 24,
    backgroundColor: '#1c1330ee', borderRadius: 16, padding: 16,
    borderColor: '#7c3aed44', borderWidth: 1,
  },
  diagTitle: { color: '#fff', fontWeight: '800', fontSize: 14, marginBottom: 10 },
  diagRow: { color: '#cbd5e1', fontSize: 11, marginVertical: 2, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  failList: {
    alignSelf: 'stretch', marginHorizontal: 16, marginBottom: 18,
    paddingVertical: 10, paddingHorizontal: 14,
    backgroundColor: '#1c1330aa', borderColor: '#fbbf2433', borderWidth: 1,
    borderRadius: 12,
  },
  failRow: { color: '#fde68a', fontSize: 12, marginVertical: 2 },
  phase1Chip: {
    position: 'absolute', bottom: 28, alignSelf: 'center',
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 12, paddingVertical: 6,
    backgroundColor: '#1c1330cc', borderRadius: 999,
    borderColor: '#7c3aed33', borderWidth: 1,
  },
  phase1Dot: {
    width: 6, height: 6, borderRadius: 3, backgroundColor: '#a78bfa', marginRight: 8,
  },
  phase1Text: { color: '#cbd5e1', fontSize: 11, fontWeight: '700' },
});
