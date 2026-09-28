export type CanonicalOperationState =
  | 'created'
  | 'validated'
  | 'authorized'
  | 'admitted'
  | 'queued'
  | 'running'
  | 'waiting_for_tool'
  | 'waiting_for_user'
  | 'retrying'
  | 'degraded'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type ProjectionEvidence = {
  source: string;
  digest: string;
  category: string;
};

export type WorkspaceProgress = {
  completed_units: number;
  total_units: number;
  fraction: number;
  label: string;
  evidence: ProjectionEvidence;
};

export type WorkspaceBlocker = {
  blocker_id: string;
  summary: string;
  severity: 'info' | 'warning' | 'blocking';
  evidence: ProjectionEvidence;
};

export type WorkspaceCost = {
  spent_units: number;
  remaining_units: number | null;
  unit: string;
  evidence: ProjectionEvidence;
};

export type WorkspaceTerminalResult = {
  summary: string;
  result: ProjectionEvidence;
};

export type WorkspaceProjection = {
  schema_version: 1;
  task_id: 'P1-PROD-03';
  accountability_id: 'ACC-P1-PROD-03';
  operation_id: string;
  tenant_id: string;
  trace_id: string;
  canonical_state: CanonicalOperationState;
  operation_version: number;
  cursor_sequence: number;
  terminal: boolean;
  operation_projection_digest: string;
  projection_authority_digest: string;
  progress: WorkspaceProgress | null;
  blockers: WorkspaceBlocker[];
  cost: WorkspaceCost | null;
  evidence: ProjectionEvidence[];
  terminal_result: WorkspaceTerminalResult | null;
  canonical_authority: 'durable-operation-projection';
  production_authority: false;
};

const STATES = new Set<CanonicalOperationState>([
  'created',
  'validated',
  'authorized',
  'admitted',
  'queued',
  'running',
  'waiting_for_tool',
  'waiting_for_user',
  'retrying',
  'degraded',
  'completed',
  'failed',
  'cancelled',
]);

const TERMINAL = new Set<CanonicalOperationState>([
  'completed',
  'failed',
  'cancelled',
]);

const SHA256 = /^[0-9a-f]{64}$/;

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value || value !== value.trim()) {
    throw new Error(`${label} must be normalized non-empty text`);
  }
  return value;
}

function positiveInteger(value: unknown, label: string): number {
  if (!Number.isInteger(value) || (value as number) < 1) {
    throw new Error(`${label} must be a positive integer`);
  }
  return value as number;
}

function nonnegativeNumber(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be finite and non-negative`);
  }
  return value;
}

function digest(value: unknown, label: string): string {
  const parsed = text(value, label);
  if (!SHA256.test(parsed)) {
    throw new Error(`${label} must be lowercase sha256`);
  }
  return parsed;
}

function evidence(value: unknown, label: string): ProjectionEvidence {
  const row = record(value, label);
  return {
    source: text(row.source, `${label}.source`),
    digest: digest(row.digest, `${label}.digest`),
    category: text(row.category, `${label}.category`),
  };
}

function progress(value: unknown): WorkspaceProgress | null {
  if (value === null) return null;
  const row = record(value, 'progress');
  const completed = nonnegativeNumber(row.completed_units, 'progress.completed_units');
  const total = positiveInteger(row.total_units, 'progress.total_units');
  const fraction = nonnegativeNumber(row.fraction, 'progress.fraction');
  if (!Number.isInteger(completed) || completed > total) {
    throw new Error('progress completed_units is invalid');
  }
  if (fraction < 0 || fraction > 1 || Math.abs(fraction - completed / total) > 1e-12) {
    throw new Error('progress fraction does not match completed/total');
  }
  return {
    completed_units: completed,
    total_units: total,
    fraction,
    label: text(row.label, 'progress.label'),
    evidence: evidence(row.evidence, 'progress.evidence'),
  };
}

function blockers(value: unknown): WorkspaceBlocker[] {
  if (!Array.isArray(value)) throw new Error('blockers must be an array');
  const seen = new Set<string>();
  return value.map((item, index) => {
    const row = record(item, `blockers[${index}]`);
    const blockerId = text(row.blocker_id, `blockers[${index}].blocker_id`);
    if (seen.has(blockerId)) throw new Error('blocker IDs must be unique');
    seen.add(blockerId);
    const severity = text(row.severity, `blockers[${index}].severity`);
    if (!['info', 'warning', 'blocking'].includes(severity)) {
      throw new Error('invalid blocker severity');
    }
    return {
      blocker_id: blockerId,
      summary: text(row.summary, `blockers[${index}].summary`),
      severity: severity as WorkspaceBlocker['severity'],
      evidence: evidence(row.evidence, `blockers[${index}].evidence`),
    };
  });
}

function cost(value: unknown): WorkspaceCost | null {
  if (value === null) return null;
  const row = record(value, 'cost');
  return {
    spent_units: nonnegativeNumber(row.spent_units, 'cost.spent_units'),
    remaining_units: row.remaining_units === null
      ? null
      : nonnegativeNumber(row.remaining_units, 'cost.remaining_units'),
    unit: text(row.unit, 'cost.unit'),
    evidence: evidence(row.evidence, 'cost.evidence'),
  };
}

function terminalResult(value: unknown): WorkspaceTerminalResult | null {
  if (value === null) return null;
  const row = record(value, 'terminal_result');
  return {
    summary: text(row.summary, 'terminal_result.summary'),
    result: evidence(row.result, 'terminal_result.result'),
  };
}

export function decodeWorkspaceProjection(value: unknown): WorkspaceProjection {
  const row = record(value, 'workspace projection');

  if (row.schema_version !== 1) throw new Error('unsupported workspace projection schema');
  if (row.task_id !== 'P1-PROD-03') throw new Error('workspace task identity drift');
  if (row.accountability_id !== 'ACC-P1-PROD-03') {
    throw new Error('workspace accountability identity drift');
  }
  if (row.canonical_authority !== 'durable-operation-projection') {
    throw new Error('workspace canonical authority drift');
  }
  if (row.production_authority !== false) {
    throw new Error('workspace projection cannot claim production authority');
  }

  const state = text(row.canonical_state, 'canonical_state');
  if (!STATES.has(state as CanonicalOperationState)) {
    throw new Error('invalid canonical operation state');
  }
  const canonicalState = state as CanonicalOperationState;
  const terminal = row.terminal;
  if (typeof terminal !== 'boolean') throw new Error('terminal must be boolean');
  if (terminal !== TERMINAL.has(canonicalState)) {
    throw new Error('terminal flag must derive from canonical state');
  }

  const result = terminalResult(row.terminal_result);
  if (terminal && result === null) {
    throw new Error('terminal workspace projection requires terminal result');
  }
  if (!terminal && result !== null) {
    throw new Error('non-terminal workspace projection cannot include terminal result');
  }

  if (!Array.isArray(row.evidence)) throw new Error('evidence must be an array');
  const evidenceRows = row.evidence.map((item, index) => (
    evidence(item, `evidence[${index}]`)
  ));

  const operationVersion = positiveInteger(
    row.operation_version,
    'operation_version',
  );
  const cursorSequence = positiveInteger(
    row.cursor_sequence,
    'cursor_sequence',
  );
  if (operationVersion !== cursorSequence) {
    throw new Error('workspace cursor must match canonical operation version');
  }

  return {
    schema_version: 1,
    task_id: 'P1-PROD-03',
    accountability_id: 'ACC-P1-PROD-03',
    operation_id: text(row.operation_id, 'operation_id'),
    tenant_id: text(row.tenant_id, 'tenant_id'),
    trace_id: text(row.trace_id, 'trace_id'),
    canonical_state: canonicalState,
    operation_version: operationVersion,
    cursor_sequence: cursorSequence,
    terminal,
    operation_projection_digest: digest(
      row.operation_projection_digest,
      'operation_projection_digest',
    ),
    projection_authority_digest: digest(
      row.projection_authority_digest,
      'projection_authority_digest',
    ),
    progress: progress(row.progress),
    blockers: blockers(row.blockers),
    cost: cost(row.cost),
    evidence: evidenceRows,
    terminal_result: result,
    canonical_authority: 'durable-operation-projection',
    production_authority: false,
  };
}
