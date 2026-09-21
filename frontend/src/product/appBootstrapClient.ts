import api from '../utils/apiClient';

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
  profiles: {
    default: { services: string[]; layers: string[][] };
    full: { services: string[]; layers: string[][] };
  };
  services: BootstrapService[];
};

export async function getAppBootstrap(signal?: AbortSignal): Promise<AppBootstrap | null> {
  const result = await api.get<AppBootstrap>('/api/app/bootstrap', {
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
