/**
 * B014 creator command envelopes for visual edits (`creator.command.v1`).
 *
 * Mirrors skeleton/forge/creator/command_surface.py `command_from_ui` /
 * `build_creator_command` for the `edit` operation: same payload field set
 * (target_id, expected_revision, patch), same identifier rules and bounds,
 * same canonical digest. One command per edited graph entity, with optimistic
 * concurrency pinned to the base revision the user started from.
 *
 * This module only builds envelopes. It performs no I/O: main has no HTTP
 * route for creator commands yet, so submission is delegated to the host via
 * the editor's `onSubmitCommands` callback.
 */
import { canonicalStringify, type JsonValue } from './canonicalJson';
import { designGraphDigest } from './designGraph';
import type { EditSession, VisualEditOp } from './graphEdits';
import { opTarget } from './graphEdits';
import { sha256Hex } from './sha256';

export const COMMAND_SCHEMA = 'creator.command.v1';
export const COMMAND_VERSION = 1;
export const VISUAL_PATCH_SCHEMA = 'creator.visual_edit.v1';
export const MAX_COMMAND_BYTES = 512 * 1024;
export const MAX_LIST_ITEMS = 256;

const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,159}$/;
const PROJECT_RE = /^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$/;

export class CreatorCommandError extends Error {
  readonly code = 'CRE.COMMAND';
  readonly reason: string;
  constructor(message: string, reason: string) {
    super(message);
    this.name = 'CreatorCommandError';
    this.reason = reason;
  }
}

export interface CreatorEditCommand {
  readonly schema: typeof COMMAND_SCHEMA;
  readonly schema_version: typeof COMMAND_VERSION;
  readonly operation: 'edit';
  readonly project_id: string;
  readonly payload: {
    readonly target_id: string;
    readonly expected_revision: number;
    readonly patch: { [key: string]: JsonValue };
  };
  readonly digest: string;
}

function opJson(op: VisualEditOp): JsonValue {
  return { ...op } as unknown as JsonValue;
}

export function buildEditCommand(args: {
  projectId: string;
  targetId: string;
  expectedRevision: number;
  patch: { [key: string]: JsonValue };
}): CreatorEditCommand {
  if (!PROJECT_RE.test(args.projectId)) throw new CreatorCommandError('project_id is not a canonical identifier', 'project_id');
  if (!ID_RE.test(args.targetId)) throw new CreatorCommandError('target_id is not a canonical identifier', 'field_type');
  if (!Number.isSafeInteger(args.expectedRevision) || args.expectedRevision < 0) {
    throw new CreatorCommandError('expected_revision must be a non-negative integer', 'field_type');
  }
  const body: { [key: string]: JsonValue } = {
    schema: COMMAND_SCHEMA,
    schema_version: COMMAND_VERSION,
    operation: 'edit',
    project_id: args.projectId,
    payload: { target_id: args.targetId, expected_revision: args.expectedRevision, patch: args.patch },
  };
  const encoded = canonicalStringify(body);
  if (encoded.length > MAX_COMMAND_BYTES) throw new CreatorCommandError('creator command exceeds serialized byte bound', 'bound');
  return Object.freeze({
    schema: COMMAND_SCHEMA,
    schema_version: COMMAND_VERSION,
    operation: 'edit',
    project_id: args.projectId,
    payload: Object.freeze({ target_id: args.targetId, expected_revision: args.expectedRevision, patch: args.patch }),
    digest: sha256Hex(encoded),
  });
}

/** Group the session's op log by target entity, preserving op order per target. */
export function commandsForSession(session: EditSession): CreatorEditCommand[] {
  const groups = new Map<string, VisualEditOp[]>();
  for (const op of session.ops) {
    const target = opTarget(op);
    const list = groups.get(target) ?? [];
    list.push(op);
    groups.set(target, list);
  }
  const baseDigest = designGraphDigest(session.base);
  const targetDigest = designGraphDigest(session.working);
  const out: CreatorEditCommand[] = [];
  for (const [targetId, ops] of groups) {
    if (ops.length > MAX_LIST_ITEMS) throw new CreatorCommandError('too many ops for one target', 'bound');
    out.push(
      buildEditCommand({
        projectId: session.base.projectId,
        targetId,
        expectedRevision: session.base.revision,
        patch: {
          schema: VISUAL_PATCH_SCHEMA,
          base_digest: baseDigest,
          target_digest: targetDigest,
          ops: ops.map(opJson),
        },
      }),
    );
  }
  return out;
}

/** Same bytes as `serialize_creator_command`. */
export function serializeEditCommand(command: CreatorEditCommand): string {
  return canonicalStringify({
    schema: command.schema,
    schema_version: command.schema_version,
    operation: command.operation,
    project_id: command.project_id,
    payload: command.payload as unknown as JsonValue,
    digest: command.digest,
  });
}
