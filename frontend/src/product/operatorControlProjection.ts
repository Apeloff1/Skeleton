import type { CanonicalOperationState } from './workspaceProjection';

export type OperatorControlAction =
  | 'cancel'
  | 'interrupt'
  | 'override'
  | 'pause'
  | 'resume';

export type HumanControlAction =
  | 'interrupt'
  | 'override'
  | 'pause'
  | 'resume';

export type OperatorControlProjection = {
  schema_version: 1;
  task_id: 'P1-PROD-04';
  accountability_id: 'ACC-P1-PROD-04';
  operation_id: string;
  tenant_id: string;
  canonical_state: CanonicalOperationState;
  terminal: boolean;
  cancelled: boolean;
  workspace_projection_digest: string;
  workspace_decision_digest: string;
  control_known: boolean;
  last_action: HumanControlAction | null;
  human_control_receipt_digest: string | null;
  control_version: number | null;
  paused: boolean | null;
  interrupted: boolean | null;
  autonomy_level: 0 | 1 | 2 | 3 | 4 | null;
  previous_control_receipt_digest: string | null;
  available_actions: OperatorControlAction[];
  canonical_operation_authority: 'durable-workspace-projection';
  human_control_authority: 'p1-auto-04-human-control' | null;
  production_authority: false;
};

const TERMINAL = new Set<CanonicalOperationState>([
  'completed',
  'failed',
  'cancelled',
]);

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

const HUMAN_ACTIONS = new Set<HumanControlAction>([
  'interrupt',
  'override',
  'pause',
  'resume',
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

function digest(value: unknown, label: string): string {
  const parsed = text(value, label);
  if (!SHA256.test(parsed)) {
    throw new Error(`${label} must be lowercase sha256`);
  }
  return parsed;
}

function positiveInteger(value: unknown, label: string): number {
  if (!Number.isInteger(value) || (value as number) < 1) {
    throw new Error(`${label} must be a positive integer`);
  }
  return value as number;
}

function autonomyLevel(value: unknown): 0 | 1 | 2 | 3 | 4 {
  if (![0, 1, 2, 3, 4].includes(value as number)) {
    throw new Error('autonomy_level must be within [0, 4]');
  }
  return value as 0 | 1 | 2 | 3 | 4;
}

function expectedActions(
  terminal: boolean,
  paused: boolean | null,
  interrupted: boolean | null,
): OperatorControlAction[] {
  if (terminal) return [];
  if (paused === null || interrupted === null) return ['cancel'];
  if (paused || interrupted) return ['cancel', 'resume'];
  return ['cancel', 'interrupt', 'override', 'pause'];
}

function sameActions(
  actual: OperatorControlAction[],
  expected: OperatorControlAction[],
): boolean {
  return actual.length === expected.length
    && actual.every((value, index) => value === expected[index]);
}

export function decodeOperatorControlProjection(
  value: unknown,
): OperatorControlProjection {
  const row = record(value, 'operator control projection');

  if (row.schema_version !== 1) {
    throw new Error('unsupported operator-control projection schema');
  }
  if (row.task_id !== 'P1-PROD-04') {
    throw new Error('operator-control task identity drift');
  }
  if (row.accountability_id !== 'ACC-P1-PROD-04') {
    throw new Error('operator-control accountability identity drift');
  }
  if (row.canonical_operation_authority !== 'durable-workspace-projection') {
    throw new Error('canonical operation authority drift');
  }
  if (row.production_authority !== false) {
    throw new Error('operator-control projection cannot claim production authority');
  }

  const stateValue = text(row.canonical_state, 'canonical_state');
  if (!STATES.has(stateValue as CanonicalOperationState)) {
    throw new Error('invalid canonical operation state');
  }
  const canonicalState = stateValue as CanonicalOperationState;
  if (typeof row.terminal !== 'boolean') {
    throw new Error('terminal must be boolean');
  }
  const terminal = row.terminal;
  if (terminal !== TERMINAL.has(canonicalState)) {
    throw new Error('terminal must derive from canonical state');
  }
  if (typeof row.cancelled !== 'boolean') {
    throw new Error('cancelled must be boolean');
  }
  const cancelled = row.cancelled;
  if (cancelled !== (canonicalState === 'cancelled')) {
    throw new Error('cancelled must derive from canonical state');
  }

  if (typeof row.control_known !== 'boolean') {
    throw new Error('control_known must be boolean');
  }
  const controlKnown = row.control_known;
  let lastAction: HumanControlAction | null = null;
  let receiptDigest: string | null = null;
  let controlVersion: number | null = null;
  let paused: boolean | null = null;
  let interrupted: boolean | null = null;
  let level: 0 | 1 | 2 | 3 | 4 | null = null;
  let previousReceipt: string | null = null;

  if (controlKnown) {
    const action = text(row.last_action, 'last_action');
    if (!HUMAN_ACTIONS.has(action as HumanControlAction)) {
      throw new Error('last_action is not a projectable human control');
    }
    lastAction = action as HumanControlAction;
    receiptDigest = digest(
      row.human_control_receipt_digest,
      'human_control_receipt_digest',
    );
    controlVersion = positiveInteger(row.control_version, 'control_version');
    if (typeof row.paused !== 'boolean') {
      throw new Error('known control state requires paused boolean');
    }
    if (typeof row.interrupted !== 'boolean') {
      throw new Error('known control state requires interrupted boolean');
    }
    paused = row.paused;
    interrupted = row.interrupted;
    level = autonomyLevel(row.autonomy_level);
    previousReceipt = row.previous_control_receipt_digest === null
      ? null
      : digest(
        row.previous_control_receipt_digest,
        'previous_control_receipt_digest',
      );
    if (row.human_control_authority !== 'p1-auto-04-human-control') {
      throw new Error('human control authority drift');
    }
  } else {
    for (const [name, item] of [
      ['last_action', row.last_action],
      ['human_control_receipt_digest', row.human_control_receipt_digest],
      ['control_version', row.control_version],
      ['paused', row.paused],
      ['interrupted', row.interrupted],
      ['autonomy_level', row.autonomy_level],
      ['previous_control_receipt_digest', row.previous_control_receipt_digest],
      ['human_control_authority', row.human_control_authority],
    ] as const) {
      if (item !== null) {
        throw new Error(`unknown control state cannot set ${name}`);
      }
    }
  }

  if (!Array.isArray(row.available_actions)) {
    throw new Error('available_actions must be an array');
  }
  const available = row.available_actions.map((item, index) => {
    const action = text(item, `available_actions[${index}]`);
    if (!['cancel', 'interrupt', 'override', 'pause', 'resume'].includes(action)) {
      throw new Error('invalid available operator action');
    }
    return action as OperatorControlAction;
  });
  const expected = expectedActions(terminal, paused, interrupted);
  if (!sameActions(available, expected)) {
    throw new Error('available_actions do not derive from canonical control state');
  }
  if (terminal && available.length !== 0) {
    throw new Error('terminal operation cannot expose live controls');
  }

  return {
    schema_version: 1,
    task_id: 'P1-PROD-04',
    accountability_id: 'ACC-P1-PROD-04',
    operation_id: text(row.operation_id, 'operation_id'),
    tenant_id: text(row.tenant_id, 'tenant_id'),
    canonical_state: canonicalState,
    terminal,
    cancelled,
    workspace_projection_digest: digest(
      row.workspace_projection_digest,
      'workspace_projection_digest',
    ),
    workspace_decision_digest: digest(
      row.workspace_decision_digest,
      'workspace_decision_digest',
    ),
    control_known: controlKnown,
    last_action: lastAction,
    human_control_receipt_digest: receiptDigest,
    control_version: controlVersion,
    paused,
    interrupted,
    autonomy_level: level,
    previous_control_receipt_digest: previousReceipt,
    available_actions: available,
    canonical_operation_authority: 'durable-workspace-projection',
    human_control_authority: controlKnown ? 'p1-auto-04-human-control' : null,
    production_authority: false,
  };
}
