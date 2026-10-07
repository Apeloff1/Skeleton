import { API_BASE, SKELETON_API_BASE } from '../../utils/apiBase';
import { bootstrapService, getAppBootstrap, getAppRuntimeStatus } from './appBootstrapClient';
import type { AppBootstrap, AppRuntimeProduct } from './appBootstrapClient';

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
): Promise<AppServiceHealth> {
  const started = Date.now();
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    try { controller?.abort(); } catch {}
  }, Math.max(250, timeoutMs));

  const onOuterAbort = () => {
    try { controller?.abort(); } catch {}
  };
  outerSignal?.addEventListener?.('abort', onOuterAbort, { once: true } as any);

  try {
    const response = await fetch(`${base}${path}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller?.signal,
    });
    const latencyMs = Date.now() - started;
    if (!response.ok) {
      return {
        name,
        ok: false,
        status: response.status,
        latencyMs,
        detail: `HTTP ${response.status}`,
      };
    }
    return {
      name,
      ok: true,
      status: response.status,
      latencyMs,
      detail: 'healthy',
    };
  } catch (error: any) {
    return {
      name,
      ok: false,
      status: null,
      latencyMs: Date.now() - started,
      detail: outerSignal?.aborted
        ? 'aborted'
        : timedOut
          ? 'timeout'
          : (error?.message || 'network_error'),
    };
  } finally {
    clearTimeout(timer);
    outerSignal?.removeEventListener?.('abort', onOuterAbort);
  }
}

export async function probeAppHealth(
  timeoutMs = 2_500,
  signal?: AbortSignal,
): Promise<AppHealthSnapshot> {
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
          checkedAt: Date.now(),
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
    probe('backend', API_BASE, backendPath, timeoutMs, signal),
    probe('skeleton', SKELETON_API_BASE, skeletonPath, timeoutMs, signal),
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
