import { ChatClientError } from './chatErrors';

export type ChatModelRuntimeFacts = {
  serving_state?: { draining: boolean; active: number; queued: number; effective_concurrency: number } | null;
  semantic_verifier_configured?: boolean;
  semantic_verifier_route?: boolean;
  generation_limits?: { max_output_utf8_bytes?: number | null; [key: string]: unknown } | null;
};

/** Reject malformed inventory before controls can select an unobserved model. */
export function validateChatModel(value: unknown): void {
  const fail = (): never => { throw new ChatClientError('The configured model inventory is invalid. Refresh readiness before selecting a model.', { kind: 'protocol', code: 'invalid_catalog', retryable: false }); };
  if (!value || typeof value !== 'object' || Array.isArray(value)) return fail();
  const row = value as Record<string, unknown>;
  for (const [key, limit] of [['id', 512], ['provider_id', 128], ['model_id', 256], ['label', 1024]] as const) {
    if (typeof row[key] !== 'string' || !row[key] || row[key].length > limit) return fail();
  }
  for (const key of ['selectable', 'available', 'active', 'credential_free']) if (typeof row[key] !== 'boolean') return fail();
  if (row.selectable === true && row.available !== true) return fail();
  for (const key of ['context_window', 'max_output_tokens', 'default_output_tokens']) {
    if (!Number.isSafeInteger(row[key]) || (row[key] as number) < 1 || (row[key] as number) > 10000000) return fail();
  }
  if ((row.default_output_tokens as number) > (row.max_output_tokens as number)) return fail();
  if (!Array.isArray(row.capabilities) || row.capabilities.length > 64
    || row.capabilities.some(capability => typeof capability !== 'string' || !capability || capability.length > 128)
    || new Set(row.capabilities).size !== row.capabilities.length) return fail();
  if (row.selectable === true && !row.capabilities.includes('text-generation')) return fail();
  const readiness = row.readiness;
  if (!readiness || typeof readiness !== 'object' || Array.isArray(readiness)) return fail();
  const issue = readiness as Record<string, unknown>;
  if (typeof issue.code !== 'string' || !issue.code || issue.code.length > 160
    || typeof issue.message !== 'string' || issue.message.length > 4000
    || issue.action != null && (typeof issue.action !== 'string' || issue.action.length > 4000)) return fail();
  if (row.supports_temperature !== undefined && typeof row.supports_temperature !== 'boolean') return fail();
  if (row.fallback !== undefined && typeof row.fallback !== 'boolean') return fail();
  for (const key of ['semantic_verifier_configured', 'semantic_verifier_route']) if (row[key] !== undefined && typeof row[key] !== 'boolean') return fail();
  if (row.serving_state != null) {
    if (!row.serving_state || typeof row.serving_state !== 'object' || Array.isArray(row.serving_state)) return fail();
    const serving = row.serving_state as Record<string, unknown>;
    if (typeof serving.draining !== 'boolean' || ['active', 'queued', 'effective_concurrency'].some(key => !Number.isSafeInteger(serving[key]) || Number(serving[key]) < 0)) return fail();
  }
  if (row.generation_limits != null) {
    if (!row.generation_limits || typeof row.generation_limits !== 'object' || Array.isArray(row.generation_limits)) return fail();
    const limits = row.generation_limits as Record<string, unknown>;
    if (limits.max_output_utf8_bytes != null && (!Number.isSafeInteger(limits.max_output_utf8_bytes) || Number(limits.max_output_utf8_bytes) < 1)) return fail();
  }
  if (row.activation != null) {
    if (typeof row.activation !== 'object' || Array.isArray(row.activation)) return fail();
    const activation = row.activation as Record<string, unknown>;
    if (activation.model_id !== row.model_id || typeof activation.schema !== 'string' || activation.schema.length > 160) return fail();
    for (const key of ['model_digest', 'artifact_sha256']) if (typeof activation[key] !== 'string' || !/^[a-f0-9]{64}$/.test(activation[key] as string)) return fail();
    for (const key of ['runtime_digest', 'manifest_digest', 'catalog_digest', 'catalog_entry_digest', 'catalog_source_sha256']) if (activation[key] != null && (typeof activation[key] !== 'string' || !/^[a-f0-9]{64}$/.test(activation[key] as string))) return fail();
    if (activation.source_model_id != null && (typeof activation.source_model_id !== 'string' || !activation.source_model_id || activation.source_model_id.length > 256)) return fail();
  }
  for (const key of ['tokenizer', 'limits_source', 'model_family', 'execution_mode']) {
    if (row[key] != null && (typeof row[key] !== 'string' || row[key].length > 160)) return fail();
  }
}
