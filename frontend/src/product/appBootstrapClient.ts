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

type Fields = Record<string, unknown>;
function object(value: unknown): value is Fields { return !!value && typeof value === 'object' && !Array.isArray(value); }
function text(value: unknown, maximum = 160): value is string { return typeof value === 'string' && value.length > 0 && value.length <= maximum && !/[\u0000-\u001f\u007f]/.test(value); }
function count(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) >= 0 && Number(value) <= 1_000_000_000; }
function path(value: unknown, empty = false): value is string {
  return typeof value === 'string' && (empty && value === '' || value.length <= 256 && /^\/(?:[a-zA-Z0-9_-]+\/?)*$/.test(value));
}
function stringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 32 && value.every(item => text(item, 64)) && new Set(value).size === value.length;
}
function application(value: unknown): value is AppBootstrap['application'] {
  return object(value) && text(value.name) && text(value.version, 64) && value.assembly_schema_version === 1;
}
function bootstrap(value: unknown): AppBootstrap | null {
  if (!object(value) || value.schema_version !== 1 || !application(value.application) || !object(value.contract)
    || !['bootstrap', 'status', 'ready'].every(key => path((value.contract as Fields)[key]) && String((value.contract as Fields)[key]).startsWith('/api/'))
    || new Set(Object.values(value.contract)).size !== 3 || Object.keys(value.contract).length !== 3
    || !Array.isArray(value.services) || value.services.length < 3 || value.services.length > 32 || !object(value.profiles)) return null;
  for (const service of value.services) {
    if (!object(service) || !text(service.name, 64) || !text(service.role) || !text(service.kind, 64)
      || typeof service.profile !== 'string' || service.profile.length > 64
      || ['canonical', 'default', 'full'].some(key => typeof service[key] !== 'boolean')
      || !path(service.health_path, true) || !path(service.ingress_prefix, true) || !stringList(service.depends_on)) return null;
  }
  const names = new Set(value.services.map(service => service.name));
  if (names.size !== value.services.length || !['backend', 'skeleton', 'mongo'].every(name => names.has(name))) return null;
  if (value.services.some(service => service.depends_on.some((name: string) => !names.has(name) || name === service.name))) return null;
  for (const kind of ['default', 'full']) {
    const profile = value.profiles[kind];
    if (!object(profile) || !stringList(profile.services) || !profile.services.length || profile.services.some(name => !names.has(name))
      || !Array.isArray(profile.layers) || !profile.layers.length || profile.layers.length > 32 || profile.layers.some(layer => !stringList(layer) || !layer.length)) return null;
    const flattened = profile.layers.flat();
    const profileServices = profile.services;
    if (flattened.length !== profileServices.length || new Set(flattened).size !== flattened.length || flattened.some(name => !profileServices.includes(name))) return null;
    const seen = new Set<string>();
    for (const layer of profile.layers as string[][]) {
      for (const name of layer) {
        const service = value.services.find(row => row.name === name);
        if (!service || service.depends_on.some((dependency: string) => !seen.has(dependency))) return null;
      }
      layer.forEach(name => seen.add(name));
    }
  }
  return value as AppBootstrap;
}

export async function getAppBootstrap(signal?: AbortSignal): Promise<AppBootstrap | null> {
  const result = await api.get<unknown>(DEFAULT_APP_BOOTSTRAP_PATH, {
    signal,
    cacheKey: 'app-bootstrap',
    cacheTtlMs: 30_000,
    timeoutMs: 5000, maxResponseChars: 128 * 1024, retries: 0,
  });
  if (signal?.aborted) return null;
  return result.ok ? bootstrap(result.data) : null;
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

function runtimeStatus(value: unknown, expected?: AppBootstrap | null): AppRuntimeStatus | null {
  if (!object(value) || typeof value.ok !== 'boolean' || value.scope !== 'public-runtime'
    || !text(value.checked_at, 64) || !Number.isFinite(Date.parse(value.checked_at)) || !application(value.application)
    || expected && (value.application.name !== expected.application.name || value.application.version !== expected.application.version)
    || !Array.isArray(value.services) || value.services.length !== 3 || !object(value.product)) return null;
  for (const service of value.services) {
    if (!object(service) || !['backend', 'skeleton', 'mongo'].includes(String(service.name)) || typeof service.ok !== 'boolean'
      || service.status !== null && (!Number.isSafeInteger(service.status) || Number(service.status) < 100 || Number(service.status) > 599)
      || !count(service.latency_ms) || !text(service.detail, 1024)) return null;
    if (service.name === 'skeleton' && service.ok && (!object(service.application)
      || service.application.component !== 'engine' || service.application.ingress_prefix !== '/api/v1'
      || service.application.name !== value.application.name || service.application.version !== value.application.version)) return null;
  }
  if (new Set(value.services.map(service => service.name)).size !== 3 || value.ok !== value.services.every(service => service.ok)) return null;
  const product = value.product;
  if (typeof product.available !== 'boolean' || ['canonical_actions', 'ready_actions', 'governed_unbound', 'unsafe_actions', 'policy_gaps'].some(key => !count(product[key]))
    || Number(product.ready_actions) > Number(product.canonical_actions) || typeof product.ready_pct !== 'number'
    || !Number.isFinite(product.ready_pct) || product.ready_pct < 0 || product.ready_pct > 100
    || typeof product.attestation_sha256 !== 'string' || !/^(?:[a-f0-9]{64})?$/.test(product.attestation_sha256)) return null;
  return value as AppRuntimeStatus;
}

export async function getAppRuntimeStatus(
  timeoutMs = 2_500,
  signal?: AbortSignal,
  bootstrap?: AppBootstrap | null,
): Promise<AppRuntimeStatus | null> {
  const boundedTimeout = Number.isFinite(timeoutMs) ? Math.max(250, Math.min(Math.trunc(timeoutMs), 10_000)) : 2500;
  const path = bootstrap?.contract.status || DEFAULT_APP_STATUS_PATH;
  const result = await api.get<unknown>(
    `${path}?timeout_ms=${encodeURIComponent(String(boundedTimeout))}`,
    {
      signal,
      timeoutMs: boundedTimeout + 500,
      retries: 0,
      cacheKey: 'app-runtime-status',
      cacheTtlMs: 1_000,
      maxResponseChars: 128 * 1024,
    },
  );
  if (signal?.aborted) return null;
  return result.ok ? runtimeStatus(result.data, bootstrap) : null;
}
