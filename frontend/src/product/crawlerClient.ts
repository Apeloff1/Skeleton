import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { API_BASE } from '../../utils/apiBase';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';

export type CrawlerReadiness = { available: boolean; configured: boolean; code: string; message: string; action?: string | null; network_reachability_verified?: boolean; limits: Record<string, number>; capabilities: Record<string, boolean> };
export type CrawlUsage = { requests: number; bytes: number; documents: number; failures: number; reserved_bytes?: number };
export type CrawlSession = {
  session_id: string; title: string; status: 'queued' | 'ready' | 'running' | 'paused' | 'completed' | 'cancelled' | 'budget_exhausted' | 'failed' | 'interrupted';
  state?: string; version: number; created_at: string; updated_at: string; seeds: string[];
  limits: { max_requests: number; max_documents: number; max_total_bytes: number; max_depth: number; [key: string]: unknown };
  counters: CrawlUsage; frontier_count: number; source_count: number; consent_current: boolean; consent_expires_at: string;
  next_ready_at?: number | null; stop_reason?: string | null; error?: { code?: string; message?: string } | null;
  queue: { url: string; depth: number; attempts: number; ready_at: number }[];
};
export type CapturedSource = { source_id: string; url: string; canonical_url?: string; title: string; text?: string; content_digest: string; fetched_at: string; review_state: string; provenance: Record<string, unknown>; text_truncated?: boolean };
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
  return value;
}
function source(value: CapturedSource, id?: string): CapturedSource {
  if (!value || !ID.test(value.source_id) || id && value.source_id !== id || typeof value.url !== 'string' || value.url.length > 4096 || typeof value.title !== 'string'
    || !HASH.test(value.content_digest) || typeof value.review_state !== 'string' || !value.provenance || typeof value.provenance !== 'object'
    || value.text !== undefined && (typeof value.text !== 'string' || new TextEncoder().encode(value.text).byteLength > 2 * 1024 * 1024)) invalid('The captured source projection is invalid.');
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
