import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { crawlRequestKey } from './crawlerClient';

export type DragonMechanic = { id: string; label: string; practice_supported: boolean };
export type DragonKnowledgeReadiness = {
  schema_version: string; configured: boolean; available: boolean;
  checks: { practice_storage: { available: boolean; code: string }; knowledge_storage: { available: boolean; code: string } };
  actions: { code: string; message: string }[]; limits: Record<string, number | string>;
  capabilities: { source_review: boolean; measured_local_practice: boolean; automatic_promotion: false; training_rights: false };
  mechanics: DragonMechanic[];
};
type DragonCrawlerReferenceIdentity = { session_id: string; source_id: string; source_digest: string; request_digest: string; consent_id: string };
export type DragonCrawlerReference = DragonCrawlerReferenceIdentity & (
  { schema_version: 'skeleton.dragon.crawler_reference.v1' }
  | { schema_version: 'skeleton.dragon.crawler_reference.v2'; source_use_version: number }
);
export type DragonKnowledgeCandidate = {
  candidate_id: string; version: number; state: 'pending_review' | 'approved' | 'rejected';
  session_id: string; source_id: string; source_ref: DragonCrawlerReference; source_digest: string; source_url: string; title: string;
  start: number; end: number; exact_quote: string; statement: string; mechanic: string; valid_until: string; created_at: string; current_source_usable?: boolean; current_source_error?: string | null;
  review: null | { review_id: string; decision: 'approve_design_reference' | 'reject'; rationale: string; reviewed_at: string; reviewer_id: string; rights_reference?: string | null; training_allowed: false };
  prepared_review?: null | { review_id: string; decision: 'approve_design_reference' | 'reject'; rationale: string; rights_reference?: string | null; reviewed_at: string; training_allowed: false };
  knowledge: null | { source_id: string; revision: number; revision_digest: string; note_id: string };
};
export type DragonPracticeReceipt = {
  practice_id: string; status: string; steps: number; return?: number; reward_components?: Record<string, number>; error_code?: string | null;
  trace_digest: string; runtime_kind: string; lesson: unknown; preview?: Record<string, unknown> | null;
};
export type DragonCandidateDraft = { session_id: string; source_id: string; start: number; end: number; statement: string; mechanic: string; idempotency_key: string };
const ROOT = '/api/dragon-academy';
const SHA = /^[a-f0-9]{64}$/;
const IDENTIFIER = /^[A-Za-z0-9:_-]{1,128}$/;
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function id(value: string) { if (!IDENTIFIER.test(value)) invalid('The Dragon evidence identity is invalid.'); return encodeURIComponent(value); }
function int(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER) { return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max; }
function crawlerReference(value: unknown): value is DragonCrawlerReference {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const ref = value as Record<string, unknown>;
  const v2 = ref.schema_version === 'skeleton.dragon.crawler_reference.v2';
  const fields = ['schema_version', 'session_id', 'source_id', 'source_digest', 'request_digest', 'consent_id', ...(v2 ? ['source_use_version'] : [])];
  return (v2 || ref.schema_version === 'skeleton.dragon.crawler_reference.v1')
    && Object.keys(ref).length === fields.length && fields.every(field => Object.prototype.hasOwnProperty.call(ref, field))
    && typeof ref.session_id === 'string' && IDENTIFIER.test(ref.session_id)
    && typeof ref.source_id === 'string' && SHA.test(ref.source_id)
    && typeof ref.source_digest === 'string' && SHA.test(ref.source_digest)
    && typeof ref.request_digest === 'string' && SHA.test(ref.request_digest)
    && typeof ref.consent_id === 'string' && ref.consent_id.length > 0 && ref.consent_id.length <= 128
    && (!v2 || int(ref.source_use_version, 0, 2147483647));
}
async function request<T>(method: 'get' | 'post', path: string, body: unknown, signal?: AbortSignal, key?: string): Promise<T> {
  const token = getAuthToken();
  if (body && new TextEncoder().encode(JSON.stringify(body)).byteLength > 16384) throw new ChatClientError('The review request exceeds its bounded size.', { kind: 'validation' });
  const options = { headers: authHeaders(), signal, retries: 0, timeoutMs: 65000, idempotencyKey: key };
  const result: ApiResult<T> = await (method === 'get' ? api.get<T>(ROOT + path, options) : api.post<T>(ROOT + path, body, options));
  if (signal?.aborted || token !== getAuthToken()) throw new ChatClientError('Your account changed or the Dragon request was detached.', { kind: 'authorization', retryable: false });
  if (!result.ok || result.data === null) throw chatApiError(result, 'The Dragon evidence operation could not be confirmed.');
  if (new TextEncoder().encode(JSON.stringify(result.data)).byteLength > 2 * 1024 * 1024) invalid('The Dragon evidence response exceeds its bound.');
  return result.data;
}
function candidate(value: DragonKnowledgeCandidate, expected?: string) {
  if (!value || !IDENTIFIER.test(value.candidate_id) || expected && value.candidate_id !== expected || !int(value.version, 1)
    || !['pending_review', 'approved', 'rejected'].includes(value.state) || !IDENTIFIER.test(value.session_id) || !IDENTIFIER.test(value.source_id)
    || !SHA.test(value.source_digest) || !crawlerReference(value.source_ref)
    || value.source_ref.session_id !== value.session_id || value.source_ref.source_id !== value.source_id || value.source_ref.source_digest !== value.source_digest
    || !SHA.test(value.source_ref.request_digest) || typeof value.source_ref.consent_id !== 'string' || value.source_ref.consent_id.length > 128
    || value.current_source_usable !== undefined && typeof value.current_source_usable !== 'boolean'
    || value.current_source_error != null && (typeof value.current_source_error !== 'string' || value.current_source_error.length > 512)
    || typeof value.source_url !== 'string' || value.source_url.length > 4096 || typeof value.title !== 'string'
    || !int(value.start, 0, 2097152) || !int(value.end, 1, 2097152) || value.end <= value.start
    || typeof value.exact_quote !== 'string' || Array.from(value.exact_quote).length !== value.end - value.start || value.end - value.start > 1000
    || typeof value.statement !== 'string' || !value.statement || Array.from(value.statement).length > 2048 || typeof value.mechanic !== 'string'
    || !Number.isFinite(Date.parse(value.valid_until)) || !Number.isFinite(Date.parse(value.created_at))) invalid('The Dragon candidate does not match a bounded preserved passage.');
  if (value.prepared_review && (!IDENTIFIER.test(value.prepared_review.review_id) || !['approve_design_reference', 'reject'].includes(value.prepared_review.decision) || typeof value.prepared_review.rationale !== 'string' || value.prepared_review.training_allowed !== false || !Number.isFinite(Date.parse(value.prepared_review.reviewed_at)))) invalid('The saved review recovery intent is invalid.');
  if (value.review && (!['approve_design_reference', 'reject'].includes(value.review.decision) || typeof value.review.rationale !== 'string'
    || !Number.isFinite(Date.parse(value.review.reviewed_at)) || value.review.training_allowed !== false)) invalid('The human review scope is invalid.');
  if (value.knowledge && (!IDENTIFIER.test(value.knowledge.source_id) || !int(value.knowledge.revision, 0) || !SHA.test(value.knowledge.revision_digest) || typeof value.knowledge.note_id !== 'string')) invalid('The reviewed design reference identity is invalid.');
  return value;
}
function practice(value: DragonPracticeReceipt) {
  if (!value || !IDENTIFIER.test(value.practice_id) || typeof value.status !== 'string' || value.status.length > 64
    || !int(value.steps, 0, 512) || value.status === 'completed' && (typeof value.return !== 'number' || !Number.isFinite(value.return) || !value.reward_components)
    || value.return !== undefined && (typeof value.return !== 'number' || !Number.isFinite(value.return))
    || value.reward_components !== undefined && (Object.keys(value.reward_components).length > 32 || Object.values(value.reward_components).some(number => typeof number !== 'number' || !Number.isFinite(number)))
    || !SHA.test(value.trace_digest) || typeof value.runtime_kind !== 'string' || value.runtime_kind.length > 128) invalid('The measured Dragon practice receipt is invalid.');
  return value;
}
export async function getDragonKnowledgeReadiness(signal?: AbortSignal): Promise<DragonKnowledgeReadiness> {
  const value = await request<DragonKnowledgeReadiness>('get', '/runtime/readiness', null, signal);
  if (!value || typeof value.schema_version !== 'string' || typeof value.configured !== 'boolean' || typeof value.available !== 'boolean'
    || !value.checks || !value.capabilities || typeof value.capabilities.source_review !== 'boolean' || typeof value.capabilities.measured_local_practice !== 'boolean'
    || value.capabilities.automatic_promotion !== false || value.capabilities.training_rights !== false || !Array.isArray(value.actions) || value.actions.length > 16
    || !Array.isArray(value.mechanics) || value.mechanics.length > 128) invalid('The Dragon readiness response is invalid.');
  for (const key of ['practice_storage', 'knowledge_storage'] as const) if (!value.checks[key] || typeof value.checks[key].available !== 'boolean' || typeof value.checks[key].code !== 'string') invalid('The Dragon storage checks are incomplete.');
  for (const mechanic of value.mechanics) if (!mechanic || typeof mechanic.id !== 'string' || typeof mechanic.label !== 'string' || typeof mechanic.practice_supported !== 'boolean') invalid('The Dragon mechanic catalogue is invalid.');
  return value;
}
export async function listDragonCandidates(state?: DragonKnowledgeCandidate['state'], cursor?: string | null, signal?: AbortSignal) {
  if (cursor && cursor.length > 4096) invalid('The Dragon review cursor is invalid.');
  const params = new URLSearchParams({ limit: '20' }); if (state) params.set('state', state); if (cursor) params.set('cursor', cursor);
  const value = await request<{ candidates: DragonKnowledgeCandidate[]; next_cursor: string | null }>('get', '/knowledge/candidates?' + params, null, signal);
  if (!Array.isArray(value.candidates) || value.candidates.length > 20 || value.next_cursor !== null && (typeof value.next_cursor !== 'string' || value.next_cursor.length > 4096)) invalid('The Dragon review list is invalid.');
  value.candidates.forEach(value => candidate(value)); return value;
}
export async function getDragonCandidate(candidateId: string, signal?: AbortSignal) {
  const result = await request<{ candidate: DragonKnowledgeCandidate }>('get', '/knowledge/candidates/' + id(candidateId), null, signal);
  return candidate(result.candidate, candidateId);
}
export async function createDragonCandidate(body: DragonCandidateDraft, signal?: AbortSignal) {
  const result = await request<{ candidate: DragonKnowledgeCandidate }>('post', '/knowledge/candidates', body, signal, body.idempotency_key);
  const value = candidate(result.candidate);
  if (value.session_id !== body.session_id || value.source_id !== body.source_id || value.start !== body.start || value.end !== body.end || value.statement !== body.statement.trim() || value.mechanic !== body.mechanic) invalid('The issued candidate differs from the selected source passage.');
  return value;
}
export async function reviewDragonCandidate(current: DragonKnowledgeCandidate, body: {
  expected_version: number; decision: 'approve_design_reference' | 'reject'; rationale: string;
  rights_reference?: string; rights_acknowledged?: true; idempotency_key: string;
}, signal?: AbortSignal) {
  const result = await request<{ candidate: DragonKnowledgeCandidate }>('post', '/knowledge/candidates/' + id(current.candidate_id) + '/review', body, signal, body.idempotency_key);
  const value = candidate(result.candidate, current.candidate_id);
  if (Object.entries(current.source_ref).some(([key, field]) => value.source_ref[key as keyof DragonCrawlerReference] !== field) || value.source_digest !== current.source_digest || value.exact_quote !== current.exact_quote) invalid('The reviewed source identity changed.');
  return value;
}
export async function runDragonPractice(current: DragonKnowledgeCandidate, body: { expected_version: number; seed: number; max_steps: number; idempotency_key: string; practice_consent: true }, signal?: AbortSignal) {
  if (!int(body.seed, 0, 2147483647) || !int(body.max_steps, 16, 512) || body.practice_consent !== true) throw new ChatClientError('Choose a seed and 16–512 bounded practice steps with explicit consent.', { kind: 'validation' });
  const result = await request<{ practice: DragonPracticeReceipt; replayed: boolean }>('post', '/knowledge/candidates/' + id(current.candidate_id) + '/practice', body, signal, body.idempotency_key);
  if (typeof result.replayed !== 'boolean') invalid('The Dragon practice replay receipt is missing.');
  return { practice: practice(result.practice), replayed: result.replayed };
}
export function dragonEvidenceKey(action: string) { return crawlRequestKey('dragon-' + action); }


export type DragonReviewedPin = { schema_version: 'skeleton.dragon.reviewed_reference.v1'; candidate_id: string; review_id: string; source_id: string; revision_digest: string; note_id: string; content_digest: string; crawler_reference: DragonCrawlerReference };
export type DragonDesignReference = {
  statement: string; exact_quote: string; text: string; mechanic: string; source_url: string; source_ref: DragonCrawlerReference;
  citation: Record<string, unknown>; review_pin: DragonReviewedPin;
  classification: 'human_reviewed_design_reference'; truth_verified: false; training_allowed: false;
};
export async function searchDragonReferences(query: string, signal?: AbortSignal) {
  const q = query.trim(); if (!q || q.length > 300) throw new ChatClientError('Enter a design-reference query of 1–300 characters.', { kind: 'validation' });
  const result = await request<{ references: DragonDesignReference[]; evidence_refs: DragonReviewedPin[] }>('get', '/knowledge/search?q=' + encodeURIComponent(q) + '&limit=8', null, signal);
  if (!Array.isArray(result.references) || result.references.length > 8 || !Array.isArray(result.evidence_refs) || result.evidence_refs.length > 64
    || result.evidence_refs.some(ref => !ref || ref.schema_version !== 'skeleton.dragon.reviewed_reference.v1' || !IDENTIFIER.test(ref.candidate_id) || !IDENTIFIER.test(ref.review_id) || !IDENTIFIER.test(ref.source_id) || !SHA.test(ref.revision_digest) || !SHA.test(ref.content_digest) || typeof ref.note_id !== 'string' || ref.note_id.length > 256 || !crawlerReference(ref.crawler_reference))) invalid('The design-reference search is invalid.');
  for (const ref of result.references) if (!ref || typeof ref.statement !== 'string' || typeof ref.exact_quote !== 'string' || typeof ref.text !== 'string'
    || typeof ref.mechanic !== 'string' || typeof ref.source_url !== 'string' || ref.source_url.length > 4096 || !crawlerReference(ref.source_ref)
    || !ref.citation || typeof ref.citation !== 'object' || ref.classification !== 'human_reviewed_design_reference'
    || ref.truth_verified !== false || ref.training_allowed !== false) invalid('A design reference has an unsupported authority classification.');
  return result;
}
export async function getDragonPracticeHistory(candidateId: string, signal?: AbortSignal) {
  const result = await request<{ practices: DragonPracticeReceipt[] }>('get', '/knowledge/candidates/' + id(candidateId) + '/practice', null, signal);
  if (!Array.isArray(result.practices) || result.practices.length > 128) invalid('The practice history exceeds its bounded page.');
  result.practices.forEach(value => practice(value)); return result.practices;
}

export async function resumeDragonReview(current: DragonKnowledgeCandidate, signal?: AbortSignal) {
  if (current.state !== 'pending_review' || !current.prepared_review || current.current_source_usable !== true) throw new ChatClientError('This saved review cannot currently resume.', { kind: 'validation' });
  const result = await request<{ candidate: DragonKnowledgeCandidate }>('post', '/knowledge/candidates/' + id(current.candidate_id) + '/review/resume', { review_id: current.prepared_review.review_id }, signal);
  const value = candidate(result.candidate, current.candidate_id); if (value.review?.review_id !== current.prepared_review.review_id || value.source_digest !== current.source_digest) invalid('The recovered review differs from the saved decision.'); return value;
}
