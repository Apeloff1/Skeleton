import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { API_BASE } from '../utils/apiBase';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';

export type CrawlerReadiness = { available: boolean; configured: boolean; code: string; message: string; action?: string | null; network_reachability_verified?: boolean; limits: Record<string, number>; capabilities: Record<string, boolean> };
export type CrawlUsage = { requests: number; bytes: number; documents: number; failures: number; reserved_bytes?: number };
export type CrawlAutomation = {
  enabled: boolean; state: 'authorized' | 'running' | 'waiting' | 'stopped' | 'disabled' | 'blocked' | 'not_authorized';
  epoch: number; slices_started: number; max_slices: number;
  expires_at: string | null; next_run_at: string | null; stop_reason: string | null;
};
export type CrawlWorker = { active: boolean; quiescent: boolean; local: boolean; lease_until: string | null; confirmation?: string; recovery_eligible?: boolean };
export type CrawlCapabilities = { can_run: boolean; can_pause: boolean; can_resume: boolean; can_cancel: boolean; can_erase: boolean; can_automate: boolean };
export type CrawlSession = {
  session_id: string; title: string; status: 'queued' | 'ready' | 'running' | 'paused' | 'completed' | 'cancelled' | 'budget_exhausted' | 'failed' | 'interrupted';
  state?: string; version: number; created_at: string; updated_at: string; seeds: string[];
  limits: { max_requests: number; max_documents: number; max_total_bytes: number; max_depth: number; [key: string]: unknown };
  counters: CrawlUsage; frontier_count: number; source_count: number; consent_current: boolean; consent_expires_at: string;
  next_ready_at?: number | null; stop_reason?: string | null; error?: { code?: string; message?: string } | null;
  automation?: CrawlAutomation; worker?: CrawlWorker; capabilities?: CrawlCapabilities;
  queue: { url: string; depth: number; attempts: number; ready_at: number }[];
};
export type SourceUsePolicy = { version: number; enabled: boolean; max_age_seconds: number; changed_at: string | null };
export type SourceFreshness = {
  usable: boolean; state: 'current' | 'withdrawn' | 'stale' | 'consent_expired' | 'session_revoked' | 'capture_time_invalid';
  capture_age_seconds: number; valid_until: string; remote_freshness_verified: false;
};
export type CapturedSource = { source_id: string; url: string; canonical_url?: string; title: string; text?: string; content_digest: string; fetched_at: string; review_state: string; provenance: Record<string, unknown>; text_truncated?: boolean; use_policy?: SourceUsePolicy; freshness?: SourceFreshness };
export type CrawlCreate = { idempotency_key: string; seeds: string[]; title?: string; topics: string[]; max_requests: number; max_documents: number; max_bytes: number; max_depth: number; consent: true; rights_acknowledged: true };
export type CrawlCommand = { idempotency_key: string; expected_version: number };
export type SourceExport = { filename: string; media_type: string; content: string; content_digest: string; session_id: string; source_id: string };
const ROOT = '/api/dragon-academy/crawler';
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const HASH = /^[a-f0-9]{64}$/;
const STATUSES = new Set(['queued', 'ready', 'running', 'paused', 'completed', 'cancelled', 'budget_exhausted', 'failed', 'interrupted']);
export function crawlRequestKey(action: string): string { return 'crawler:' + action + ':' + (globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + '-' + Math.random().toString(36).slice(2)); }
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function identifier(value: string): string { if (!ID.test(value)) invalid('The crawler identity is invalid.'); return encodeURIComponent(value); }
function integer(value: unknown, maximum = Number.MAX_SAFE_INTEGER): boolean { return Number.isSafeInteger(value) && (value as number) >= 0 && (value as number) <= maximum; }
async function read<T>(operation: Promise<ApiResult<T>>, token: string, message: string): Promise<T> {
  const result = await operation;
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen web capture.', { kind: 'authorization', retryable: false });
  if (!result.ok || !result.data) throw chatApiError(result, message);
  return result.data;
}
function options(signal?: AbortSignal) { return { signal, headers: authHeaders(), timeoutMs: 65000, retries: 0 }; }
function session(value: CrawlSession, expectedId?: string): CrawlSession {
  if (!value || !ID.test(value.session_id) || expectedId && value.session_id !== expectedId || !STATUSES.has(value.status)
    || !integer(value.version) || value.version < 1 || typeof value.title !== 'string' || value.title.length > 160
    || !Array.isArray(value.seeds) || value.seeds.length > 16 || value.seeds.some(url => typeof url !== 'string' || url.length > 4096)
    || !value.limits || !value.counters || !integer(value.frontier_count) || !integer(value.source_count, 64)
    || typeof value.consent_current !== 'boolean' || !Number.isFinite(Date.parse(value.consent_expires_at))
    || !Array.isArray(value.queue) || value.queue.length > 32 || JSON.stringify(value).length > 512 * 1024) invalid('The crawler returned an invalid session projection.');
  for (const count of Object.values(value.counters)) if (!integer(count, 33554432)) invalid('The crawler counters are invalid.');
  for (const field of ['requests', 'bytes', 'documents', 'failures'] as const) if (!integer(value.counters[field], 33554432)) invalid('The crawler counters are incomplete.');
  for (const row of value.queue) if (!row || typeof row.url !== 'string' || row.url.length > 4096 || !integer(row.depth, 3) || !integer(row.attempts, 128) || typeof row.ready_at !== 'number' || !Number.isFinite(row.ready_at)) invalid('The crawler queue is invalid.');
  if (value.automation) {
    const a = value.automation;
    if (typeof a.enabled !== 'boolean' || !['authorized', 'running', 'waiting', 'stopped', 'disabled', 'blocked', 'not_authorized'].includes(a.state)
      || !integer(a.epoch) || !integer(a.slices_started, 64) || !integer(a.max_slices, 64) || a.slices_started > a.max_slices
      || a.enabled && a.max_slices < 1 || a.expires_at !== null && !Number.isFinite(Date.parse(a.expires_at))
      || a.next_run_at !== null && !Number.isFinite(Date.parse(a.next_run_at))
      || a.stop_reason !== null && (typeof a.stop_reason !== 'string' || a.stop_reason.length > 4096)) invalid('The crawler automation authorization is invalid.');
  }
  if (value.worker && (['active', 'quiescent', 'local'].some(key => typeof value.worker![key as keyof CrawlWorker] !== 'boolean')
    || value.worker.lease_until !== null && !Number.isFinite(Date.parse(value.worker.lease_until))
    || value.worker.confirmation !== undefined && (typeof value.worker.confirmation !== 'string' || value.worker.confirmation.length > 256)
    || value.worker.recovery_eligible !== undefined && typeof value.worker.recovery_eligible !== 'boolean')) invalid('The crawler worker projection is invalid.');
  if (value.capabilities && ['can_run', 'can_pause', 'can_resume', 'can_cancel', 'can_erase', 'can_automate'].some(key => typeof value.capabilities![key as keyof CrawlCapabilities] !== 'boolean')) invalid('The crawler command capabilities are invalid.');
  return value;
}
function source(value: CapturedSource, id?: string): CapturedSource {
  if (!value || !ID.test(value.source_id) || id && value.source_id !== id || typeof value.url !== 'string' || value.url.length > 4096 || typeof value.title !== 'string'
    || !HASH.test(value.content_digest) || typeof value.review_state !== 'string' || !value.provenance || typeof value.provenance !== 'object'
    || value.text !== undefined && (typeof value.text !== 'string' || new TextEncoder().encode(value.text).byteLength > 2 * 1024 * 1024)) invalid('The captured source projection is invalid.');
  if ((value.use_policy === undefined) !== (value.freshness === undefined)) invalid('The source-use projection is incomplete.');
  if (value.use_policy && value.freshness) {
    const policy = value.use_policy, freshness = value.freshness;
    if (!integer(policy.version, 2147483647) || typeof policy.enabled !== 'boolean' || !integer(policy.max_age_seconds, 86400) || policy.max_age_seconds < 60
      || policy.changed_at !== null && (typeof policy.changed_at !== 'string' || !Number.isFinite(Date.parse(policy.changed_at)))
      || policy.version === 0 && policy.changed_at !== null || policy.version > 0 && policy.changed_at === null
      || typeof freshness.usable !== 'boolean' || !['current', 'withdrawn', 'stale', 'consent_expired', 'session_revoked', 'capture_time_invalid'].includes(freshness.state)
      || freshness.usable !== (freshness.state === 'current') || freshness.usable && !policy.enabled
      || !integer(freshness.capture_age_seconds) || typeof freshness.valid_until !== 'string' || !Number.isFinite(Date.parse(freshness.valid_until))
      || freshness.remote_freshness_verified !== false) invalid('The source-use or capture-age projection is invalid.');
  }
  return value;
}
export async function getCrawlerReadiness(signal?: AbortSignal): Promise<CrawlerReadiness> {
  const value = await read(api.get<CrawlerReadiness>(ROOT + '/readiness', options(signal)), getAuthToken(), 'Crawler readiness is unavailable.');
  if (!value || typeof value.available !== 'boolean' || typeof value.configured !== 'boolean' || typeof value.message !== 'string' || !value.capabilities || !value.limits) invalid('The crawler readiness projection is invalid.');
  return value;
}
export async function listCrawls(cursor?: string, signal?: AbortSignal): Promise<{ sessions: CrawlSession[]; next_cursor: string | null }> {
  const value = await read(api.get<{ sessions: CrawlSession[]; next_cursor: string | null }>(ROOT + '/sessions?limit=32' + (cursor ? '&cursor=' + identifier(cursor) : ''), options(signal)), getAuthToken(), 'Your crawler sessions could not be loaded.');
  if (!Array.isArray(value.sessions) || value.sessions.length > 32 || value.next_cursor !== null && !ID.test(value.next_cursor)) invalid('The crawler session page is invalid.');
  value.sessions.forEach(row => session(row)); return value;
}
export async function getCrawl(id: string, signal?: AbortSignal): Promise<CrawlSession> {
  const value = await read(api.get<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id), options(signal)), getAuthToken(), 'The crawler session could not be refreshed.'); return session(value.session, id);
}
export async function createCrawl(body: CrawlCreate, signal?: AbortSignal): Promise<CrawlSession> {
  if (body.seeds.length < 1 || body.seeds.length > 16 || new Set(body.seeds).size !== body.seeds.length || body.consent !== true || body.rights_acknowledged !== true) throw new ChatClientError('Provide distinct seed URLs and acknowledge capture rights.', { kind: 'validation' });
  for (const seed of body.seeds) { let url: URL; try { url = new URL(seed); } catch { throw new ChatClientError('Enter complete http or https seed URLs, one per line.', { kind: 'validation' }); } if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || seed.length > 2048) throw new ChatClientError('Use http or https URLs without embedded credentials.', { kind: 'validation' }); }
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions', body, options(signal)), getAuthToken(), 'The crawl could not be created. Retry the same request to check its outcome.'); return session(value.session);
}
export async function runCrawl(id: string, body: CrawlCommand & { max_steps: number }, signal?: AbortSignal): Promise<CrawlSession> {
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id) + '/run', body, options(signal)), getAuthToken(), 'The bounded slice did not return a confirmed result. Refresh or retry the same request.'); return session(value.session, id);
}
export async function controlCrawl(id: string, body: CrawlCommand & { action: 'pause' | 'resume' | 'cancel' }, signal?: AbortSignal): Promise<CrawlSession> {
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id) + '/control', body, options(signal)), getAuthToken(), 'The crawler control was not confirmed. Refresh before another command.'); return session(value.session, id);
}
export async function listCrawlSources(id: string, cursor?: string, signal?: AbortSignal): Promise<{ sources: CapturedSource[]; next_cursor: string | null }> {
  const value = await read(api.get<{ sources: CapturedSource[]; next_cursor: string | null }>(ROOT + '/sessions/' + identifier(id) + '/sources?limit=32' + (cursor ? '&cursor=' + identifier(cursor) : ''), options(signal)), getAuthToken(), 'Captured sources could not be loaded.');
  if (!Array.isArray(value.sources) || value.sources.length > 32 || value.next_cursor !== null && !ID.test(value.next_cursor)) invalid('The source page is invalid.'); value.sources.forEach(row => source(row)); return value;
}
export async function getCrawlSource(id: string, sourceId: string, signal?: AbortSignal): Promise<CapturedSource> {
  const value = await read(api.get<{ source: CapturedSource }>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId), options(signal)), getAuthToken(), 'The captured source could not be read.'); return source(value.source, sourceId);
}
export async function configureCrawlSourceUse(id: string, sourceId: string, body: CrawlCommand & { enabled: boolean; max_age_seconds: number }, signal?: AbortSignal): Promise<{ session: CrawlSession; source: CapturedSource }> {
  if (!HASH.test(sourceId) || !integer(body.expected_version) || body.expected_version < 1 || typeof body.enabled !== 'boolean'
    || !integer(body.max_age_seconds, 86400) || body.max_age_seconds < 60 || typeof body.idempotency_key !== 'string'
    || !body.idempotency_key || body.idempotency_key !== body.idempotency_key.trim() || body.idempotency_key.length > 128) {
    throw new ChatClientError('Choose a current source and a capture-age limit between 60 and 86,400 seconds.', { kind: 'validation' });
  }
  const value = await read(api.post<{ session: CrawlSession; source: CapturedSource }>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId) + '/use', body, options(signal)), getAuthToken(), 'The source-use change was not confirmed. Retry the same saved change or refresh current settings.');
  session(value.session, id); source(value.source, sourceId);
  if (!value.source.use_policy || !value.source.freshness || value.source.text !== undefined) invalid('The source-use change returned an incomplete receipt.');
  return value;
}
export async function exportCrawlSource(id: string, sourceId: string, format: 'json' | 'markdown', signal?: AbortSignal): Promise<SourceExport> {
  const token = getAuthToken();
  const value = await read(api.get<SourceExport>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId) + '/export?format=' + format, options(signal)), getAuthToken(), 'The source export could not be authorized.');
  if (!value || value.session_id !== id || value.source_id !== sourceId || typeof value.content !== 'string' || new TextEncoder().encode(value.content).byteLength > 2 * 1024 * 1024 || !HASH.test(value.content_digest) || typeof value.filename !== 'string' || !['application/json', 'text/markdown'].includes(value.media_type.split(';')[0].trim())) invalid('The source export is invalid.');
  if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, value.content) !== value.content_digest) invalid('The source export content changed.'); if (signal?.aborted || token !== getAuthToken()) throw new ChatClientError('Your account changed or the export was detached.', { kind: 'authorization' }); return value;
}

export type CrawlEvent = { sequence: number; kind: string; at: number; url?: string | null; source_id?: string | null; reason?: string | null };
export async function getCrawlEvents(id: string, signal?: AbortSignal): Promise<{ events: CrawlEvent[]; history_truncated: boolean }> {
  const value = await read(api.get<{ session_id: string; events: CrawlEvent[]; history_truncated: boolean }>(ROOT + '/sessions/' + identifier(id) + '/events?after_sequence=0&limit=64', options(signal)), getAuthToken(), 'Crawler event history could not be loaded.');
  if (value.session_id !== id || !Array.isArray(value.events) || value.events.length > 64 || typeof value.history_truncated !== 'boolean') invalid('The crawler event page is invalid.');
  let previous = 0;
  for (const event of value.events) { if (!event || !integer(event.sequence) || event.sequence <= previous || typeof event.kind !== 'string' || event.kind.length > 128 || typeof event.at !== 'number' || !Number.isFinite(event.at) || event.url != null && (typeof event.url !== 'string' || event.url.length > 4096) || event.reason != null && (typeof event.reason !== 'string' || event.reason.length > 4096)) invalid('The crawler event sequence is invalid.'); previous = event.sequence; }
  return value;
}
export async function eraseCrawl(id: string, body: CrawlCommand, signal?: AbortSignal): Promise<void> {
  const token = getAuthToken(); const current = new AbortController(); const stop = () => current.abort(); signal?.addEventListener('abort', stop, { once: true }); const timer = setTimeout(stop, 30000);
  try {
    if (signal?.aborted) throw new ChatClientError('Request detached.', { kind: 'cancelled' });
    const response = await fetch(API_BASE + ROOT + '/sessions/' + identifier(id), { method: 'DELETE', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body), signal: current.signal });
    if (token !== getAuthToken()) throw new ChatClientError('Your account changed.', { kind: 'authorization' });
    const text = await response.text(); if (text.length > 65536) invalid('The crawler deletion receipt exceeds its bound.');
    let value: { session_id?: string; status?: string; version?: number; detail?: unknown }; try { value = JSON.parse(text); } catch { invalid('The crawler deletion receipt is invalid.'); }
    if (!response.ok) throw chatApiError({ ok: false, status: response.status, data: value, error: null, rid: response.headers.get('x-request-id') }, 'Source erasure was not confirmed. Retry the same command.');
    if (value.session_id !== id || value.status !== 'deleted' || !integer(value.version)) invalid('The crawler deletion receipt belongs to another session.');
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', stop); }
}


export type CrawlTextPage = {
  session_id: string; source_id: string; version: number; offset: number; end: number; total_chars: number;
  text: string; next_offset: number | null; content_digest: string; chunk_digest: string;
  offset_unit: 'unicode_code_points'; source_classification: string;
};
export type CrawlSearchHit = {
  source_id: string; canonical_url: string; title: string; content_hash: string; preserved_text_hash: string;
  passage_hash: string; start: number; end: number; text: string; lexical_score: number;
  review_state: string; authority: string; instruction_risks: { risk: string; start: number; end: number; detail: string }[];
};
export type CrawlSearchPage = { schema_version: string; run_id: string; session_id: string; version: number; query: string; hits: CrawlSearchHit[]; evidence_digest: string };
export async function authorizeCrawlAutomation(id: string, body: CrawlCommand & { enabled: boolean; max_slices: number; max_seconds: number }, signal?: AbortSignal): Promise<CrawlSession> {
  if (typeof body.enabled !== 'boolean' || !integer(body.max_slices, 64) || body.max_slices < 1 || !integer(body.max_seconds, 3600) || body.max_seconds < 15) throw new ChatClientError('Choose 1–64 bounded slices and 15–3,600 seconds.', { kind: 'validation' });
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id) + '/automation', body, options(signal)), getAuthToken(), 'Automatic capture was not confirmed. Retry the same saved request or refresh its state.');
  return session(value.session, id);
}
export async function getCrawlText(id: string, sourceId: string, offset = 0, digest?: string, signal?: AbortSignal): Promise<CrawlTextPage> {
  if (!integer(offset, 2097152) || digest !== undefined && !HASH.test(digest)) invalid('The source text cursor is invalid.');
  const token = getAuthToken();
  const value = await read(api.get<CrawlTextPage>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId) + '/text?offset=' + offset + '&max_chars=8000' + (digest ? '&expected_content_digest=' + digest : ''), options(signal)), token, 'The preserved source passage could not be read.');
  if (!value || value.session_id !== id || value.source_id !== sourceId || !integer(value.version) || value.offset !== offset || value.offset_unit !== 'unicode_code_points'
    || !integer(value.end, 2097152) || !integer(value.total_chars, 2097152) || value.end < offset || value.end > value.total_chars
    || typeof value.text !== 'string' || Array.from(value.text).length !== value.end - offset || new TextEncoder().encode(value.text).byteLength > 64000
    || !HASH.test(value.content_digest) || digest && value.content_digest !== digest || !HASH.test(value.chunk_digest)
    || value.next_offset !== null && (value.next_offset !== value.end || value.end >= value.total_chars)
    || value.next_offset === null && value.end !== value.total_chars || typeof value.source_classification !== 'string') invalid('The preserved source text page is invalid.');
  const measured = await digestStringAsync(CryptoDigestAlgorithm.SHA256, value.text);
  if (signal?.aborted || token !== getAuthToken()) throw new ChatClientError('The source read was detached or your account changed.', { kind: 'authorization' });
  if (measured !== value.chunk_digest) invalid('The preserved source text bytes changed.');
  return value;
}
export async function searchCrawlSources(id: string, query: string, signal?: AbortSignal): Promise<CrawlSearchPage> {
  const text = query.trim(); if (!text || text.length > 512) throw new ChatClientError('Enter a source query of 1–512 characters.', { kind: 'validation' });
  const token = getAuthToken();
  const value = await read(api.get<CrawlSearchPage>(ROOT + '/sessions/' + identifier(id) + '/search?query=' + encodeURIComponent(text) + '&limit=8', options(signal)), getAuthToken(), 'The captured source search could not be read.');
  if (!value || value.session_id !== id || value.query !== text || typeof value.schema_version !== 'string' || !integer(value.version) || !HASH.test(value.evidence_digest) || !Array.isArray(value.hits) || value.hits.length > 8) invalid('The source search returned an invalid scope.');
  for (const hit of value.hits) {
    if (!hit || !ID.test(hit.source_id) || typeof hit.canonical_url !== 'string' || hit.canonical_url.length > 4096 || typeof hit.title !== 'string'
      || !HASH.test(hit.content_hash) || !HASH.test(hit.preserved_text_hash) || !HASH.test(hit.passage_hash) || !integer(hit.start, 2097152) || !integer(hit.end, 2097152)
      || hit.end <= hit.start || typeof hit.text !== 'string' || Array.from(hit.text).length !== hit.end - hit.start || hit.text.length > 16000
      || typeof hit.lexical_score !== 'number' || !Number.isFinite(hit.lexical_score) || typeof hit.review_state !== 'string' || typeof hit.authority !== 'string'
      || !Array.isArray(hit.instruction_risks) || hit.instruction_risks.length > 32 || hit.instruction_risks.some(risk => !risk || typeof risk.risk !== 'string' || risk.risk.length > 256 || typeof risk.detail !== 'string' || risk.detail.length > 4096 || !integer(risk.start, 16000) || !integer(risk.end, 16000) || risk.end < risk.start)) invalid('A source search passage is invalid.');
    if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, hit.text) !== hit.passage_hash) invalid('The captured search passage bytes changed.');
    if (signal?.aborted || token !== getAuthToken()) throw new ChatClientError('The source search was detached or your account changed.', { kind: 'authorization' });
  }
  return value;
}
