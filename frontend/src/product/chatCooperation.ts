import { ChatClientError } from './chatErrors';

export type ChatCooperationRole = 'plan' | 'draft' | 'critique' | 'refine';
export type ChatCooperationPolicy = {
  schema_version: 'skeleton.ai.cooperation.v1';
  review_rounds: number;
  max_stage_output_tokens: number;
  roles: Partial<Record<ChatCooperationRole, { provider_id: string; model_id: string }>>;
};
export type ChatCooperationModel = {
  id: string; provider_id: string; model_id: string; label: string; available: boolean; selectable: boolean;
  credential_free: boolean; capabilities: readonly string[]; context_window?: number | null;
  max_output_tokens?: number | null; readiness?: { message?: string } | null;
};
export const COOPERATION_ROLES: readonly { role: ChatCooperationRole; label: string }[] = [
  { role: 'plan', label: 'Planning' }, { role: 'draft', label: 'Drafting' },
  { role: 'critique', label: 'Review' }, { role: 'refine', label: 'Refinement' },
];
export function cooperationStageCount(policy: ChatCooperationPolicy): number { return 2 + 2 * policy.review_rounds; }
export function minimumCooperationTokens(policy: ChatCooperationPolicy): number { return 64 * cooperationStageCount(policy); }
export function cooperationModelReady(model: ChatCooperationModel): boolean {
  return model.available && model.selectable && model.capabilities.includes('text-generation')
    && Number.isSafeInteger(model.max_output_tokens) && (model.max_output_tokens ?? 0) >= 64
    && Number.isSafeInteger(model.context_window) && (model.context_window ?? 0) > 64;
}
/** Readiness can restrict a choice; only the engine can admit its actual context. */
export function cooperationConfigurationIssues(policy: ChatCooperationPolicy, models: readonly ChatCooperationModel[], answerTokenLimit?: number): string[] {
  const issues: string[] = [];
  try { normalizeChatCooperation(policy); } catch (error) { return [error instanceof Error ? error.message : 'The review settings are invalid.']; }
  const minimum = minimumCooperationTokens(policy);
  if (answerTokenLimit !== undefined && (!Number.isSafeInteger(answerTokenLimit) || answerTokenLimit < minimum)) issues.push(`${policy.review_rounds} review ${policy.review_rounds === 1 ? 'round needs' : 'rounds need'} at least ${minimum.toLocaleString()} total answer tokens. Increase the shared answer budget or reduce the rounds.`);
  for (const { role, label } of COOPERATION_ROLES) {
    const pair = policy.roles[role]; if (!pair) continue;
    const model = models.find(row => row.provider_id === pair.provider_id && row.model_id === pair.model_id);
    if (!model || !cooperationModelReady(model)) issues.push(`${label} model ${pair.model_id} is not currently available for this text workflow. Refresh models or choose another explicit model.`);
  }
  return issues;
}
export type ChatCooperationSummary = {
  schema_version: 'skeleton.ai.cooperation.v1'; policy_digest: string; brief_digest: string; source_snapshot_digest: string;
  completed_stages: number; total_stages: number; complete: boolean; independent_review_certified: false;
  artifacts: { stage_id: string; role: ChatCooperationRole; output_digest: string; request_digest: string;
    provider_receipt: string; provider: string; model: string }[];
};

export function validateChatCooperationSummary(value: ChatCooperationSummary): ChatCooperationSummary {
  const fail = (): never => { throw new ChatClientError('The recorded response-review evidence is invalid. Reopen the saved turn to recover its canonical answer.', { kind: 'protocol', code: 'invalid_cooperation_evidence', retryable: false }); };
  const hash = (raw: unknown) => typeof raw === 'string' && /^[a-f0-9]{64}$/.test(raw);
  if (!value || value.schema_version !== 'skeleton.ai.cooperation.v1' || !hash(value.policy_digest) || !hash(value.brief_digest)
    || !hash(value.source_snapshot_digest) || ![4, 6, 8].includes(value.total_stages) || !Number.isSafeInteger(value.completed_stages)
    || value.completed_stages < 0 || value.completed_stages > value.total_stages || typeof value.complete !== 'boolean'
    || value.complete !== (value.completed_stages === value.total_stages) || value.independent_review_certified !== false
    || !Array.isArray(value.artifacts) || value.artifacts.length !== value.completed_stages) return fail();
  const stages: { id: string; role: ChatCooperationRole }[] = [{ id: 'plan', role: 'plan' }, { id: 'draft', role: 'draft' }];
  for (let round = 1; stages.length < value.total_stages; round += 1) stages.push({ id: `critique:${round}`, role: 'critique' }, { id: `refine:${round}`, role: 'refine' });
  const receipts = new Set<string>();
  for (const [index, artifact] of value.artifacts.entries()) {
    if (!artifact || artifact.stage_id !== stages[index].id || artifact.role !== stages[index].role
      || !hash(artifact.output_digest) || !hash(artifact.request_digest)
      || typeof artifact.provider_receipt !== 'string' || !artifact.provider_receipt || artifact.provider_receipt.length > 512
      || receipts.has(artifact.provider_receipt) || typeof artifact.provider !== 'string' || !artifact.provider || artifact.provider.length > 128
      || typeof artifact.model !== 'string' || !artifact.model || artifact.model.length > 256) return fail();
    receipts.add(artifact.provider_receipt);
  }
  return value;
}

/** Monotonic projection of one bound operation; receipt prefixes are immutable. */
export function reconcileChatCooperation(previous: ChatCooperationSummary | null | undefined, incoming: ChatCooperationSummary): ChatCooperationSummary {
  validateChatCooperationSummary(incoming);
  if (!previous) return incoming;
  validateChatCooperationSummary(previous);
  if (previous.policy_digest !== incoming.policy_digest || previous.brief_digest !== incoming.brief_digest
    || previous.source_snapshot_digest !== incoming.source_snapshot_digest || previous.total_stages !== incoming.total_stages) {
    throw new ChatClientError('The saved response-review identity changed. Reopen the canonical turn.', { kind: 'protocol', code: 'cooperation_identity_changed', retryable: false });
  }
  for (let index = 0; index < Math.min(previous.artifacts.length, incoming.artifacts.length); index += 1) {
    const before = previous.artifacts[index]; const after = incoming.artifacts[index];
    if (['stage_id', 'role', 'output_digest', 'request_digest', 'provider_receipt', 'provider', 'model'].some(key => before[key as keyof typeof before] !== after[key as keyof typeof after])) {
      throw new ChatClientError('A recorded response-review receipt changed. Reopen the canonical turn.', { kind: 'protocol', code: 'cooperation_receipt_changed', retryable: false });
    }
  }
  return incoming.completed_stages < previous.completed_stages ? previous : incoming;
}

export function validateChatCooperationReceipts(summary: ChatCooperationSummary, references: unknown): void {
  if (!Array.isArray(references) || references.length > 256 || references.some(value => typeof value !== 'string' || !value || value.length > 512)
    || new Set(references).size !== references.length || summary.artifacts.some(artifact => !references.includes(artifact.provider_receipt))) {
    throw new ChatClientError('The response-review stages do not match the recorded model receipts.', { kind: 'protocol', code: 'cooperation_receipts_unbound', retryable: false });
  }
}

export function reviewedResponsePolicy(): ChatCooperationPolicy {
  return { schema_version: 'skeleton.ai.cooperation.v1', review_rounds: 1, max_stage_output_tokens: 512, roles: {} };
}

/** Snapshot exact reviewed-response settings before admission or device persistence. */
export function normalizeChatCooperation(value: unknown): ChatCooperationPolicy {
  const invalid = (): never => { throw new ChatClientError('The saved response-review settings are invalid. Reopen the saved turn before continuing.', { kind: 'validation', code: 'invalid_cooperation_policy', retryable: false }); };
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid();
  const policy = value as Record<string, unknown>;
  if (Object.keys(policy).some(key => !['schema_version', 'review_rounds', 'max_stage_output_tokens', 'roles'].includes(key))
    || policy.schema_version !== 'skeleton.ai.cooperation.v1'
    || !Number.isSafeInteger(policy.review_rounds) || (policy.review_rounds as number) < 1 || (policy.review_rounds as number) > 3
    || !Number.isSafeInteger(policy.max_stage_output_tokens) || (policy.max_stage_output_tokens as number) < 64 || (policy.max_stage_output_tokens as number) > 4096
    || !policy.roles || typeof policy.roles !== 'object' || Array.isArray(policy.roles)) return invalid();
  const roles: ChatCooperationPolicy['roles'] = {};
  const entries = Object.entries(policy.roles);
  if (entries.length > 4) return invalid();
  for (const [role, raw] of entries) {
    if (!['plan', 'draft', 'critique', 'refine'].includes(role) || !raw || typeof raw !== 'object' || Array.isArray(raw)) return invalid();
    const selection = raw as Record<string, unknown>;
    if (Object.keys(selection).length !== 2 || typeof selection.provider_id !== 'string' || !selection.provider_id || selection.provider_id.length > 128
      || typeof selection.model_id !== 'string' || !selection.model_id || selection.model_id.length > 256) return invalid();
    roles[role as ChatCooperationRole] = { provider_id: selection.provider_id, model_id: selection.model_id };
  }
  return { schema_version: 'skeleton.ai.cooperation.v1', review_rounds: policy.review_rounds as number,
    max_stage_output_tokens: policy.max_stage_output_tokens as number, roles };
}
