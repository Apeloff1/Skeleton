/**
 * LaunchCascade — Redundant 4-layer launcher.
 *
 * Why this exists:
 *   Users have reported the app crashing during boot — the animated
 *   `/welcome` starfall splash never rendering, or the heavy `/hub`
 *   route killing the JS thread on import. We can't always know which
 *   layer is the culprit (Animated bridge, AsyncStorage hang, a single
 *   bad import inside hub.tsx, etc.), so we provide MULTIPLE fallback
 *   launchers — each progressively simpler — and auto-escalate when:
 *
 *     • A layer throws (caught by an inline error boundary)
 *     • A layer doesn't paint within 3.5 s ("frozen" sentinel)
 *     • The user explicitly taps "Skip" / "Open hub directly"
 *
 *   Layer 0 — Animated starfall welcome (best UX)
 *   Layer 1 — Static gradient welcome (no animations)
 *   Layer 2 — Minimal one-button launcher (text only)
 *   Layer 3 — Hard safe-mode shortcut (no React work at all, just two
 *             plain TouchableOpacity rows)
 *
 *   Tap "Skip" anywhere advances forward; the user is always one tap
 *   from `/hub`. No matter what fails, you should at least reach Layer 3
 *   where a button can route to `/safe-mode` for recovery.
 *
 *   The cascade also writes attempt counts to AsyncStorage so consecutive
 *   crashes during the same boot session don't re-pick the same layer.
 */
import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { safeGetItem, safeSetItem } from '../utils/safeStorage';
import { traceStep, traceStepSync } from '../utils/bootTracer';
import { readBootCache } from '../src/boot';

const ATTEMPT_KEY = '@launcher/attempt:v1';
const WELCOME_FLAG_KEY = '@codedock:welcome_seen:v1';
const MAX_LAYER = 3;
/** Hard timeout per layer — if no progress, escalate. */
const LAYER_TIMEOUT_MS = 3500;
/**
 * Aged-out reset: if the last successful boot happened within this window,
 * any persisted "attempt" counter is forgiven (reset to 0). Without this a
 * single transient crash months ago would pin the user to Layer 3 forever.
 */
const ATTEMPT_AGE_OUT_MS = 60 * 60 * 1000;  // 1 hour

// ─────────────────────────────────────────────────────────────────────
//  Inline ErrorBoundary — local to the cascade so layer failures are
//  caught and trigger the next layer instead of bubbling to the global
//  ErrorBoundary (which would block forward progress).
// ─────────────────────────────────────────────────────────────────────
interface BoundaryProps { onError: (e: Error) => void; children: React.ReactNode }
class LayerBoundary extends React.Component<BoundaryProps, { errored: boolean }> {
  state = { errored: false };
  static getDerivedStateFromError() { return { errored: true }; }
  componentDidCatch(error: Error) {
    // Surface the error so we can diagnose which layer crashed.
    // Use both console.warn (visible in dev tools) and traceStep (durable).
    try {
      console.warn('[LaunchCascade] layer boundary caught:', error?.message || error);
      traceStep(`cascade_boundary_${String(error?.message || error).slice(0, 80)}`).catch(() => {});
    } catch {}
    try { this.props.onError(error); } catch {}
  }
  render() {
    if (this.state.errored) return null;
    return this.props.children as any;
  }
}

// ─────────────────────────────────────────────────────────────────────
//  Layer 0 — BootLauncher (progress bar + readiness checks + decorative
//  Starfall). The Starfall is now PURELY decorative — animation deferred
//  via InteractionManager so it never gates user input or eats first-
//  frame budget. Replaces the old Layer0_Starfall, which kicked 18 Animated
//  loops on mount and was a primary source of cold-boot jank.
// ─────────────────────────────────────────────────────────────────────
function Layer0_BootLauncher({
  onEnter, onEscalate,
}: { onEnter: () => void; onEscalate: (why: string) => void }) {
  // Lazy require so any parse error in BootLauncher is caught by the
  // surrounding LayerBoundary and we fall through to Layer 1.
  let BootLauncher: any = null;
  try {
     
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    BootLauncher = require('./BootLauncher').default;
  } catch (e) {
    throw e;
  }
  return <BootLauncher onReady={onEnter} onEscalate={onEscalate} />;
}

// ─────────────────────────────────────────────────────────────────────
//  Layer 1 — Static gradient welcome (no Animated, no starfall)
// ─────────────────────────────────────────────────────────────────────
function Layer1_Static({ onEnter, onSkip }: { onEnter: () => void; onSkip: () => void }) {
  return (
    <View style={[styles.fill, { backgroundColor: '#0a0a14' }]}>
      <View style={styles.center}>
        <Text style={styles.title}>CodeDock</Text>
        <Text style={styles.tagline}>Quantum Nexus</Text>
        <Text style={styles.subtitle}>Welcome aboard. Tap below to launch the hub.</Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={onEnter} activeOpacity={0.8}>
          <Text style={styles.primaryBtnText}>Open Hub</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onSkip} hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }} style={{ marginTop: 18 }}>
          <Text style={styles.tapHint}>Use minimal launcher</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────
//  Layer 2 — Minimal one-button launcher (almost no React work)
// ─────────────────────────────────────────────────────────────────────
function Layer2_Minimal({ onEnter, onSkip }: { onEnter: () => void; onSkip: () => void }) {
  return (
    <View style={[styles.fill, { backgroundColor: '#0a0a14', justifyContent: 'center' }]}>
      <View style={{ paddingHorizontal: 32 }}>
        <Text style={[styles.title, { fontSize: 28 }]}>CodeDock</Text>
        <Text style={[styles.subtitle, { marginBottom: 28 }]}>
          Minimal launcher — animations disabled for stability.
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={onEnter} activeOpacity={0.8}>
          <Text style={styles.primaryBtnText}>Enter App</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onSkip} style={[styles.secondaryBtn, { marginTop: 12 }]}>
          <Text style={styles.secondaryBtnText}>Open Recovery (Safe Mode)</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────
//  Layer 3 — Hard safe-mode shortcut (last resort)
// ─────────────────────────────────────────────────────────────────────
function Layer3_SafeMode({ goSafeMode, retryFromTop }: { goSafeMode: () => void; retryFromTop: () => void }) {
  return (
    <View style={[styles.fill, { backgroundColor: '#0a0a14', justifyContent: 'center' }]}>
      <View style={{ paddingHorizontal: 32 }}>
        <Text style={[styles.title, { fontSize: 24, color: '#fbbf24' }]}>Launcher fallback</Text>
        <Text style={[styles.subtitle, { marginBottom: 24 }]}>
          We had trouble starting the app. Pick a recovery option:
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={goSafeMode} activeOpacity={0.8}>
          <Text style={styles.primaryBtnText}>Open Safe Mode</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={retryFromTop} style={[styles.secondaryBtn, { marginTop: 12 }]}>
          <Text style={styles.secondaryBtnText}>Retry launcher (start over)</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────
//  Cascade controller
// ─────────────────────────────────────────────────────────────────────
export default function LaunchCascade() {
  const router = useRouter();
  const [layer, setLayer] = React.useState<number>(0);
  const [ready, setReady] = React.useState(false);
  const escalateLockRef = React.useRef(false);
  const watchdogRef = React.useRef<any>(null);

  // ── Boot once: hydrate attempt counter ──
  React.useEffect(() => {
    (async () => {
      try {
        await traceStep('cascade_mounted');

        // Allow ?reset=1 or ?launcher=0..3 in URL to override attempt counter
        // for QA / manual recovery. Useful when persisted attempt is high
        // but the user wants to retry the full sequence.
        let urlOverride: number | null = null;
        try {
          if (typeof window !== 'undefined' && window.location?.search) {
            const params = new URLSearchParams(window.location.search);
            if (params.get('reset') === '1') urlOverride = 0;
            const lq = params.get('launcher');
            if (lq !== null) {
              const n = parseInt(lq, 10);
              if (!Number.isNaN(n)) urlOverride = Math.min(MAX_LAYER, Math.max(0, n));
            }
          }
        } catch {}

        const raw = await safeGetItem(ATTEMPT_KEY, '0', 400);
        let persisted = Math.min(MAX_LAYER, Math.max(0, parseInt(raw || '0', 10) || 0));

        // Aged-out reset: if the previous boot succeeded recently, any
        // persisted layer escalation is stale — forgive it so the user
        // gets the rich Layer-0 experience back.
        if (persisted > 0) {
          try {
            const cache = await readBootCache();
            if (cache && (Date.now() - cache.ts) < ATTEMPT_AGE_OUT_MS) {
              await traceStep(`cascade_attempt_aged_out_from_${persisted}`);
              await safeSetItem(ATTEMPT_KEY, '0');
              persisted = 0;
            }
          } catch { /* no cache → keep persisted */ }
        }

        const start = urlOverride !== null ? urlOverride : persisted;
        if (urlOverride !== null) {
          // Wipe the persisted attempt — user explicitly requested a reset.
          await safeSetItem(ATTEMPT_KEY, String(urlOverride));
        }
        setLayer(start);

        // NOTE (2026-02): we used to skip-to-/hub here when the welcome
        // flag was set — but that bypassed all boot health checks, so a
        // backend outage / corrupt storage would crash mid-route. The
        // BootLauncher (Layer 0) now runs every launch with a real
        // progress bar and auto-advances returning users when ALL checks
        // pass. This makes every launch self-verifying without adding
        // perceived latency: returning users still see only a brief
        // "Ready — launching…" flash before the hub appears.
        await traceStep(`cascade_layer_${start}`);
      } catch {
        // If anything fails reading attempts, start fresh.
        setLayer(0);
      } finally {
        setReady(true);
      }
    })();
  }, [router]);

  // ── Watchdog: if a layer doesn't progress in LAYER_TIMEOUT_MS, escalate ──
  // (Layer 0 / BootLauncher manages its OWN watchdog — every check has its
  //  own timeout + fallback. Skipping it here avoids a double-watchdog
  //  race that could escalate while legitimate boot work is in flight.)
  React.useEffect(() => {
    if (!ready) return;
    if (layer === 0) return;             // BootLauncher self-governs
    if (layer >= MAX_LAYER) return;
    if (watchdogRef.current) clearTimeout(watchdogRef.current);
    watchdogRef.current = setTimeout(() => {
      // The user hasn't progressed — assume the current layer is broken
      // visually (frozen, blank, off-screen) and auto-escalate.
      escalate(`watchdog_layer_${layer}`);
    }, LAYER_TIMEOUT_MS);
    return () => {
      if (watchdogRef.current) clearTimeout(watchdogRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layer, ready]);

  const escalate = React.useCallback((reason: string) => {
    if (escalateLockRef.current) return;
    escalateLockRef.current = true;
    setTimeout(() => { escalateLockRef.current = false; }, 200);
    setLayer(prev => {
      const next = Math.min(MAX_LAYER, prev + 1);
      traceStep(`cascade_escalate_${prev}_to_${next}_${reason}`).catch(() => {});
      // Persist the NEW layer so if THIS boot crashes hard before
      // markBootClean(), the next launch picks the simpler layer.
      safeSetItem(ATTEMPT_KEY, String(next)).catch(() => {});
      return next;
    });
  }, []);

  const enterHub = React.useCallback(async () => {
    try {
      await safeSetItem(WELCOME_FLAG_KEY, '1');
    } catch {}
    try {
      await safeSetItem(ATTEMPT_KEY, '0'); // clean attempts on successful entry
    } catch {}
    await traceStep('cascade_enter_hub');
    router.replace('/hub');
  }, [router]);

  const goSafeMode = React.useCallback(async () => {
    await traceStep('cascade_go_safe_mode');
    router.replace('/safe-mode');
  }, [router]);

  const retryFromTop = React.useCallback(async () => {
    try { await safeSetItem(ATTEMPT_KEY, '0'); } catch {}
    setLayer(0);
  }, []);

  if (!ready) {
    return (
      <View style={[styles.fill, styles.center, { backgroundColor: '#0a0a14' }]}>
        <ActivityIndicator size="small" color="#a78bfa" />
      </View>
    );
  }

  // Render current layer wrapped in a local boundary that escalates on error.
  // The key={layer} forces a fresh LayerBoundary instance for each layer so
  // a previous layer's error state doesn't leak forward (which would render
  // null forever after the first failure).
  traceStepSync(`cascade_render_layer_${layer}`);
  return (
    <LayerBoundary key={`layer-${layer}`} onError={() => escalate('boundary_caught')}>
      {layer === 0 && (
        <Layer0_BootLauncher
          onEnter={enterHub}
          onEscalate={(why: string) => {
            if (why === 'bootlauncher_user_safe_mode') {
              goSafeMode();
            } else {
              escalate(why);
            }
          }}
        />
      )}
      {layer === 1 && <Layer1_Static onEnter={enterHub} onSkip={() => escalate('user_skip_static')} />}
      {layer === 2 && <Layer2_Minimal onEnter={enterHub} onSkip={goSafeMode} />}
      {layer >= 3 && <Layer3_SafeMode goSafeMode={goSafeMode} retryFromTop={retryFromTop} />}
    </LayerBoundary>
  );
}

// ─────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#0a0a14' },
  bg:   { ...StyleSheet.absoluteFillObject },
  center: {
    flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28,
  },
  title: {
    color: '#fff', fontSize: 38, fontWeight: '900', letterSpacing: -1,
    textAlign: 'center',
    ...(Platform.OS === 'ios'
      ? { textShadowColor: '#a78bfa88', textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 12 }
      : {}),
  },
  tagline: {
    color: '#a78bfa', fontSize: 13, fontWeight: '700', letterSpacing: 4,
    textTransform: 'uppercase', marginTop: 6, marginBottom: 22, textAlign: 'center',
  },
  subtitle: {
    color: '#d1d5db', fontSize: 13, textAlign: 'center', lineHeight: 20,
    maxWidth: 320, marginBottom: 36,
  },
  primaryBtn: {
    backgroundColor: '#7c3aed', paddingHorizontal: 32, paddingVertical: 16,
    borderRadius: 999, alignItems: 'center', minHeight: 52, justifyContent: 'center',
  },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '800', letterSpacing: 0.5 },
  secondaryBtn: {
    borderColor: '#a78bfa55', borderWidth: 1, paddingVertical: 14,
    borderRadius: 999, alignItems: 'center', minHeight: 48, justifyContent: 'center',
  },
  secondaryBtnText: { color: '#a78bfa', fontSize: 13, fontWeight: '700' },
  tapHint: { color: '#9ca3af', fontSize: 12, fontStyle: 'italic' },
});
