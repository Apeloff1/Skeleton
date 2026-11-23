/** Authenticated, bounded previews over the existing AI workflow owner. */
import { authHeaders, getAuthToken, getAuthEpoch } from '../auth/gameforgeAuth';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import api, { type ApiResult } from '../utils/apiClient';
import { chatApiError } from './chatErrors';
import { HASH, canonicalJourneyJSON, checkedRequest, isJourneyId, isObject, readJourneyEnvelope, type JourneyId, type JourneyRequest, type JourneyPreview } from '../features/Jeeves/journeys/journeyDraft';

export type JourneyOption = { type: 'choice' | 'integer'; label?: string; choices?: string[]; minimum?: number; maximum?: number; default?: string | number };
export type JourneyDefinition = { journey_id: JourneyId; title: string; description: string; destination: string; options: Record<string, JourneyOption>; default_options: Record<string, string | number> };
export type JourneyCatalog = { schema_version: 'skeleton.ai.workflow_journey_catalog.v1'; catalog_version: number; journeys: JourneyDefinition[]; execution_authorized: false; catalog_digest: string };
export type JourneyDraft = { schema_version: 'skeleton.ai.workflow_draft.v1'; request: JourneyRequest; request_digest: string; journey_id: JourneyId; options: Record<string, string | number>; source_refs: JourneyRequest['source_refs']; prompt: string; chat_settings: { max_tokens: number; review_response: boolean }; minimum_output_tokens: number; output_kind: string; output_schema: Record<string, unknown>; destination: string; execution_authorized: false; draft_digest: string };
type Scope = { token: string; epoch: number; actor: string; tenant: string };
const OPTIONS = { retries: 0, timeoutMs: 15000, maxResponseChars: 128 * 1024 };
const ROOT = '/api/ai';
async function verifyDigest(value: unknown, expected: unknown): Promise<void> {
  if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, canonicalJourneyJSON(value)) !== expected) throw new Error('The workflow fingerprint does not match its reviewed content. Reload the preview.');
}
function validScope(scope: Scope, signal?: AbortSignal): void {
  if (signal?.aborted || scope.token !== getAuthToken() || scope.epoch !== getAuthEpoch()) throw new Error('Your account changed or this review was closed. Prepare the journey again.');
}
async function read<T>(request: Promise<ApiResult<T>>, scope: Scope, signal?: AbortSignal): Promise<T> {
  const result = await request; validScope(scope, signal);
  if (!result.ok || result.data == null) throw chatApiError(result, 'This workflow preview is unavailable. Your authored draft is preserved.');
  return result.data;
}
async function account(signal?: AbortSignal): Promise<Scope> {
  const scope: Scope = { token: getAuthToken(), epoch: getAuthEpoch(), actor: '', tenant: '' };
  const me = await read(api.get<unknown>('/api/auth/me', { ...OPTIONS, signal, headers: authHeaders() }), scope, signal);
  if (!isObject(me) || me.authenticated !== true || !isObject(me.user)) throw new Error('Sign in to prepare a guided journey.');
  scope.actor = String(me.user.email || me.user.user_id || ''); scope.tenant = String(me.user.tenant_id || 'default');
  if (!scope.actor || scope.actor.length > 512 || scope.tenant.length > 512) throw new Error('Your account identity is incomplete.');
  return scope;
}
function scoped(value: unknown, schema: string, scope: Scope): Record<string, unknown> {
  if (!isObject(value) || value.schema_version !== schema || value.actor_id !== scope.actor || value.tenant_id !== scope.tenant) throw new Error('The preview does not belong to the current account.');
  return value;
}
export async function getJourneyCatalog(signal?: AbortSignal): Promise<JourneyCatalog> {
  const scope = await account(signal);
  const response = scoped(await read(api.get<unknown>(ROOT + '/workflow-journeys', { ...OPTIONS, signal, headers: authHeaders() }), scope, signal), 'skeleton.ai.workflow_journeys.v1', scope);
  const value = response.catalog;
  if (!isObject(value) || value.schema_version !== 'skeleton.ai.workflow_journey_catalog.v1' || value.execution_authorized !== false
    || !HASH.test(String(value.catalog_digest)) || !Array.isArray(value.journeys) || value.journeys.length !== 5
    || new Set(value.journeys.map(item => isObject(item) && item.journey_id)).size !== 5) throw new Error('The journey catalog is incomplete or unsupported.');
  for (const item of value.journeys) {
    if (!isObject(item) || !isJourneyId(item.journey_id) || typeof item.title !== 'string' || item.title.length > 160
      || typeof item.description !== 'string' || item.description.length > 1000 || typeof item.destination !== 'string'
      || !isObject(item.options) || Object.keys(item.options).length > 12 || !isObject(item.default_options)) throw new Error('The journey options are invalid.');
    for (const option of Object.values(item.options)) {
      if (!isObject(option) || !['choice', 'integer'].includes(String(option.type))) throw new Error('A journey has an unsupported option.');
      if (option.type === 'choice' && (!Array.isArray(option.choices) || option.choices.length > 24 || option.choices.some(choice => typeof choice !== 'string' || choice.length > 80))) throw new Error('A journey option list is invalid.');
      if (option.type === 'integer' && (!Number.isSafeInteger(option.minimum) || !Number.isSafeInteger(option.maximum) || Number(option.minimum) > Number(option.maximum))) throw new Error('A journey budget range is invalid.');
    }
  }
  const { catalog_digest, ...content } = value;
  await verifyDigest(content, catalog_digest); validScope(scope, signal);
  return value as JourneyCatalog;
}
export async function prepareJourneyDraft(request: JourneyRequest, signal?: AbortSignal): Promise<JourneyDraft> {
  checkedRequest(request); const scope = await account(signal);
  const response = scoped(await read(api.post<unknown>(ROOT + '/workflow-drafts', request, { ...OPTIONS, signal, headers: authHeaders() }), scope, signal), 'skeleton.ai.workflow_draft_response.v1', scope);
  const value = response.draft;
  if (!isObject(value) || value.schema_version !== 'skeleton.ai.workflow_draft.v1' || value.execution_authorized !== false
    || value.journey_id !== request.journey_id || !HASH.test(String(value.request_digest)) || !HASH.test(String(value.draft_digest))
    || typeof value.prompt !== 'string' || value.prompt.length > 16000 || !isObject(value.chat_settings)
    || !Number.isSafeInteger(value.chat_settings.max_tokens) || Number(value.chat_settings.max_tokens) < 1
    || Number(value.chat_settings.max_tokens) > 8192 || typeof value.chat_settings.review_response !== 'boolean'
    || !Number.isSafeInteger(value.minimum_output_tokens) || !isObject(value.output_schema)) throw new Error('The prepared journey is invalid.');
  const envelope = readJourneyEnvelope(value.prompt);
  if (!envelope || envelope.request_digest !== value.request_digest || canonicalJourneyJSON(envelope.request) !== canonicalJourneyJSON(value.request)) throw new Error('The prepared prompt is not bound to its reviewed request.');
  checkedRequest(value.request);
  const normalized = value.request as JourneyRequest;
  if (normalized.goal !== request.goal.trim() || Object.entries(request.options).some(([key, choice]) => normalized.options[key] !== choice)
    || canonicalJourneyJSON(normalized.source_refs) !== canonicalJourneyJSON(request.source_refs.map(source => ({ ...source, label: source.label.trim(), locator: source.locator.trim(), excerpt: source.excerpt.trim() })))) throw new Error('The prepared request differs from your selected content or options.');
  const { draft_digest, ...content } = value;
  await verifyDigest(content, draft_digest); await verifyDigest(normalized, value.request_digest); validScope(scope, signal);
  return value as JourneyDraft;
}
export async function validateJourneyArtifact(request: JourneyRequest, artifact: unknown, signal?: AbortSignal): Promise<JourneyPreview> {
  checkedRequest(request); const scope = await account(signal);
  const response = scoped(await read(api.post<unknown>(ROOT + '/workflow-artifacts', { ...request, artifact }, { ...OPTIONS, signal, headers: authHeaders() }), scope, signal), 'skeleton.ai.workflow_artifact_response.v1', scope);
  const value = response.preview;
  if (!isObject(value) || value.schema_version !== 'skeleton.ai.workflow_preview.v1' || value.execution_authorized !== false
    || value.journey_id !== request.journey_id || !HASH.test(String(value.request_digest)) || !HASH.test(String(value.artifact_digest))
    || !isObject(value.artifact) || value.artifact.request_digest !== value.request_digest || value.artifact.journey_id !== request.journey_id
    || !isObject(value.checks) || !Array.isArray(value.warnings) || value.warnings.length > 20 || value.warnings.some(item => typeof item !== 'string' || item.length > 1000)) throw new Error('The artifact review is invalid.');
  await verifyDigest(value.artifact, value.artifact_digest); await verifyDigest(request, value.request_digest); validScope(scope, signal);
  return value as JourneyPreview;
}
