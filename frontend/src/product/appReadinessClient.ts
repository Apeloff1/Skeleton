import api from '../utils/apiClient';
import { authHeaders, getAuthToken, checkMe } from '../auth/gameforgeAuth';
import { probeAppHealth, type AppHealthSnapshot } from './appHealthClient';

export type ReadinessCheck = {
  id: string; label: string; status: 'ready' | 'blocked' | 'unknown' | 'sign_in';
  message: string; action?: string;
};
export type AppReadiness = { observedAt: number; checks: ReadinessCheck[]; health: AppHealthSnapshot | null };

function detail(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value.slice(0, 2000) : fallback;
}

/** Each verdict belongs to its observed owner; service health never implies AI readiness. */
export async function readAppReadiness(signal?: AbortSignal): Promise<AppReadiness> {
  const healthPromise = probeAppHealth(2500, signal).catch(() => null);
  const account = await checkMe();
  const token = getAuthToken();
  const opts = { signal, headers: authHeaders(), timeoutMs: 12000, retries: 0 };
  const [healthResult, studio, chat, crawler] = await Promise.allSettled([
    healthPromise,
    api.get<Record<string, unknown>>('/api/game-studio-health', opts),
    api.get<Record<string, unknown>>('/api/ai/chat/readiness', opts),
    api.get<Record<string, unknown>>('/api/dragon-academy/crawler/readiness', opts),
  ]);
  if (signal?.aborted) throw new Error('Readiness check cancelled.');
  if (token !== getAuthToken()) throw new Error('Your account changed. Check readiness again.');
  const health = healthResult.status === 'fulfilled' ? healthResult.value : null;
  const checks: ReadinessCheck[] = [];
  for (const name of ['backend', 'skeleton'] as const) {
    const item = health?.services.find(row => row.name === name);
    checks.push({ id: name, label: name === 'backend' ? 'Application service' : 'AI engine service',
      status: item?.ok ? 'ready' : item ? 'blocked' : 'unknown',
      message: item?.ok ? 'The service responded to its health check.' : 'The service could not be reached. Start the installed application and check its status.',
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
  for (const [id, label, result] of [['chat', 'AI conversations', chat], ['crawler', 'Web capture', crawler]] as const) {
    const response = result.status === 'fulfilled' ? result.value : null;
    const data = response?.ok ? response.data : null;
    checks.push({ id, label, status: data?.available === true ? 'ready' : response?.status === 401 || response?.status === 403 ? 'sign_in' : data && typeof data.available === 'boolean' ? 'blocked' : 'unknown',
      message: detail(data?.message, id === 'chat' && data && typeof data.available === 'boolean' ? data.available ? 'The conversation store, engine and configured model are ready.' : 'AI chat prerequisites are incomplete. Open AI chat for the model catalog or run host diagnostics.' : response?.status === 401 || response?.status === 403 ? 'Sign in to inspect this capability.' : 'Readiness has not been observed. Refresh after the application is running.'),
      action: detail(data?.action, id === 'chat' ? 'python -m skeleton app check --runtime' : 'Check database and engine storage admission configuration.') });
  }
  return { observedAt: Date.now(), checks, health };
}
