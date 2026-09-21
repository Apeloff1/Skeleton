import api from '../utils/apiClient';

const DEFAULT_APP_BOOTSTRAP_PATH = '/api/app/bootstrap';
const DEFAULT_APP_STATUS_PATH = '/api/app/status';

export type BootstrapService = {
  name: string;
  role: string;
  kind: string;
  canonical: boolean;
  profile: string;
  health_path: string;
  ingress_prefix: string;
  depends_on: string[];
  default: boolean;
  full: boolean;
};

export type AppBootstrap = {
  schema_version: number;
  application: {
    name: string;
    version: string;
    assembly_schema_version: number;
  };
  contract: {
    bootstrap: string;
    status: string;
    ready: string;
  };
  profiles: {
    default: { services: string[]; layers: string[][] };
    full: { services: string[]; layers: string[][] };
  };
  services: BootstrapService[];
};

export async function getAppBootstrap(signal?: AbortSignal): Promise<AppBootstrap | null> {
  const result = await api.get<AppBootstrap>(DEFAULT_APP_BOOTSTRAP_PATH, {
    signal,
    cacheKey: 'app-bootstrap',
    cacheTtlMs: 30_000,
    retries: 1,
  });
  return result.ok && result.data ? result.data : null;
}

export function bootstrapService(
  bootstrap: AppBootstrap | null,
  name: string,
): BootstrapService | null {
  return bootstrap?.services.find((service) => service.name === name) ?? null;
}


export type AppRuntimeService = {
  name: 'backend' | 'skeleton' | 'mongo';
  ok: boolean;
  status: number | null;
  latency_ms: number;
  detail: string;
  application?: {
    name?: string;
    version?: string;
    component?: string;
    ingress_prefix?: string;
  };
};

export type AppRuntimeProduct = {
  available: boolean;
  canonical_actions: number;
  ready_actions: number;
  ready_pct: number;
  governed_unbound: number;
  unsafe_actions: number;
  policy_gaps: number;
  attestation_sha256: string;
  detail?: string;
};

export type AppRuntimeStatus = {
  ok: boolean;
  checked_at: string;
  application: AppBootstrap['application'];
  scope: 'public-runtime';
  services: AppRuntimeService[];
  product: AppRuntimeProduct;
};

export async function getAppRuntimeStatus(
  timeoutMs = 2_500,
  signal?: AbortSignal,
  bootstrap?: AppBootstrap | null,
): Promise<AppRuntimeStatus | null> {
  const boundedTimeout = Math.max(250, Math.min(timeoutMs, 10_000));
  const path = bootstrap?.contract.status || DEFAULT_APP_STATUS_PATH;
  const result = await api.get<AppRuntimeStatus>(
    `${path}?timeout_ms=${encodeURIComponent(String(boundedTimeout))}`,
    {
      signal,
      timeoutMs: boundedTimeout + 500,
      retries: 0,
      cacheKey: 'app-runtime-status',
      cacheTtlMs: 1_000,
    },
  );
  return result.ok && result.data ? result.data : null;
}
