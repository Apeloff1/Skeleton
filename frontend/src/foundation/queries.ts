/**
 * Typed query definitions over existing public API contracts.
 * Parsers are pure so they can be unit-tested without the network.
 */
export interface ApiLike {
  get<T = unknown>(path: string, opts?: { timeoutMs?: number }): Promise<{ ok: boolean; status: number; data: T | null; error: string | null }>;
}

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError'; }
}

export async function getJson<T>(api: ApiLike, path: string, timeoutMs = 15_000): Promise<T> {
  const r = await api.get<T>(path, { timeoutMs });
  if (!r.ok || r.data === null || r.data === undefined) throw new ApiError(r.error || `HTTP ${r.status}`, r.status);
  return r.data;
}

// ── /api/health/overview ────────────────────────────────────────────────
export const OVERVIEW_SUBSYSTEMS = ['registry', 'watchdog', 'cold_storage', 'databases', 'feature_flags', 'deprecations', 'boot'] as const;
export type Subsystem = (typeof OVERVIEW_SUBSYSTEMS)[number];
export interface OverviewSlot { ok: boolean; error?: string; [k: string]: unknown }
export interface OverviewPayload {
  process: { pid: number; python: string; started_at: number; uptime_s: number; deploy_env: 'dev' | 'production' };
  elapsed_ms: number;
  all_green: boolean;
  registry: OverviewSlot; watchdog: OverviewSlot; cold_storage: OverviewSlot; databases: OverviewSlot;
  feature_flags: OverviewSlot; deprecations: OverviewSlot; boot: OverviewSlot;
}
export const overviewKey = ['health', 'overview'] as const;

export function failingSubsystems(data: OverviewPayload | null | undefined): Subsystem[] {
  if (!data) return [];
  return OVERVIEW_SUBSYSTEMS.filter(k => !data[k]?.ok);
}

export type HealthColour = 'green' | 'yellow' | 'red' | 'grey';
export function healthColour(data: OverviewPayload | null | undefined): HealthColour {
  if (!data) return 'grey';
  if (data.all_green) return 'green';
  return failingSubsystems(data).length >= 3 ? 'red' : 'yellow';
}

export function formatUptime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

// ── /api/gameforge/studio/vault/unified ────────────────────────────────
export interface VaultItem {
  id: string; name: string; source: string; kind: string;
  detail?: string; created_at?: number | string; encrypted?: boolean; image?: string;
}
export interface VaultList { items: VaultItem[]; counts: Record<string, number> }
export const vaultKey = (limit: number) => ['vault', 'unified', limit] as const;

export function parseVault(raw: unknown): VaultList {
  const r = (raw && typeof raw === 'object' ? raw : {}) as { ok?: unknown; items?: unknown; counts?: unknown; error?: unknown };
  if (r.ok === false) throw new ApiError(typeof r.error === 'string' ? r.error : 'Vault unavailable', 200);
  const items = Array.isArray(r.items)
    ? r.items.filter((i): i is VaultItem => !!i && typeof i === 'object' && typeof (i as VaultItem).id === 'string')
      .map(i => ({ ...i, name: typeof i.name === 'string' && i.name ? i.name : i.id, source: String(i.source ?? 'unknown'), kind: String(i.kind ?? 'file') }))
    : [];
  const counts: Record<string, number> = {};
  if (r.counts && typeof r.counts === 'object') {
    for (const [k, v] of Object.entries(r.counts as Record<string, unknown>)) if (typeof v === 'number' && Number.isFinite(v)) counts[k] = v;
  }
  return { items, counts };
}
