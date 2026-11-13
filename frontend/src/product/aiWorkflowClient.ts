import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import api, { type ApiResult } from '../utils/apiClient';
import { ChatClientError, chatApiError } from './chatErrors';

export type WorkflowSurface = 'chat' | 'studio' | 'crawler';
export type ChatWorkflowSettings = { max_tokens: number; review_response: boolean };
export type StudioWorkflowSettings = {
  max_steps: number; max_model_calls: number; max_jobs: number;
  max_output_tokens: number; authorization_seconds: number;
  completion_mode: 'native' | 'original';
};
export type CrawlerWorkflowSettings = {
  max_requests: number; max_documents: number; max_bytes: number; max_depth: number;
};
type TemplateMetadata = {
  schema_version: 'skeleton.ai.workflow_template.v1'; template_id: string; revision: number;
  title: string; description: string; requirements: string[]; scope: 'draft_only';
  execution_authorized: false; template_digest: string;
};
export type WorkflowTemplate = TemplateMetadata & (
  { surface: 'chat'; settings: ChatWorkflowSettings }
  | { surface: 'studio'; settings: StudioWorkflowSettings }
  | { surface: 'crawler'; settings: CrawlerWorkflowSettings }
);
export type WorkflowCatalog = {
  schema_version: 'skeleton.ai.workflow_catalog.v1'; catalog_version: number;
  catalog_digest: string; templates: WorkflowTemplate[]; execution_authorized: false;
};
type AccountScope = { token: string; principalId: string; tenantId: string };
export type WorkflowCatalogObservation = { catalog: WorkflowCatalog; scope: AccountScope; observedAt: number };

type Fields = Record<string, unknown>;
const ROOT = '/api/ai/workflow-templates';
const HASH = /^[a-f0-9]{64}$/;
const OPTIONS = { timeoutMs: 15000, retries: 0, maxResponseChars: 128 * 1024 };
const TEMPLATE_FIELDS = ['schema_version', 'template_id', 'revision', 'surface', 'title', 'description', 'settings', 'requirements', 'scope', 'execution_authorized', 'template_digest'];
const SETTINGS = {
  chat: ['max_tokens', 'review_response'],
  studio: ['max_steps', 'max_model_calls', 'max_jobs', 'max_output_tokens', 'authorization_seconds', 'completion_mode'],
  crawler: ['max_requests', 'max_documents', 'max_bytes', 'max_depth'],
} as const;

function invalid(message: string): never {
  throw new ChatClientError(message, { kind: 'protocol', code: 'workflow_template_invalid', retryable: false });
}
function object(value: unknown): value is Fields { return !!value && typeof value === 'object' && !Array.isArray(value); }
function exact(value: Fields, fields: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === fields.length && keys.every(key => fields.includes(key));
}
function integer(value: unknown, minimum: number, maximum: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum && Number(value) <= maximum;
}
function text(value: unknown, maximum: number): value is string {
  return typeof value === 'string' && !!value && value === value.trim() && value.length <= maximum
    && !/[\u0000-\u001f\u007f]/.test(value)
    && !Array.from(value).some(character => { const point = character.codePointAt(0)!; return point >= 0xd800 && point <= 0xdfff; });
}
function identity(value: unknown): string {
  if (!text(value, 512)) invalid('Your authenticated account identity is incomplete. Verify your session again.');
  return value.trim();
}
function current(token: string, signal?: AbortSignal): void {
  if (signal?.aborted) throw new ChatClientError('Workflow template inspection detached.', { kind: 'cancelled', retryable: false });
  if (getAuthToken() !== token) throw new ChatClientError('Your account changed. Reload workflow templates before applying a draft.', { kind: 'authorization', code: 'workflow_account_changed', retryable: false });
}
async function read<T>(request: Promise<ApiResult<T>>, token: string, signal?: AbortSignal): Promise<T> {
  const result = await request;
  current(token, signal);
  if (!result.ok || result.data == null) throw chatApiError(result, 'Workflow templates could not be loaded. Check your account and application connection.');
  return result.data;
}
async function account(signal?: AbortSignal, expected?: AccountScope): Promise<AccountScope> {
  const token = getAuthToken();
  current(token, signal);
  const me = await read(api.get<unknown>('/api/auth/me', { ...OPTIONS, signal, headers: authHeaders() }), token, signal);
  if (!object(me) || me.authenticated !== true || !object(me.user)) {
    throw new ChatClientError('Sign in to inspect workflow templates.', { kind: 'authorization', retryable: false });
  }
  const scope = { token, principalId: identity(me.user.email || me.user.user_id), tenantId: identity(me.user.tenant_id || 'default') };
  if (expected && (expected.token !== scope.token || expected.principalId !== scope.principalId || expected.tenantId !== scope.tenantId)) {
    throw new ChatClientError('The workflow template observation belongs to a different account. Reload it before applying.', { kind: 'authorization', code: 'workflow_scope_changed', retryable: false });
  }
  return scope;
}

function template(value: unknown): WorkflowTemplate {
  if (!object(value) || !exact(value, TEMPLATE_FIELDS) || value.schema_version !== 'skeleton.ai.workflow_template.v1'
    || !['chat', 'studio', 'crawler'].includes(String(value.surface)) || !integer(value.revision, 1, 1_000_000)
    || !text(value.template_id, 96) || !/^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,3}$/.test(value.template_id)
    || !value.template_id.startsWith(`${value.surface}.`) || !text(value.title, 80) || !text(value.description, 512)
    || value.scope !== 'draft_only' || value.execution_authorized !== false || !HASH.test(String(value.template_digest))
    || !Array.isArray(value.requirements) || !value.requirements.length || value.requirements.length > 8 || value.requirements.some(item => !text(item, 160))
    || new Set(value.requirements).size !== value.requirements.length || !object(value.settings)) invalid('A workflow template has unsupported fields or authority. Refresh its catalog.');
  const settings = value.settings;
  const surface = value.surface as WorkflowSurface;
  if (!exact(settings, SETTINGS[surface])) invalid('A workflow template changes unsupported form settings.');
  if (surface === 'chat' && (!integer(settings.max_tokens, 1, 8192) || typeof settings.review_response !== 'boolean')) invalid('The chat template answer budget is invalid.');
  if (surface === 'studio' && (!integer(settings.max_steps, 1, 16) || !integer(settings.max_model_calls, 1, 16)
    || !integer(settings.max_jobs, 0, 8) || !integer(settings.max_output_tokens, 256, 4096)
    || !integer(settings.authorization_seconds, 60, 3600) || !['native', 'original'].includes(String(settings.completion_mode)))) invalid('The studio template exceeds the bounded goal settings.');
  if (surface === 'crawler' && (!integer(settings.max_requests, 1, 128) || !integer(settings.max_documents, 1, 64)
    || !integer(settings.max_bytes, 1024, 33554432) || !integer(settings.max_depth, 0, 3))) invalid('The capture template exceeds the bounded acquisition settings.');
  return value as WorkflowTemplate;
}

/** Canonical encoding is exact here because every allowed number is a bounded
 * integer and all object keys belong to the ASCII schema whitelist. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  const encoded = JSON.stringify(value);
  if (encoded === undefined) invalid('The workflow catalog contains an unsupported JSON value.');
  return encoded;
}

async function verifyCatalogDigests(value: WorkflowCatalog): Promise<void> {
  await Promise.all(value.templates.map(async item => {
    const { template_digest, ...content } = item;
    const expected = await digestStringAsync(CryptoDigestAlgorithm.SHA256, canonical(content));
    if (expected !== template_digest) invalid('A workflow template digest does not match its displayed settings. Reload the catalog.');
  }));
  const { catalog_digest, ...content } = value;
  const expected = await digestStringAsync(CryptoDigestAlgorithm.SHA256, canonical(content));
  if (expected !== catalog_digest) invalid('The workflow catalog digest does not match its templates. Reload the catalog.');
}

/** Inspect a bounded draft catalog. Parsed values never grant execution or readiness. */
function catalog(value: unknown): WorkflowCatalog {
  if (!object(value) || !exact(value, ['schema_version', 'catalog_version', 'catalog_digest', 'templates', 'execution_authorized'])
    || value.schema_version !== 'skeleton.ai.workflow_catalog.v1' || !integer(value.catalog_version, 1, 1_000_000)
    || !HASH.test(String(value.catalog_digest)) || value.execution_authorized !== false
    || !Array.isArray(value.templates) || !value.templates.length || value.templates.length > 16) invalid('The workflow catalog is unsupported or exceeds its bounds.');
  // Response parsing occurs inside the transport's 128 KiB bound. This second
  // limit applies to the catalog itself, independent of the scoped wrapper.
  let encoded: string;
  try { encoded = JSON.stringify(value); } catch { return invalid('The workflow catalog is not bounded JSON.'); }
  if (new TextEncoder().encode(encoded).byteLength > 65536) invalid('The workflow catalog exceeds 64 KiB.');
  const templates = value.templates.map(template);
  if (new Set(templates.map(item => item.template_id)).size !== templates.length) invalid('The workflow catalog contains duplicate template identities.');
  return { schema_version: 'skeleton.ai.workflow_catalog.v1', catalog_version: value.catalog_version as number,
    catalog_digest: value.catalog_digest as string, execution_authorized: false, templates };
}

async function observedCatalog(scope: AccountScope, signal?: AbortSignal): Promise<WorkflowCatalogObservation> {
  const result = await read(api.get<unknown>(ROOT, { ...OPTIONS, signal, headers: authHeaders() }), scope.token, signal);
  if (!object(result) || !exact(result, ['schema_version', 'actor_id', 'tenant_id', 'catalog'])
    || result.schema_version !== 'skeleton.ai.workflow_templates.v1'
    || identity(result.actor_id) !== scope.principalId || identity(result.tenant_id) !== scope.tenantId) {
    throw new ChatClientError('Workflow templates do not match the verified account. Reload the current session.', { kind: 'authorization', code: 'workflow_scope_mismatch', retryable: false });
  }
  const checked = catalog(result.catalog);
  await verifyCatalogDigests(checked);
  current(scope.token, signal);
  return { catalog: checked, scope, observedAt: Date.now() };
}

export async function getAIWorkflowCatalog(signal?: AbortSignal): Promise<WorkflowCatalogObservation> {
  return observedCatalog(await account(signal), signal);
}

/** Recheck account and exact catalog identity before staging an explicit draft. */
export async function authorizeWorkflowTemplate(
  observed: WorkflowCatalogObservation, selected: WorkflowTemplate, signal?: AbortSignal,
): Promise<WorkflowTemplate> {
  current(observed.scope.token, signal);
  const scope = await account(signal, observed.scope);
  const fresh = await observedCatalog(scope, signal);
  if (fresh.catalog.catalog_digest !== observed.catalog.catalog_digest) {
    throw new ChatClientError('Workflow templates changed since inspection. Reload the catalog and review the current settings.', { kind: 'conflict', code: 'workflow_catalog_changed', retryable: false });
  }
  const retained = observed.catalog.templates.find(item => item.template_id === selected.template_id);
  const next = fresh.catalog.templates.find(item => item.template_id === selected.template_id);
  if (!retained || !next || retained.template_digest !== selected.template_digest || next.template_digest !== selected.template_digest
    || next.revision !== selected.revision || next.surface !== selected.surface) invalid('The selected workflow template does not match the current catalog.');
  return next;
}

export function workflowTemplateSummary(value: WorkflowTemplate): string[] {
  if (value.surface === 'chat') return [`${value.settings.max_tokens.toLocaleString()} answer tokens`, value.settings.review_response ? 'Review and refine selected' : 'Direct response selected'];
  if (value.surface === 'studio') return [`${value.settings.max_steps} actions · ${value.settings.max_model_calls} model calls · ${value.settings.max_jobs} jobs`, `${value.settings.max_output_tokens.toLocaleString()} decision tokens · ${value.settings.authorization_seconds / 60} min authorization window`, `${value.settings.completion_mode === 'original' ? 'Original' : 'Native'} workflow draft`];
  return [`${value.settings.max_requests} requests · ${value.settings.max_documents} documents`, `${(value.settings.max_bytes / 1048576).toLocaleString()} MiB · depth ${value.settings.max_depth}`];
}
