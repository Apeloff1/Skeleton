import { API_BASE, SKELETON_API_BASE } from '../utils/apiBase';
import { bootstrapService, getAppBootstrap, getAppRuntimeStatus } from './appBootstrapClient';
import type { AppBootstrap, AppRuntimeProduct } from './appBootstrapClient';
import { readBoundedResponseText } from '../utils/apiClient';

export type AppServiceHealth = {
  name: 'backend' | 'skeleton' | 'mongo';
  ok: boolean;
  status: number | null;
  latencyMs: number;
  detail: string;
};

export type AppHealthSnapshot = {
  ok: boolean;
  checkedAt: number;
  services: readonly AppServiceHealth[];
  application: AppBootstrap['application'] | null;
  product: AppRuntimeProduct | null;
  contractSource: 'runtime' | 'bootstrap-fallback' | 'static-fallback';
};

const FALLBACK_HEALTH_PATHS = Object.freeze({
  backend: '/api/health',
  skeleton: '/api/v1/health/live',
});

async function probe(
  name: AppServiceHealth['name'],
  base: string,
  path: string,
  timeoutMs: number,
  outerSignal?: AbortSignal,
  application?: AppBootstrap['application'],
): Promise<AppServiceHealth> {
  const started = Date.now();
  const failure = (detail: string, status: number | null = null): AppServiceHealth => ({ name, ok: false, status, latencyMs: Date.now() - started, detail });
  if (outerSignal?.aborted) return failure('aborted');
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  let timedOut = false;
  let rejectDeadline: (error: Error) => void = () => {};
  let rejectCancelled: (error: Error) => void = () => {};
  const deadline = new Promise<never>((_resolve, reject) => { rejectDeadline = reject; });
  const cancelled = new Promise<never>((_resolve, reject) => { rejectCancelled = reject; });
  const timer = setTimeout(() => { timedOut = true; try { controller?.abort(); } catch {} rejectDeadline(new Error('timeout')); }, timeoutMs);

  const onOuterAbort = () => {
    try { controller?.abort(); } catch {}
    rejectCancelled(new Error('aborted'));
  };
  outerSignal?.addEventListener?.('abort', onOuterAbort, { once: true } as any);

  try {
    const target = `${base}${path}`;
    const read = async (): Promise<AppServiceHealth> => {
      const response = await fetch(target, { method: 'GET', headers: { Accept: 'application/json' }, signal: controller?.signal, redirect: 'error' });
      if (!response.ok) return failure(`HTTP ${response.status}`, response.status);
      if (response.redirected || response.url && new URL(response.url).href !== new URL(target).href) return failure('health endpoint redirected', response.status);
      const bounded = await readBoundedResponseText(response, 64 * 1024);
      if (bounded.oversized) { controller?.abort(); return failure('health response too large', response.status); }
      let payload: any;
      try { payload = JSON.parse(bounded.text); } catch { return failure('invalid health response', response.status); }
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return failure('invalid health response', response.status);
      const identity = name === 'skeleton' ? payload.application : payload.canonical_application;
      if (name === 'skeleton' || identity !== undefined) {
        const expected = application || { name: 'Skeleton', version: '16.0.0' };
        if (!identity || typeof identity !== 'object' || identity.name !== expected.name || identity.version !== expected.version
          || identity.component !== (name === 'skeleton' ? 'engine' : 'backend')
          || identity.ingress_prefix !== (name === 'skeleton' ? '/api/v1' : '/api')) return failure('service identity mismatch', response.status);
        if (name === 'skeleton' && payload.alive !== true) return failure('engine liveness not confirmed', response.status);
      } else if (name === 'backend' && payload.status !== 'healthy') return failure('health status not confirmed', response.status);
      return { name, ok: true, status: response.status, latencyMs: Date.now() - started, detail: 'healthy' };
    };
    const result = await Promise.race([read(), deadline, cancelled]);
    return outerSignal?.aborted ? failure('aborted') : result;
  } catch {
    return failure(outerSignal?.aborted ? 'aborted' : timedOut ? 'timeout' : 'network_error');
  } finally {
    clearTimeout(timer);
    outerSignal?.removeEventListener?.('abort', onOuterAbort);
  }
}

export async function probeAppHealth(
  timeoutMs = 2_500,
  signal?: AbortSignal,
): Promise<AppHealthSnapshot> {
  timeoutMs = Number.isFinite(timeoutMs) ? Math.max(250, Math.min(10000, Math.trunc(timeoutMs))) : 2500;
  let bootstrap: AppBootstrap | null = null;
  try {
    bootstrap = await getAppBootstrap(signal);
  } catch {
    bootstrap = null;
  }

  if (bootstrap) {
    try {
      const runtime = await getAppRuntimeStatus(timeoutMs, signal, bootstrap);
      if (runtime) {
        return {
          ok: runtime.ok,
          checkedAt: Date.parse(runtime.checked_at),
          services: runtime.services.map((service) => ({
            name: service.name,
            ok: service.ok,
            status: service.status,
            latencyMs: service.latency_ms,
            detail: service.detail,
          })),
          application: runtime.application,
          product: runtime.product,
          contractSource: 'runtime',
        };
      }
    } catch {
      // Fall through to direct probes using bootstrap-owned health paths.
    }
  }

  const backendPath = bootstrapService(bootstrap, 'backend')?.health_path || FALLBACK_HEALTH_PATHS.backend;
  const skeletonPath = bootstrapService(bootstrap, 'skeleton')?.health_path || FALLBACK_HEALTH_PATHS.skeleton;

  const services = await Promise.all([
    probe('backend', API_BASE, backendPath, timeoutMs, signal, bootstrap?.application),
    probe('skeleton', SKELETON_API_BASE, skeletonPath, timeoutMs, signal, bootstrap?.application),
  ]);

  return {
    // Direct probes are diagnostic fallback only. They cannot verify private
    // state services, so the whole-application verdict remains fail-closed.
    ok: false,
    checkedAt: Date.now(),
    services,
    application: bootstrap?.application ?? null,
    product: null,
    contractSource: bootstrap ? 'bootstrap-fallback' : 'static-fallback',
  };
}
