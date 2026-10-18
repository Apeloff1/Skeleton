import { ChatClientError } from './chatErrors';

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
  for (const key of ['tokenizer', 'limits_source', 'model_family', 'execution_mode']) {
    if (row[key] != null && (typeof row[key] !== 'string' || row[key].length > 160)) return fail();
  }
}
