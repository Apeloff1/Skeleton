import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { API_BASE } from '../utils/apiBase';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { canonicalPilotReceipt, pilotReceiptBody } from './crawlerPilotReceipt';

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
export type CrawlCreate = { idempotency_key: string; seeds: string[]; title?: string; topics: string[]; max_requests: number; max_documents: number; max_bytes: number; max_depth: number; discover_sitemaps?: boolean; frontier_strategy?: 'fifo' | 'balanced'; consent: true; rights_acknowledged: true };
export type CrawlCommand = { idempotency_key: string; expected_version: number };
export type SourceExport = { filename: string; media_type: string; content: string; content_digest: string; session_id: string; source_id: string };
const ROOT = '/api/dragon-academy/crawler';
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const HASH = /^[a-f0-9]{64}$/;
const OPERATION_STAGE_NAMES = [
  'exact_canonical_event_timeline',
  'per_origin_robots_and_cooldown_safety',
  'physical_worker_restart_and_cas_witness',
  'measured_resource_capacity_envelope',
  'opaque_bounded_dispatch_preflight',
  'review_only_operator_recovery_runbook',
] as const;
const FORENSIC_STAGE_NAMES = [
  'exact_selected_source_custody',
  'source_text_security_inspection',
  'anchored_passage_geometry',
  'possible_source_reuse',
  'objective_failure_counterfactual',
  'source_boilerplate_screening',
  'bounded_capture_age_analysis',
  'cross_source_sentence_echoes',
  'active_content_render_risk',
  'privacy_and_secret_exposure',
  'objective_host_concentration',
  'possible_polarity_collisions',
  'canonical_capture_provenance_posture',
  'operator_objective_grounding',
  'selected_reference_concentration',
  'mandate_consent_horizon',
  'reverse_source_objective_usage',
  'policy_bound_research_deficit_matrix',
  'untrusted_context_resource_budget',
  'captured_extraction_quality_diagnostics',
  'operator_query_rank_support_audit',
  'captured_origin_redirect_hygiene',
  'objective_selection_fairness_metrics',
  'conservative_risky_source_ablation',
  'script_coverage_lexical_limitations',
  'review_only_forensic_queue',
] as const;

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
  if (body.frontier_strategy !== undefined && !['fifo', 'balanced'].includes(body.frontier_strategy)) throw new ChatClientError('Choose a canonical bounded frontier scheduling strategy.', { kind: 'validation' });
  if (body.discover_sitemaps !== undefined && typeof body.discover_sitemaps !== 'boolean') throw new ChatClientError('Sitemap discovery must be explicitly enabled or disabled.', { kind: 'validation' });
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


// Dragon Atlas is a read-only, owner-scoped research inspection. Its
// hashes are integrity identifiers, never reviewed-knowledge authorization.
export type CrawlAtlasObjective = {
  objective_id: string;
  question: string;
  dimension: 'fact' | 'method' | 'timeline' | 'source' | 'counterexample' | 'implementation';
  stage: 'discovery' | 'collection' | 'verification' | 'review';
  priority: number;
  minimum_reviewable_passages: number;
  minimum_attested_groups: number;
  max_source_age_seconds: number;
  required_terms: string[];
  blocked_terms: string[];
};
export type CrawlAtlasEffort = {
  task_type: 'source_policy' | 'passage_integrity' | 'source_provenance' |
    'claim_contradiction' | 'claim_corroboration' | 'objective_gap' | 'human_fact_review';
  estimated_minutes: number;
  estimate_basis: 'operator_estimate';
};
export type CrawlAtlasRequest = {
  objectives: CrawlAtlasObjective[];
  retrieval_mode: 'fusion' | 'lexical_bm25';
  review_effort?: CrawlAtlasEffort[];
  review_budget_minutes?: number;
};
export type CrawlAtlasStage = {
  ordinal: number; name: string; receipt_digest: string; chain_digest: string;
};
export type CrawlAtlasReviewTask = {
  task_id: string; type: string; objective_id: string | null;
  source_id: string | null; priority: number; predecessors: string[];
  current_status: 'pending_human_review'; automatically_approvable: false;
};
export type CrawlPilotQualification = {
  schema_version: 'skeleton.dragon.campaign_pilot_qualification.v1';
  atlas_digest: string; snapshot_digest: string; source_policy_digest: string;
  run_sequence: number; pilot_status: 'ready_for_human_review' | 'held_for_repair';
  pilot_check_count: number;
  checks: { code: string; status: 'qualified' | 'held'; next_action: string | null }[];
  blocked_checks: string[]; operator_actions: string[];
  external_release_checks: { code: string; status: 'not_qualified' }[];
  source_only: true; read_only: true; human_review_required: true;
  network_used: false; model_invoked: false; source_text_included: false;
  training_authorized: false; publication_authorized: false; release_authorized: false;
  release_status: 'held_until_independent_exact_head_and_device_evidence';
  recheck_mongo_authority_before_any_followup: true; qualification_digest: string;
};
export type CrawlAtlasReport = {
  schema_version: 'skeleton.dragon.campaign_atlas_dashboard.v1';
  session_id: string; run_id: string; run_sequence: number;
  snapshot_digest: string; mandate_digest: string; atlas_digest: string;
  issued_at: number; dashboard_digest: string; stages: CrawlAtlasStage[];
  source_policy: {
    digest: string; sources_seen: number; included_source_count: number;
    excluded_source_count: number; complete_current_policy_required: true;
  };
  objectives: {
    objective_id: string; dimension: string; stage: string; priority: number;
  }[];
  query_lattice: { digest: string; queries: number; source_authority: string };
  retrieval: {
    digest: string; mode: 'fusion' | 'lexical_bm25';
    candidate_passages: number; retained_hits: number; distinct_hosts: number;
    evidence: {
      source_id: string; canonical_url: string; passage_hash: string;
      start: number; end: number; score: number;
      objective_ids: string[]; review_required: true;
    }[];
  };
  lexical_ranking: null | {
    ranking_digest: string; indexed_passages: number; scored_passages: number;
    scored_query_receipts: number; indexed_terms: number;
    ai_embedding_used: false; model_confidence_certified: false;
  };
  context: {
    digest: string; source_references: number; serialized_bytes: number;
    raw_source_text_redacted: true; fresh_policy_recheck_required: true;
  };
  numeric_signals: {
    report_digest: string; observed_quantities: number;
    cross_source_review_candidates: number; unit_families: string[];
    candidates: {
      objective_id: string; left_source_id: string; right_source_id: string;
      left_span_start: number; right_span_start: number;
      unit_family: string; normalized_left: string; normalized_right: string;
      relative_gap: number; human_review_required: true;
      factual_contradiction_established: false;
    }[];
    facts_verified: false;
  };
  temporal_signals: {
    report_digest: string; date_mentions: number; date_groups: number;
    groups: {
      objective_id: string; date: string; source_count: number;
      date_not_verified_as_remote_update: true;
    }[];
    remote_freshness_verified: false;
  };
  evidence_graph: {
    graph_digest: string; vertices: number; arcs: number; retained_passages: number;
    sources: number; held_sources: number; graph_is_factual_proof: false;
    objective_neighborhoods: {
      objective_id: string; source_count: number; passage_count: number;
      host_count: number; claim_count: number; independence_attested: false;
    }[];
  };
  review_operations: {
    agenda_digest: string; replay_digest: string; tasks_total: number;
    pending_tasks: number; blocked_tasks: number; ready_task_ids: string[];
    task_types: Record<string, number>;
    recommended_queue: CrawlAtlasReviewTask[];
    human_review_recorded: false; durable_review_mutations: false;
  };
  review_portfolio: null | {
    portfolio_digest: string; estimated_minutes: number; budget_minutes: number;
    selected_count: number; task_ids: string[]; persistence_performed: false;
    effort_is_observed: false;
  };
  jeeves_handoff: {
    manifest_digest: string; citation_count: number; task_count: number;
    body_excluded: true; network_called: false; dispatch_granted: false;
    requires_fresh_source_policy: true;
  };
  citation_manifest: {
    manifest_digest: string; exact_anchored_references: number;
    body_redacted: true; publication_permission: false;
  };
  forensics: {
    report_digest: string; frame_set_digest: string; atlas_digest: string;
    source_policy_digest: string; retrieval_digest: string;
    stages: CrawlAtlasStage[];
    selected_passages: number; selected_sources: number;
    security_held_passages: number; security_held_sources: number;
    active_content_held_sources: number; privacy_held_sources: number;
    cross_host_sentence_echoes: number; source_reuse_components: number;
    possible_polarity_collisions: number; low_information_passages: number;
    capture_age_held_sources: number; overlap_excess_characters: number;
    concentrated_objectives: string[]; review_tasks: number;
    provenance_held_sources: number; grounding_deficit_objectives: number;
    reference_reused_sources: number; consent_renewal_review_due: boolean;
    urgent_research_gaps: number; context_selected_utf8_bytes: number;
    context_budget_exceeded: boolean;
    extraction_held_sources: number; query_unsupported_objectives: number;
    origin_review_sources: number; selection_source_dominance_objectives: number;
    risk_ablated_objectives: number; script_coverage_review_objectives: number;
    critical_review_tasks: number;
    review_queue: {
      task_id: string; risk: 'critical' | 'high' | 'medium' | 'low';
      reason: string; source_ids: string[]; objective_ids: string[];
      model_may_decide: false;
    }[];
    source_bodies_redacted: true; human_review_required: true;
    publication_granted: false; training_permission: false;
    network_or_model_invoked: false;
  };
  operations: {
    report_digest: string; source_snapshot_digest: string; run_sequence: number;
    stages: CrawlAtlasStage[];
    retained_event_count: number; historical_events_incomplete: boolean;
    event_clock_integrity_review: boolean; pending_dispatch: boolean;
    uncertain_bytes: number; inspected_origins: number;
    unresolved_robots_origins: number; stale_robots_origins: number;
    observed_resource_samples: number; hypothetical_work_candidates: number;
    capacity_holds: string[]; critical_operator_steps: number;
    operator_runbook: {
      code: string; priority: 'critical' | 'high' | 'medium' | 'advisory';
      requires_backend_authority: true; automatically_executed: false;
    }[];
    physical_worker_fenced: false; mongo_checkpoint_confirmed: false;
    live_robots_permission_granted: false; network_executed: false;
    source_text_redacted: true; read_only: true;
    automatic_recovery_authorized: false;
  };
  evidence_family_stress: {
    stress_digest: string; policy_digest: string; retrieval_digest: string;
    robustness_digest: string; similarity_digest: string;
    selected_source_records: number; exact_content_families: number;
    possible_near_duplicate_clusters: number;
    flagged_objectives: string[]; objectives_with_similarity_holds: string[];
    objectives: {
      objective_id: string; target_attested_groups: number;
      selected_passages: number; selected_source_records: number;
      exact_content_families: number; possible_near_duplicate_clusters: number;
      possible_mirror_collapse: number; unscored_sources: number;
      worst_host_loss_clusters: number;
      hypothetical_target_shortfall: number; observed_hosts: number;
      concern: string; independent_evidence_attested: false;
    }[];
    limitations: string[];
    claim_correctness_verified: false;
    source_text_exported: false; model_or_network_invoked: false;
    human_review_required: true;
  };
  source_similarity: {
    audit_digest: string; retrieval_digest: string; policy_digest: string;
    selected_sources: number; compared_sources: number; held_sources: number;
    eligible_pairs: number; candidate_pairs: number;
    cross_host_candidates: number; skipped_oversize: number;
    skipped_short: number; jaccard_threshold: number;
    containment_threshold: number;
    candidate_leads: {
      left_host: string; right_host: string;
      jaccard: number; smaller_set_containment: number;
      length_ratio: number; relation: 'exact_content' | 'near_duplicate_review';
      cross_host: boolean;
      human_lineage_review_required: true; shared_origin_established: false;
    }[];
    clusters: {
      observed_hosts: string[]; source_count: number;
      direct_candidate_edges: number; all_pairs_verified: false;
      independent_origin_verified: false;
    }[];
    source_bodies_redacted: true; network_used: false;
    training_or_publication_granted: false; lineage_verified: false;
  };
  retrieval_robustness: {
    audit_digest: string; retrieval_digest: string;
    selected_passages: number; selected_sources: number; selected_hosts: number;
    distinct_content_families: number; cross_host_exact_copy_groups: number;
    exact_copy_families: {
      content_sha256: string; source_count: number; host_count: number;
      hosts: string[]; selected_passages: number;
      independence_verified: false;
    }[];
    flagged_objectives: string[];
    objectives: {
      objective_id: string; selected_passages: number;
      distinct_selected_sources: number; distinct_selected_hosts: number;
      distinct_content_families: number; cross_host_exact_content_reuse: boolean;
      dominant_host: string | null; dominant_host_fraction: number;
      remaining_passages_after_host_loss: number;
      remaining_sources_after_host_loss: number;
      risk: 'no_selected_evidence' | 'single_host' |
        'host_concentrated' | 'multiple_observed_hosts' |
        'same_content_on_multiple_hosts';
      independence_confirmed: false;
    }[];
    host_ablation: {
      removed_host: string; removed_selected_passages: number;
      surviving_selected_passages: number; surviving_unique_sources: number;
      surviving_distinct_content_families: number;
      objectives_without_evidence: string[];
      objectives_left_with_one_host: string[];
      reranking_executed: false;
    }[];
    objective_reuse: {
      left_objective_id: string; right_objective_id: string;
      shared_source_count: number; shared_host_count: number;
      shared_content_family_count: number;
      source_jaccard: number; independence_proven: false;
    }[];
    limitations: string[]; source_bodies_excluded: true;
    verified_independence: false; network_or_reranking_executed: false;
  };
  canonical_routes: {
    route_digest: string; node_count: number; committed_parent_arcs: number;
    components: number; unreachable_pending: number; unknown_parent_urls: number;
    host_load: {
      host: string; discovered_nodes: number; pending_urls: number;
      ready_urls: number; robots_status: string; observed_fairness_share: number;
    }[];
    network_authority: false;
  };
  slice_simulation: {
    simulation_digest: string; projected_request_slots: number;
    projected_byte_reserve: number; remaining_requests: number;
    remaining_bytes: number; steps: {
      url: string; action: 'robots_preflight_only' | 'page_fetch_candidate';
      host: string; ready_at: number; conservative_byte_cap: number;
      robots_preflight_required: boolean;
    }[];
    held_urls: [string, string][]; blockers: string[];
    physical_worker_authorized: false; network_committed: false;
    real_robots_admission_executed: false;
  };
  dispatch_recovery: {
    ledger_digest: string; retained_event_count: number;
    event_history_incomplete: boolean; pending_dispatch: boolean;
    uncertain_bytes: number; hosts: {
      host: string; fault_grade: string; dispatch_intents: number;
      retries: number; transport_failures: number; interrupted: number;
    }[];
    recovery_queue: {
      code: string; severity: string; supporting_sequences: number[];
      requires_operator_resolution: boolean; auto_execute: false;
    }[];
    physical_worker_join_confirmed: false; mongo_commit_confirmed: false;
    uncertain_bytes_refunded: false;
  };
  scorecard: {
    digest: string; dimensions: {
      name: string; numerator: number; denominator: number;
      ratio: number; grade: string; limitations: string[];
    }[];
    alerts: string[]; advisory_priority: number; decision: 'human_review_hold';
  };
  pilot_qualification?: CrawlPilotQualification;
  read_only: true; network_executed: false;
  publication_granted: false; training_permission: false; review_required: true;
};
const ATLAS_OBJECTIVE_ID = /^[a-z][a-z0-9_-]{2,63}$/;
const ATLAS_TERM = /^[a-z0-9_-]{2,48}$/;
const ATLAS_DIMENSIONS = new Set(['fact', 'method', 'timeline', 'source', 'counterexample', 'implementation']);
const ATLAS_STAGES = new Set(['discovery', 'collection', 'verification', 'review']);
const ATLAS_EFFORT_TYPES = new Set([
  'source_policy', 'passage_integrity', 'source_provenance',
  'claim_contradiction', 'claim_corroboration', 'objective_gap', 'human_fact_review',
]);
function safeAtlasRequest(request: CrawlAtlasRequest): void {
  if (!request || !Array.isArray(request.objectives) || request.objectives.length < 1
      || request.objectives.length > 8 || !['fusion', 'lexical_bm25'].includes(request.retrieval_mode)) {
    throw new ChatClientError('Choose a bounded objective and retrieval algorithm.', { kind: 'validation', retryable: false });
  }
  const seen = new Set<string>();
  for (const item of request.objectives) {
    if (!item || !ATLAS_OBJECTIVE_ID.test(item.objective_id) || seen.has(item.objective_id)
        || typeof item.question !== 'string' || item.question !== item.question.trim()
        || item.question.length < 3 || item.question.length > 512
        || !ATLAS_DIMENSIONS.has(item.dimension) || !ATLAS_STAGES.has(item.stage)
        || typeof item.priority !== 'number' || !Number.isFinite(item.priority)
        || item.priority < 0 || item.priority > 1
        || !Number.isSafeInteger(item.minimum_reviewable_passages) || item.minimum_reviewable_passages < 1
        || item.minimum_reviewable_passages > 32
        || !Number.isSafeInteger(item.minimum_attested_groups) || item.minimum_attested_groups < 1
        || item.minimum_attested_groups > 16
        || !Number.isSafeInteger(item.max_source_age_seconds) || item.max_source_age_seconds < 60
        || item.max_source_age_seconds > 86400
        || !Array.isArray(item.required_terms) || item.required_terms.length > 16
        || !Array.isArray(item.blocked_terms) || item.blocked_terms.length > 16
        || [...item.required_terms, ...item.blocked_terms].some(term => !ATLAS_TERM.test(term))
        || item.required_terms.some(term => item.blocked_terms.includes(term))
        || new Set(item.required_terms).size !== item.required_terms.length
        || new Set(item.blocked_terms).size !== item.blocked_terms.length) {
      throw new ChatClientError('Research goals need valid bounded questions, terms and targets.', { kind: 'validation', retryable: false });
    }
    seen.add(item.objective_id);
  }
  if (request.review_effort) {
    if (!Array.isArray(request.review_effort) || request.review_effort.length > 7
        || new Set(request.review_effort.map(row => row.task_type)).size !== request.review_effort.length
        || request.review_effort.some(row => !ATLAS_EFFORT_TYPES.has(row.task_type)
          || row.estimate_basis !== 'operator_estimate'
          || !Number.isSafeInteger(row.estimated_minutes) || row.estimated_minutes < 1
          || row.estimated_minutes > 180)) {
      throw new ChatClientError('Use explicit finite review-effort estimates.', { kind: 'validation', retryable: false });
    }
  }
  if (request.review_budget_minutes !== undefined && (!integer(request.review_budget_minutes, 1440)
      || request.review_budget_minutes < 1)) {
    throw new ChatClientError('Choose a finite human-review time budget.', { kind: 'validation', retryable: false });
  }
}
function checkedPilotQualification(value: CrawlPilotQualification, atlas: CrawlAtlasReport): boolean {
  if (!value || value.schema_version !== 'skeleton.dragon.campaign_pilot_qualification.v1'
    || value.atlas_digest !== atlas.atlas_digest
    || value.snapshot_digest !== atlas.snapshot_digest
    || value.source_policy_digest !== atlas.source_policy.digest
    || value.run_sequence !== atlas.run_sequence
    || !HASH.test(value.qualification_digest)
    || value.pilot_check_count !== 10
    || !Array.isArray(value.checks) || value.checks.length !== 10
    || !Array.isArray(value.blocked_checks) || value.blocked_checks.length > 10
    || !Array.isArray(value.operator_actions) || value.operator_actions.length > 10
    || !Array.isArray(value.external_release_checks) || value.external_release_checks.length !== 10
    || !value.external_release_checks.every(item =>
      item && /^[a-z0-9_]{3,90}$/.test(item.code) && item.status === 'not_qualified')
    || !value.checks.every(item =>
      item && /^[a-z0-9_]{3,90}$/.test(item.code)
      && (item.status === 'qualified' && item.next_action === null
        || item.status === 'held' && typeof item.next_action === 'string'
        && /^[a-z0-9_]{3,90}$/.test(item.next_action)))
    || new Set(value.checks.map(item => item.code)).size !== 10
    || value.blocked_checks.join('|')
      !== value.checks.filter(item => item.status === 'held').map(item => item.code).join('|')
    || value.operator_actions.join('|')
      !== value.checks.filter(item => item.status === 'held').map(item => item.next_action).join('|')
    || value.pilot_status !== (value.blocked_checks.length ? 'held_for_repair' : 'ready_for_human_review')
    || value.source_only !== true || value.read_only !== true
    || value.human_review_required !== true || value.network_used !== false
    || value.model_invoked !== false || value.source_text_included !== false
    || value.training_authorized !== false || value.publication_authorized !== false
    || value.release_authorized !== false
    || value.release_status !== 'held_until_independent_exact_head_and_device_evidence'
    || value.recheck_mongo_authority_before_any_followup !== true
    || JSON.stringify(value).length > 16000) return false;
  return true;
}
function checkedAtlasReport(value: CrawlAtlasReport, sessionId: string, requestedMode: CrawlAtlasRequest['retrieval_mode']): CrawlAtlasReport {
  if (!value || value.schema_version !== 'skeleton.dragon.campaign_atlas_dashboard.v1'
      || value.session_id !== sessionId || typeof value.run_id !== 'string'
      || !HASH.test(value.snapshot_digest) || !HASH.test(value.mandate_digest)
      || !HASH.test(value.atlas_digest) || !HASH.test(value.dashboard_digest)
      || !integer(value.run_sequence) || typeof value.issued_at !== 'number'
      || !Number.isFinite(value.issued_at) || value.retrieval?.mode !== requestedMode
      || !Array.isArray(value.stages) || value.stages.length !== 26
      || !value.stages.every((row, index) => row.ordinal === index
        && typeof row.name === 'string' && row.name.length < 100
        && HASH.test(row.receipt_digest) && HASH.test(row.chain_digest))
      || !value.source_policy || !HASH.test(value.source_policy.digest)
      || !integer(value.source_policy.sources_seen, 64)
      || !integer(value.source_policy.included_source_count, 64)
      || !integer(value.source_policy.excluded_source_count, 64)
      || value.source_policy.included_source_count + value.source_policy.excluded_source_count
         !== value.source_policy.sources_seen
      || !value.context?.raw_source_text_redacted
      || !value.context?.fresh_policy_recheck_required
      || !value.review_operations || value.review_operations.human_review_recorded !== false
      || value.review_operations.durable_review_mutations !== false
      || !Array.isArray(value.review_operations.recommended_queue)
      || value.review_operations.recommended_queue.length > 32
      || value.review_operations.recommended_queue.some(task =>
        !task || typeof task.task_id !== 'string' || task.automatically_approvable !== false
        || task.current_status !== 'pending_human_review')
      || !value.citation_manifest?.body_redacted
      || value.citation_manifest.publication_permission !== false
      || !value.jeeves_handoff?.body_excluded
      || value.jeeves_handoff.network_called !== false
      || value.jeeves_handoff.dispatch_granted !== false
      || !value.forensics
      || !HASH.test(value.forensics.report_digest)
      || !HASH.test(value.forensics.frame_set_digest)
      || value.forensics.atlas_digest !== value.atlas_digest
      || value.forensics.source_policy_digest !== value.source_policy.digest
      || value.forensics.retrieval_digest !== value.retrieval.digest
      || !Array.isArray(value.forensics.stages)
      || value.forensics.stages.length !== FORENSIC_STAGE_NAMES.length
      || value.forensics.stages.some((entry, index) =>
        !entry || entry.ordinal !== index
        || entry.name !== FORENSIC_STAGE_NAMES[index]
        || !HASH.test(entry.receipt_digest) || !HASH.test(entry.chain_digest))
      || !integer(value.forensics.selected_passages, 32)
      || !integer(value.forensics.selected_sources, 32)
      || !integer(value.forensics.security_held_passages, 32)
      || !integer(value.forensics.security_held_sources, 32)
      || !integer(value.forensics.active_content_held_sources, 32)
      || !integer(value.forensics.privacy_held_sources, 32)
      || !integer(value.forensics.cross_host_sentence_echoes, 256)
      || !integer(value.forensics.source_reuse_components, 32)
      || !integer(value.forensics.possible_polarity_collisions, 256)
      || !integer(value.forensics.low_information_passages, 32)
      || !integer(value.forensics.capture_age_held_sources, 32)
      || !integer(value.forensics.overlap_excess_characters, 48000)
      || !integer(value.forensics.provenance_held_sources, 32)
      || !integer(value.forensics.grounding_deficit_objectives, 32)
      || !integer(value.forensics.reference_reused_sources, 32)
      || typeof value.forensics.consent_renewal_review_due !== 'boolean'
      || !integer(value.forensics.urgent_research_gaps, 32)
      || !integer(value.forensics.context_selected_utf8_bytes, 196608)
      || typeof value.forensics.context_budget_exceeded !== 'boolean'
      || !integer(value.forensics.extraction_held_sources, 32)
      || !integer(value.forensics.query_unsupported_objectives, 32)
      || !integer(value.forensics.origin_review_sources, 32)
      || !integer(value.forensics.selection_source_dominance_objectives, 32)
      || !integer(value.forensics.risk_ablated_objectives, 32)
      || !integer(value.forensics.script_coverage_review_objectives, 32)
      || !integer(value.forensics.review_tasks, 256)
      || !integer(value.forensics.critical_review_tasks, 256)
      || value.forensics.critical_review_tasks > value.forensics.review_tasks
      || !Array.isArray(value.forensics.concentrated_objectives)
      || value.forensics.concentrated_objectives.length > 8
      || value.forensics.concentrated_objectives.some(x => typeof x !== 'string' || x.length > 64)
      || !Array.isArray(value.forensics.review_queue)
      || value.forensics.review_queue.length > 24
      || value.forensics.review_queue.length > value.forensics.review_tasks
      || value.forensics.review_queue.some(item =>
        !item || typeof item.task_id !== 'string' || item.task_id.length !== 24
        || !['critical', 'high', 'medium', 'low'].includes(item.risk)
        || typeof item.reason !== 'string' || item.reason.length > 128
        || !Array.isArray(item.source_ids) || item.source_ids.length > 32
        || item.source_ids.some(id => !HASH.test(id))
        || !Array.isArray(item.objective_ids) || item.objective_ids.length > 8
        || item.objective_ids.some(id => typeof id !== 'string' || id.length > 64)
        || item.model_may_decide !== false)
      || value.forensics.source_bodies_redacted !== true
      || value.forensics.human_review_required !== true
      || value.forensics.publication_granted !== false
      || value.forensics.training_permission !== false
      || value.forensics.network_or_model_invoked !== false
      || !value.operations
       || !HASH.test(value.operations.report_digest)
       || value.operations.source_snapshot_digest !== value.snapshot_digest
       || value.operations.run_sequence !== value.run_sequence
       || !Array.isArray(value.operations.stages)
       || value.operations.stages.length !== OPERATION_STAGE_NAMES.length
       || value.operations.stages.some((entry, index) =>
         !entry || entry.ordinal !== index || entry.name !== OPERATION_STAGE_NAMES[index]
         || !HASH.test(entry.receipt_digest) || !HASH.test(entry.chain_digest))
       || !integer(value.operations.retained_event_count, 64)
       || typeof value.operations.historical_events_incomplete !== 'boolean'
       || typeof value.operations.event_clock_integrity_review !== 'boolean'
       || typeof value.operations.pending_dispatch !== 'boolean'
       || !integer(value.operations.uncertain_bytes, 33_554_432)
       || !integer(value.operations.inspected_origins, 32)
       || !integer(value.operations.unresolved_robots_origins, 32)
       || !integer(value.operations.stale_robots_origins, 32)
       || !integer(value.operations.observed_resource_samples, 32)
       || !integer(value.operations.hypothetical_work_candidates, 4)
       || !Array.isArray(value.operations.capacity_holds)
       || value.operations.capacity_holds.length > 32
       || value.operations.capacity_holds.some(code => typeof code !== 'string'
         || !/^[a-z][a-z0-9_]{2,95}$/.test(code))
       || !integer(value.operations.critical_operator_steps, 48)
       || !Array.isArray(value.operations.operator_runbook)
       || value.operations.operator_runbook.length > 16
       || value.operations.operator_runbook.some(item =>
         !item || typeof item.code !== 'string'
         || !/^[a-z][a-z0-9_]{2,95}$/.test(item.code)
         || !['critical', 'high', 'medium', 'advisory'].includes(item.priority)
         || item.requires_backend_authority !== true
         || item.automatically_executed !== false)
       || value.operations.physical_worker_fenced !== false
       || value.operations.mongo_checkpoint_confirmed !== false
       || value.operations.live_robots_permission_granted !== false
       || value.operations.network_executed !== false
       || value.operations.source_text_redacted !== true
       || value.operations.read_only !== true
       || value.operations.automatic_recovery_authorized !== false
       || !value.evidence_family_stress
      || !HASH.test(value.evidence_family_stress.stress_digest)
      || value.evidence_family_stress.policy_digest !== value.source_policy.digest
      || value.evidence_family_stress.retrieval_digest !== value.retrieval.digest
      || value.evidence_family_stress.robustness_digest
         !== value.retrieval_robustness?.audit_digest
      || value.evidence_family_stress.similarity_digest
         !== value.source_similarity?.audit_digest
      || !integer(value.evidence_family_stress.selected_source_records, 32)
      || !integer(value.evidence_family_stress.exact_content_families, 32)
      || !integer(value.evidence_family_stress.possible_near_duplicate_clusters, 32)
      || value.evidence_family_stress.exact_content_families
         > value.evidence_family_stress.selected_source_records
      || value.evidence_family_stress.possible_near_duplicate_clusters
         > value.evidence_family_stress.exact_content_families
      || !Array.isArray(value.evidence_family_stress.objectives)
      || value.evidence_family_stress.objectives.length !== value.objectives?.length
      || value.evidence_family_stress.objectives.some(item =>
        !item || typeof item.objective_id !== 'string'
        || item.independent_evidence_attested !== false
        || !integer(item.selected_source_records, 32)
        || !integer(item.exact_content_families, 32)
        || !integer(item.possible_near_duplicate_clusters, 32)
        || !integer(item.unscored_sources, 32)
        || !integer(item.hypothetical_target_shortfall, 16)
        || !integer(item.target_attested_groups, 16)
        || item.target_attested_groups < 1
        || item.possible_near_duplicate_clusters > item.exact_content_families
        || item.exact_content_families > item.selected_source_records)
      || !Array.isArray(value.evidence_family_stress.flagged_objectives)
      || value.evidence_family_stress.flagged_objectives.length > 8
      || !Array.isArray(value.evidence_family_stress.objectives_with_similarity_holds)
      || value.evidence_family_stress.objectives_with_similarity_holds.length > 8
      || !Array.isArray(value.evidence_family_stress.limitations)
      || value.evidence_family_stress.limitations.length < 5
      || value.evidence_family_stress.claim_correctness_verified !== false
      || value.evidence_family_stress.source_text_exported !== false
      || value.evidence_family_stress.model_or_network_invoked !== false
      || value.evidence_family_stress.human_review_required !== true
      || !value.source_similarity || !HASH.test(value.source_similarity.audit_digest)
      || value.source_similarity.retrieval_digest !== value.retrieval.digest
      || value.source_similarity.policy_digest !== value.source_policy.digest
      || !integer(value.source_similarity.selected_sources, 32)
      || !integer(value.source_similarity.compared_sources, 32)
      || !integer(value.source_similarity.held_sources, 32)
      || value.source_similarity.compared_sources + value.source_similarity.held_sources
         !== value.source_similarity.selected_sources
      || !integer(value.source_similarity.eligible_pairs, 496)
      || !integer(value.source_similarity.candidate_pairs, 496)
      || value.source_similarity.candidate_pairs > value.source_similarity.eligible_pairs
      || !integer(value.source_similarity.cross_host_candidates, 496)
      || value.source_similarity.cross_host_candidates > value.source_similarity.candidate_pairs
      || !integer(value.source_similarity.skipped_oversize, 32)
      || !integer(value.source_similarity.skipped_short, 32)
      || !Number.isFinite(value.source_similarity.jaccard_threshold)
      || value.source_similarity.jaccard_threshold < 0.5
      || value.source_similarity.jaccard_threshold > 1
      || !Number.isFinite(value.source_similarity.containment_threshold)
      || value.source_similarity.containment_threshold < 0.5
      || value.source_similarity.containment_threshold > 1
      || value.source_similarity.source_bodies_redacted !== true
      || value.source_similarity.network_used !== false
      || value.source_similarity.training_or_publication_granted !== false
      || value.source_similarity.lineage_verified !== false
      || !Array.isArray(value.source_similarity.candidate_leads)
      || value.source_similarity.candidate_leads.length > 16
      || value.source_similarity.candidate_leads.length > value.source_similarity.candidate_pairs
      || value.source_similarity.candidate_leads.some(item =>
        !item || !['exact_content', 'near_duplicate_review'].includes(item.relation)
        || item.human_lineage_review_required !== true
        || item.shared_origin_established !== false
        || !Number.isFinite(item.jaccard) || item.jaccard < 0 || item.jaccard > 1
        || !Number.isFinite(item.smaller_set_containment)
        || item.smaller_set_containment < 0 || item.smaller_set_containment > 1
        || !Number.isFinite(item.length_ratio)
        || item.length_ratio < 0 || item.length_ratio > 1)
      || !Array.isArray(value.source_similarity.clusters)
      || value.source_similarity.clusters.length > 16
      || value.source_similarity.clusters.some(item =>
        !item || item.all_pairs_verified !== false
        || item.independent_origin_verified !== false
        || !integer(item.source_count, 32) || item.source_count < 2
        || !integer(item.direct_candidate_edges, 496)
        || !Array.isArray(item.observed_hosts) || item.observed_hosts.length > 32)
      || !value.retrieval_robustness
      || !HASH.test(value.retrieval_robustness.audit_digest)
      || value.retrieval_robustness.retrieval_digest !== value.retrieval.digest
      || !integer(value.retrieval_robustness.selected_passages, 32)
      || !integer(value.retrieval_robustness.selected_sources, 64)
      || !integer(value.retrieval_robustness.selected_hosts, 32)
      || !integer(value.retrieval_robustness.distinct_content_families, 32)
      || value.retrieval_robustness.distinct_content_families
         > value.retrieval_robustness.selected_sources
      || !integer(value.retrieval_robustness.cross_host_exact_copy_groups, 32)
      || !Array.isArray(value.retrieval_robustness.exact_copy_families)
      || value.retrieval_robustness.exact_copy_families.length > 32
      || value.retrieval_robustness.exact_copy_families.some(family =>
        !family || !HASH.test(family.content_sha256)
        || family.independence_verified !== false
        || !integer(family.source_count, 32) || family.source_count < 2
        || !integer(family.host_count, 32)
        || !Array.isArray(family.hosts) || family.hosts.length !== family.host_count)
      || value.retrieval_robustness.source_bodies_excluded !== true
      || value.retrieval_robustness.verified_independence !== false
      || value.retrieval_robustness.network_or_reranking_executed !== false
      || !Array.isArray(value.retrieval_robustness.objectives)
      || value.retrieval_robustness.objectives.length !== value.objectives?.length
      || value.retrieval_robustness.objectives.some(row =>
        !row || row.independence_confirmed !== false
        || !Number.isFinite(row.dominant_host_fraction)
        || row.dominant_host_fraction < 0 || row.dominant_host_fraction > 1)
      || !Array.isArray(value.retrieval_robustness.host_ablation)
      || value.retrieval_robustness.host_ablation.length > 32
      || value.retrieval_robustness.host_ablation.some(row =>
        !row || row.reranking_executed !== false)
      || !Array.isArray(value.retrieval_robustness.objective_reuse)
      || value.retrieval_robustness.objective_reuse.length > 28
      || value.retrieval_robustness.objective_reuse.some(row =>
        !row || row.independence_proven !== false
        || !Number.isFinite(row.source_jaccard)
        || row.source_jaccard < 0 || row.source_jaccard > 1)
      || !Array.isArray(value.retrieval_robustness.flagged_objectives)
      || value.retrieval_robustness.flagged_objectives.length > 8
      || !Array.isArray(value.retrieval_robustness.limitations)
      || value.retrieval_robustness.limitations.length < 5
      || value.retrieval_robustness.limitations.length > 12
      || value.canonical_routes?.network_authority !== false
      || value.slice_simulation?.network_committed !== false
      || value.slice_simulation.physical_worker_authorized !== false
      || value.dispatch_recovery?.mongo_commit_confirmed !== false
      || value.dispatch_recovery.physical_worker_join_confirmed !== false
      || value.dispatch_recovery.uncertain_bytes_refunded !== false
      || value.scorecard?.decision !== 'human_review_hold'
      || !Array.isArray(value.scorecard.alerts) || value.scorecard.alerts.length > 256
      || value.pilot_qualification !== undefined && !checkedPilotQualification(value.pilot_qualification, value)
      || value.read_only !== true || value.network_executed !== false
      || value.publication_granted !== false || value.training_permission !== false
      || value.review_required !== true || JSON.stringify(value).length > 512 * 1024) {
    invalid('The current Dragon research inspection is incomplete or violates source authority.');
  }
  return value;
}
export async function getCrawlAtlas(
  id: string, request: CrawlAtlasRequest, signal?: AbortSignal,
): Promise<CrawlAtlasReport> {
  safeAtlasRequest(request);
  const previousToken = getAuthToken();
  const payload = await read(
    api.post<{ report: CrawlAtlasReport }>(
      ROOT + '/sessions/' + identifier(id) + '/research/atlas',
      request, options(signal),
    ),
    previousToken, 'The Dragon research inspection could not be verified.',
  );
  if (signal?.aborted || previousToken !== getAuthToken()) {
    throw new ChatClientError('The research inspection was detached or your account changed.', { kind: 'authorization', retryable: false });
  }
  const report = checkedAtlasReport(payload.report, id, request.retrieval_mode);
  if (report.pilot_qualification) {
    // Both the status envelope and this exact-byte digest are source-only:
    // neither is a substitute for the backend's authenticated Mongo re-read.
    const receipt = report.pilot_qualification;
    let canonical: string;
    try { canonical = canonicalPilotReceipt(pilotReceiptBody(receipt)); }
    catch { invalid('Pilot receipt has an invalid canonical payload.'); }
    const observed = await digestStringAsync(CryptoDigestAlgorithm.SHA256, canonical);
    if (signal?.aborted || previousToken !== getAuthToken()) {
      throw new ChatClientError('The pilot receipt was detached from your session.',
        { kind: 'authorization', retryable: false });
    }
    if (observed !== receipt.qualification_digest) {
      invalid('The exact Dragon pilot qualification receipt did not verify.');
    }
  }
  return report;
}
