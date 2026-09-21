import { API_BASE, SKELETON_API_BASE } from '../../utils/apiBase';

export type AppServiceHealth = {
  name: 'backend' | 'skeleton';
  ok: boolean;
  status: number | null;
  latencyMs: number;
  detail: string;
};

export type AppHealthSnapshot = {
  ok: boolean;
  checkedAt: number;
  services: readonly AppServiceHealth[];
};

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
  const services = await Promise.all([
    probe('backend', API_BASE, '/api/health', timeoutMs, signal),
    probe('skeleton', SKELETON_API_BASE, '/api/v1/health/live', timeoutMs, signal),
  ]);

  return {
    ok: services.every((service) => service.ok),
    checkedAt: Date.now(),
    services,
  };
}
