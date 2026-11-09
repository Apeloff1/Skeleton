import api from '../utils/apiClient';
import { authHeaders, getAuthToken, getAuthEpoch, checkMe } from '../auth/gameforgeAuth';
import { probeAppHealth, type AppHealthSnapshot } from './appHealthClient';

export type ReadinessCheck = {
  id: string; label: string; status: 'ready' | 'blocked' | 'unknown' | 'sign_in';
  message: string; action?: string;
};
export type AppReadiness = { observedAt: number; accountEpoch: number; checks: ReadinessCheck[]; health: AppHealthSnapshot | null };

function detail(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value.slice(0, 2000) : fallback;
}

function localGuardIssue(data: Record<string, unknown> | null): { message: string; action: string } | null {
  if (!data || data.available !== false || !data.models || typeof data.models !== 'object' || Array.isArray(data.models)
      || !data.checks || typeof data.checks !== 'object' || Array.isArray(data.checks)) return null;
  const models = data.models as Record<string, unknown>;
  const checks = data.checks as Record<string, unknown>;
  if (models.available !== false || !models.readiness || typeof models.readiness !== 'object' || Array.isArray(models.readiness)
      || !checks.models || typeof checks.models !== 'object' || Array.isArray(checks.models)) return null;
  const code = (models.readiness as Record<string, unknown>).code;
  const observed = checks.models as Record<string, unknown>;
  if (observed.available !== false || observed.code !== code) return null;
  if (code === 'local_guard_unavailable') return {
    message: 'Local AI is unavailable because its required trusted guard is not configured.',
    action: 'Preparing or replacing model weights alone will not enable local chat. Ask the installation administrator to complete the trusted local AI setup.',
  };
  if (code === 'local_guard_configuration_invalid') return {
    message: 'The required local AI guard configuration is invalid.',
    action: 'Ask the installation administrator to review the local guard configuration. Do not disable the guard.',
  };
  return null;
}

/** A missing observation is never a positive readiness verdict. A failed observed
 * probe is blocked, while an absent private-service probe remains unknown. */
export function serviceReadinessStatus(item: { ok?: unknown; detail?: unknown } | undefined): ReadinessCheck['status'] {
  if (!item || typeof item !== 'object' || typeof item.ok !== 'boolean'
      || typeof item.detail !== 'string' || item.detail.length > 2000) return 'unknown';
  if (item.ok === true) return 'ready';
  return item.detail.startsWith('observation pending') ? 'unknown' : 'blocked';
}

/** Each verdict belongs to its observed owner; service health never implies AI readiness. */
export async function readAppReadiness(signal?: AbortSignal): Promise<AppReadiness> {
  const healthPromise = probeAppHealth(2500, signal).catch(() => null);
  const epoch = getAuthEpoch();
  const account = await checkMe(signal);
  if (signal?.aborted) throw new Error('Readiness check cancelled.');
  if (epoch !== getAuthEpoch()) throw new Error('Your account changed. Check readiness again.');
  const token = getAuthToken();
  const opts = { signal, headers: authHeaders(), timeoutMs: 12000, maxResponseChars: 1024 * 1024, retries: 0 };
  const inspect = (path: string) => account.observed !== false && account.authenticated
    ? api.get<Record<string, unknown>>(path, opts) : Promise.resolve(null);
  const [healthResult, studio, chat, crawler, dragon] = await Promise.allSettled([
    healthPromise,
    inspect('/api/game-studio-health'),
    inspect('/api/ai/chat/readiness'),
    inspect('/api/dragon-academy/crawler/readiness'),
    inspect('/api/dragon-academy/runtime/readiness'),
  ]);
  if (signal?.aborted) throw new Error('Readiness check cancelled.');
  if (token !== getAuthToken() || epoch !== getAuthEpoch()) throw new Error('Your account changed. Check readiness again.');
  const health = healthResult.status === 'fulfilled' ? healthResult.value : null;
  const checks: ReadinessCheck[] = [];
  for (const name of ['backend', 'skeleton', 'mongo'] as const) {
    const item = health?.services.find(row => row.name === name);
    const serviceStatus = serviceReadinessStatus(item);
    checks.push({ id: name, label: name === 'backend' ? 'Application service' : name === 'mongo' ? 'Database service' : 'AI engine service',
      status: serviceStatus,
      message: serviceStatus === 'ready' ? 'The service responded to its health check.'
        : serviceStatus === 'unknown' ? 'SERVICE_UNOBSERVED: This service was not independently verified; no readiness claim is available.'
        : name === 'mongo' ? 'The application database could not be observed as healthy. Account sign-in and durable work need this service; inspect it before retrying.'
        : 'SERVICE_UNAVAILABLE: The service health probe failed. Inspect host diagnostics before retrying.',
      action: 'python -m skeleton app status --live' });
  }
  const authData = account.observed !== false ? account : null;
  checks.push({ id: 'account', label: 'Your account',
    status: authData?.authenticated === true ? 'ready' : authData ? 'sign_in' : 'unknown',
    message: authData?.authenticated === true ? 'Your account was verified by the application.' : authData?.enforced === false ? 'Local access is allowed, but account-owned chat caches and captured sources still require a verified sign-in.' : authData?.enforced === true ? 'Sign in to use account-owned conversations and captured sources.' : 'The account service could not be checked.' });
  const studioResult = studio.status === 'fulfilled' ? studio.value : null;
  const storage = studioResult?.ok && studioResult.data?.storage && typeof studioResult.data.storage === 'object'
    ? studioResult.data.storage as Record<string, unknown> : null;
  checks.push({ id: 'storage', label: 'Durable storage', status: storage?.connected === true && storage.admitter_configured === true ? 'ready' : storage ? 'blocked' : 'unknown',
    message: storage ? storage.connected !== true ? 'The application database is unavailable.' : storage.admitter_configured !== true ? 'The engine storage admission connection is not configured.' : 'The database and storage admission are configured.' : 'Sign in and refresh to check durable storage.',
    action: 'python -m skeleton app check --runtime' });
  const schemas = { chat: 'backend.ai.chat-readiness.v1', crawler: 'skeleton.dragon.crawler_readiness.v1', dragon: 'skeleton.dragon.runtime_readiness.v1' };
  for (const [id, label, result] of [['chat', 'AI conversations', chat], ['crawler', 'Web capture', crawler], ['dragon', 'Dragon review & reference practice', dragon]] as const) {
    const response = result.status === 'fulfilled' ? result.value : null;
    const data = response?.ok && response.data?.schema_version === schemas[id] && typeof response.data.available === 'boolean' ? response.data : null;
    const signIn = authData !== null && authData.authenticated !== true || response?.status === 401 || response?.status === 403;
    const roleBlocked = id === 'crawler' && data?.available === true && !['editor', 'admin'].includes(account.role);
    const guardIssue = id === 'chat' ? localGuardIssue(data) : null;
    const readyText = id === 'crawler' ? 'Crawler storage and engine admission are reachable. Network access, rights and run limits are checked separately for each capture.'
      : id === 'dragon' ? 'Dragon reference storage and measured local practice are ready. Approval and role permissions remain separate.'
      : 'The conversation store, engine and configured model are ready.';
    const blockedText = id === 'crawler' ? 'Crawler storage or engine admission needs setup. A chat model is not required for web capture.'
      : id === 'dragon' ? 'Dragon persistence or reference practice prerequisites need operator setup. Open Review & practice for the observed checks.'
      : 'AI chat prerequisites are incomplete. Open AI chat for the model catalog or run host diagnostics.';
    checks.push({ id, label, status: signIn ? 'sign_in' : roleBlocked ? 'blocked' : data?.available === true ? 'ready' : data ? 'blocked' : 'unknown',
      message: signIn ? 'Sign in to inspect this capability.' : roleBlocked ? 'Capture infrastructure is ready. An editor or administrator role is required to create or run captures; a viewer can inspect existing sources.' : guardIssue?.message || detail(data?.message, data ? data.available ? readyText : blockedText : 'Readiness has not been observed. Refresh after the application is running.'),
      action: roleBlocked ? 'Ask the configured installation owner to assign an editor role through the existing administrator controls.' : guardIssue?.action || detail(data?.action, id === 'dragon' ? 'Configure private Dragon persistence and enable the operator-approved empty-store bootstrap, then inspect Review & practice.' : id === 'chat' ? 'python -m skeleton app check --runtime' : 'Check database and engine storage admission configuration.') });
  }
  return { observedAt: Date.now(), accountEpoch: epoch, checks, health };
}
