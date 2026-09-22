/**
 * LaunchCascade — redundant 4-layer launcher.
 *
 * Every normal launch now enters the lightweight canonical `/product` shell.
 * The legacy `/hub` remains available from that shell while consolidation
 * continues, but it is no longer on the critical cold-start path.
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
const LAYER_TIMEOUT_MS = 3500;
const ATTEMPT_AGE_OUT_MS = 60 * 60 * 1000;

interface BoundaryProps { onError: (e: Error) => void; children: React.ReactNode }
class LayerBoundary extends React.Component<BoundaryProps, { errored: boolean }> {
  state = { errored: false };
  static getDerivedStateFromError() { return { errored: true }; }
  componentDidCatch(error: Error) {
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

function Layer0_BootLauncher({
  onEnter, onEscalate,
}: { onEnter: () => void; onEscalate: (why: string) => void }) {
  let BootLauncher: any = null;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    BootLauncher = require('./BootLauncher').default;
  } catch (e) {
    throw e;
  }
  return <BootLauncher onReady={onEnter} onEscalate={onEscalate} />;
}

function Layer1_Static({ onEnter, onSkip }: { onEnter: () => void; onSkip: () => void }) {
  return (
    <View style={[styles.fill, { backgroundColor: '#0a0a14' }]}>
      <View style={styles.center}>
        <Text style={styles.title}>Skeleton</Text>
        <Text style={styles.tagline}>Unified Product</Text>
        <Text style={styles.subtitle}>Create, Play, Learn and Operate from one consolidated shell.</Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={onEnter} activeOpacity={0.8}>
          <Text style={styles.primaryBtnText}>Open Skeleton</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onSkip} hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }} style={{ marginTop: 18 }}>
          <Text style={styles.tapHint}>Use minimal launcher</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function Layer2_Minimal({ onEnter, onSkip }: { onEnter: () => void; onSkip: () => void }) {
  return (
    <View style={[styles.fill, { backgroundColor: '#0a0a14', justifyContent: 'center' }]}>
      <View style={{ paddingHorizontal: 32 }}>
        <Text style={[styles.title, { fontSize: 28 }]}>Skeleton</Text>
        <Text style={[styles.subtitle, { marginBottom: 28 }]}>
          Minimal launcher — animations disabled for stability.
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={onEnter} activeOpacity={0.8}>
          <Text style={styles.primaryBtnText}>Enter Product</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onSkip} style={[styles.secondaryBtn, { marginTop: 12 }]}>
          <Text style={styles.secondaryBtnText}>Open Recovery (Safe Mode)</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

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

export default function LaunchCascade() {
  const router = useRouter();
  const [layer, setLayer] = React.useState<number>(0);
  const [ready, setReady] = React.useState(false);
  const escalateLockRef = React.useRef(false);
  const watchdogRef = React.useRef<any>(null);
  const tracedLayerRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    (async () => {
      try {
        await traceStep('cascade_mounted');
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
        if (persisted > 0) {
          try {
            const cache = await readBootCache();
            if (cache && (Date.now() - cache.ts) < ATTEMPT_AGE_OUT_MS) {
              await traceStep(`cascade_attempt_aged_out_from_${persisted}`);
              await safeSetItem(ATTEMPT_KEY, '0');
              persisted = 0;
            }
          } catch {}
        }

        const start = urlOverride !== null ? urlOverride : persisted;
        if (urlOverride !== null) {
          await safeSetItem(ATTEMPT_KEY, String(urlOverride));
        }
        setLayer(start);
        await traceStep(`cascade_layer_${start}`);
      } catch {
        setLayer(0);
      } finally {
        setReady(true);
      }
    })();
  }, [router]);

  React.useEffect(() => {
    if (!ready || layer === 0 || layer >= MAX_LAYER) return;
    if (watchdogRef.current) clearTimeout(watchdogRef.current);
    watchdogRef.current = setTimeout(() => {
      escalate(`watchdog_layer_${layer}`);
    }, LAYER_TIMEOUT_MS);
    return () => {
      if (watchdogRef.current) clearTimeout(watchdogRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layer, ready]);

  // Keep the crash breadcrumb, but record it once per layer transition instead
  // of writing the complete trace to AsyncStorage on every React render.
  React.useEffect(() => {
    if (!ready || tracedLayerRef.current === layer) return;
    tracedLayerRef.current = layer;
    traceStepSync(`cascade_render_layer_${layer}`);
  }, [layer, ready]);

  const escalate = React.useCallback((reason: string) => {
    if (escalateLockRef.current) return;
    escalateLockRef.current = true;
    setTimeout(() => { escalateLockRef.current = false; }, 200);
    setLayer(prev => {
      const next = Math.min(MAX_LAYER, prev + 1);
      traceStep(`cascade_escalate_${prev}_to_${next}_${reason}`).catch(() => {});
      safeSetItem(ATTEMPT_KEY, String(next)).catch(() => {});
      return next;
    });
  }, []);

  const enterProduct = React.useCallback(async () => {
    try { await safeSetItem(WELCOME_FLAG_KEY, '1'); } catch {}
    try { await safeSetItem(ATTEMPT_KEY, '0'); } catch {}
    await traceStep('cascade_enter_product');
    router.replace('/product');
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

  return (
    <LayerBoundary key={`layer-${layer}`} onError={() => escalate('boundary_caught')}>
      {layer === 0 && (
        <Layer0_BootLauncher
          onEnter={enterProduct}
          onEscalate={(why: string) => {
            if (why === 'bootlauncher_user_safe_mode') goSafeMode();
            else escalate(why);
          }}
        />
      )}
      {layer === 1 && <Layer1_Static onEnter={enterProduct} onSkip={() => escalate('user_skip_static')} />}
      {layer === 2 && <Layer2_Minimal onEnter={enterProduct} onSkip={goSafeMode} />}
      {layer >= 3 && <Layer3_SafeMode goSafeMode={goSafeMode} retryFromTop={retryFromTop} />}
    </LayerBoundary>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#0a0a14' },
  bg: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28 },
  title: {
    color: '#fff', fontSize: 38, fontWeight: '900', letterSpacing: -1, textAlign: 'center',
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
