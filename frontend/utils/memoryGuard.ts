/**
 * memoryGuard — OOM guard + guardrails for low-RAM devices (Samsung S20).
 *
 *  React Native dispatches an AppState 'memoryWarning' when the OS is under
 *  memory pressure (Android onTrimMemory / iOS didReceiveMemoryWarning). This
 *  is the ONLY reliable cross-platform OOM early-warning. On that signal we:
 *    1. force-run the on-device self-cleaner (frees AsyncStorage/FS cache),
 *    2. notify all subscribers so heavy views can shed memory NOW
 *       (3D viewport disposes its GL context, starfields drop to 0, etc.),
 *    3. durably log it (survives the crash via bootTracer's session ring).
 *
 *  Also exposes a static device "tier" (from expo-device total RAM) so heavy
 *  components can pick conservative caps up-front instead of reacting late.
 */
import { AppState } from 'react-native';
import { traceStepSync } from './bootTracer';

export type MemTier = 'low' | 'mid' | 'high';

let _tier: MemTier = 'mid';
let _installed = false;
const _listeners = new Set<() => void>();

/** Device memory tier — drives up-front guardrail caps. */
export function getMemTier(): MemTier { return _tier; }

/** Per-tier guardrail limits consumed by heavy components.
 *  SAFE, conservative parameters: lower resolution, fps caps and disabled
 *  antialias/shadows on weaker tiers to bound GPU / thermal / VRAM load. */
export function memLimits() {
  switch (_tier) {
    case 'low':  return {
      maxModals: 6,  maxMeshes: 28,  maxParts: 28,  stars: 10, frameMs: 50,
      maxRenderPx: 320, pixelRatio: 1,    antialias: false, shadows: false, shadowMap: 512,
    };
    case 'high': return {
      maxModals: 20, maxMeshes: 80,  maxParts: 80,  stars: 36, frameMs: 33,
      maxRenderPx: 512, pixelRatio: 1.25, antialias: true,  shadows: true,  shadowMap: 1024,
    };
    default:     return {
      maxModals: 12, maxMeshes: 48,  maxParts: 48,  stars: 18, frameMs: 40,
      maxRenderPx: 384, pixelRatio: 1,    antialias: false, shadows: true,  shadowMap: 768,
    };
  }
}

export type RenderLimits = ReturnType<typeof memLimits>;

// ── Runtime STRESS escalation (redundant guard layered over the static tier).
// Each memory-pressure / sustained-slow-frame event raises stress; it decays
// over time. effectiveLimits() folds stress into the static caps so the app
// progressively LOWERS resolution / fps / mesh budget under real pressure.
let _stress = 0;            // 0 (calm) … 3 (severe)
let _stressTs = 0;
const _stressListeners = new Set<() => void>();

export function getStress(): number {
  // decay one level per 20s of calm
  const now = Date.now();
  if (_stress > 0 && now - _stressTs > 20000) {
    _stress = Math.max(0, _stress - Math.floor((now - _stressTs) / 20000));
    _stressTs = now;
  }
  return _stress;
}

export function bumpStress(by = 1): void {
  _stress = Math.min(3, _stress + by);
  _stressTs = Date.now();
  _stressListeners.forEach(l => { try { l(); } catch {} });
}

export function onStressChange(cb: () => void): () => void {
  _stressListeners.add(cb);
  return () => { _stressListeners.delete(cb); };
}

/** Static caps DOWNSCALED by the current runtime stress level. Heavy
 *  components should read THIS (and re-read on pressure) for live safety. */
export function effectiveLimits(): RenderLimits {
  const base = memLimits();
  const s = getStress();
  if (s <= 0) return base;
  const cut = 1 - Math.min(0.6, s * 0.2);           // up to -60% at severe
  return {
    ...base,
    maxMeshes: Math.max(8, Math.round(base.maxMeshes * cut)),
    maxParts:  Math.max(8, Math.round(base.maxParts * cut)),
    stars:     Math.max(0, Math.round(base.stars * cut)),
    maxRenderPx: Math.max(192, Math.round(base.maxRenderPx * cut)),
    pixelRatio: 1,
    frameMs: Math.min(66, base.frameMs + s * 6),     // throttle fps → lower CPU/GPU
    antialias: s >= 1 ? false : base.antialias,
    shadows:   s >= 2 ? false : base.shadows,
    shadowMap: s >= 1 ? Math.max(256, Math.round(base.shadowMap / (1 + s))) : base.shadowMap,
  };
}

// Sustained-slow-frame detector → thermal/CPU proxy (no native thermal API in
// Expo Go). N consecutive frames slower than 1.6× the cap raises stress.
let _slowRun = 0;
export function reportFrameTime(ms: number, capMs: number): void {
  if (ms > capMs * 1.6) {
    if (++_slowRun >= 30) { _slowRun = 0; bumpStress(1); }
  } else if (_slowRun > 0) {
    _slowRun = Math.max(0, _slowRun - 1);
  }
}

/** Subscribe to memory-pressure events. Returns an unsubscribe fn. */
export function onMemoryPressure(cb: () => void): () => void {
  _listeners.add(cb);
  return () => { _listeners.delete(cb); };
}

let _lastPressure = 0;
/** Fire a memory-pressure response (debounced). Safe to call manually too. */
export function triggerMemoryPressure(reason = 'os_warning'): void {
  const now = Date.now();
  if (now - _lastPressure < 3000) return;
  _lastPressure = now;
  bumpStress(1);   // redundant runtime guard escalates with each pressure event
  traceStepSync(`MEM_PRESSURE ${reason}`);
  // 1) force the self-cleaner (lazy import avoids a static cycle).
  try { import('./selfCleaner').then(m => m.runSelfCleaner('mem_pressure', true)).catch(() => {}); } catch {}
  // 2) tell heavy components to shed memory immediately.
  _listeners.forEach(l => { try { l(); } catch {} });
}

/** Install once, as early as possible (root layout). Idempotent. */
export function installMemoryGuard(): void {
  if (_installed) return;
  _installed = true;

  // Detect device RAM tier (best-effort; expo-device is native-only).
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Device = require('expo-device');
    const bytes: number | null = Device?.totalMemory ?? null;
    if (typeof bytes === 'number' && bytes > 0) {
      const gb = bytes / (1024 ** 3);
      _tier = gb < 4 ? 'low' : gb < 6 ? 'mid' : 'high';
    }
  } catch { /* keep default 'mid' */ }

  try {
    // RN exposes OS memory warnings through AppState.
    AppState.addEventListener('memoryWarning', () => triggerMemoryPressure('os_warning'));
  } catch { /* not all platforms emit this */ }

  // Redundant proactive poll: where a JS-heap reading is available (web /
  // some engines), pre-empt OOM by reacting at 82% heap BEFORE the OS warns.
  try {
    const perf: any = (globalThis as any).performance;
    if (perf && perf.memory && typeof perf.memory.usedJSHeapSize === 'number') {
      setInterval(() => {
        try {
          const m = perf.memory;
          if (m.jsHeapSizeLimit > 0 && m.usedJSHeapSize / m.jsHeapSizeLimit > 0.82) {
            triggerMemoryPressure('heap_high');
          }
        } catch { /* ignore */ }
      }, 5000);
    }
  } catch { /* ignore */ }

  traceStepSync(`mem_guard_installed tier=${_tier}`);
}
