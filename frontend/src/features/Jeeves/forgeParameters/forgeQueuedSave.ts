/** Session-only Forge save snapshots. The server owns admission and completion. */
import type { ForgeDocument, ForgeStep } from '../../../product/gameFrontierAuthoringClient';

export type QueuedForgeStep = ForgeStep & { localId: string };
export type ForgeSaveScope = {
  projectId: string;
  accountEpoch: number;
  accountToken: string;
  viewEpoch: number;
};
export type ForgeSaveSnapshot = {
  readonly scope: Readonly<ForgeSaveScope>;
  readonly projectId: string;
  readonly document: ForgeDocument;
  readonly steps: readonly ForgeStep[];
  readonly stepIds: readonly string[];
  readonly requestId: string;
};
export type ForgePendingSave = {
  readonly snapshot: ForgeSaveSnapshot;
  readonly uncertain: boolean;
};

const SHA = /^[a-f0-9]{64}$/;
const MAX_STEPS = 64;
const MAX_PARAMETERS = 32;
const MAX_PARAMETER_BYTES = 128000;
// These are the existing guided-parameter inspection limits, per value tree.
const MAX_DEPTH = 64;
const MAX_NODES = 20000;

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Expected a plain JSON object.');
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) throw new Error('Use a plain JSON object without executable properties.');
  return value as Record<string, unknown>;
}

function own(value: Record<string, unknown>, key: string): unknown {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (!descriptor || !('value' in descriptor) || !descriptor.enumerable) throw new Error('Required save fields must be ordinary JSON data.');
  return descriptor.value;
}

function closed(value: Record<string, unknown>, allowed: readonly string[]): void {
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== 'string' || !allowed.includes(key)) throw new Error('Unexpected save field.');
    own(value, key);
  }
}

/** Validate every array descriptor before accessing any element's data. */
function arrayData(value: unknown, maximum: number, minimum = 0): unknown[] {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) throw new Error('Use ordinary JSON arrays.');
  const length = Object.getOwnPropertyDescriptor(value, 'length')?.value;
  if (!Number.isSafeInteger(length) || length < minimum || length > maximum) throw new Error('The array exceeds the existing editor limits.');
  const descriptors = new Map<number, PropertyDescriptor>();
  for (const key of Reflect.ownKeys(value)) {
    if (key === 'length') continue;
    if (typeof key !== 'string' || !/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= length) {
      throw new Error('JSON arrays cannot contain named or symbol properties.');
    }
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !('value' in descriptor) || !descriptor.enumerable) throw new Error('JSON arrays require explicit ordinary entries.');
    descriptors.set(Number(key), descriptor);
  }
  if (descriptors.size !== length) throw new Error('JSON arrays require explicit ordinary entries.');
  const values: unknown[] = [];
  for (let index = 0; index < length; index += 1) values.push(descriptors.get(index)!.value);
  return values;
}

/** Copy data descriptors, never invoking toJSON, getters or coercion hooks. */
function copyData(value: unknown): unknown {
  const seen = new Set<object>();
  let nodes = 0;
  const visit = (current: unknown, depth: number): unknown => {
    if (++nodes > MAX_NODES || depth > MAX_DEPTH) throw new Error('The save value exceeds existing editor inspection limits.');
    if (current === null || typeof current === 'string' || typeof current === 'boolean') return current;
    if (typeof current === 'number') {
      if (!Number.isFinite(current)) throw new Error('Save values must contain finite JSON numbers.');
      return current;
    }
    if (!current || typeof current !== 'object') throw new Error('Save values must contain JSON data only.');
    if (seen.has(current)) throw new Error('Save values cannot contain cycles.');
    seen.add(current);
    let result: unknown;
    if (Array.isArray(current)) {
      result = arrayData(current, MAX_NODES).map(item => visit(item, depth + 1));
    } else {
      const object = record(current);
      const output: Record<string, unknown> = {};
      for (const key of Reflect.ownKeys(object)) {
        if (typeof key !== 'string') throw new Error('JSON objects cannot contain symbol properties.');
        Object.defineProperty(output, key, { value: visit(own(object, key), depth + 1),
          enumerable: true, configurable: true, writable: true });
      }
      result = output;
    }
    seen.delete(current);
    return result;
  };
  return visit(value, 0);
}

function freezeData<T>(value: T): T {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freezeData(child);
    Object.freeze(value);
  }
  return value;
}

function text(value: unknown, maximum: number): string {
  if (typeof value !== 'string' || !value || value !== value.trim() || value.length > maximum) throw new Error('Save identities must be nonempty normalized strings.');
  return value;
}

function bytes(value: unknown): number {
  const quoted = (text: string): number => {
    let size = 0;
    // Stringifying a primitive string cannot invoke an object's toJSON hook.
    // Lone surrogates become ASCII escapes, matching JSON transport size.
    for (const part of JSON.stringify(text)) {
      const code = part.codePointAt(0)!;
      size += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
      if (size > MAX_PARAMETER_BYTES) break;
    }
    return size;
  };
  const count = (current: unknown): number => {
    if (current === null) return 4;
    if (typeof current === 'string') return quoted(current);
    if (typeof current === 'boolean') return current ? 4 : 5;
    if (typeof current === 'number') return String(current).length;
    const entries = Array.isArray(current) ? current : Object.keys(current as object);
    let size = 2;
    for (let index = 0; index < entries.length; index += 1) {
      size += index ? 1 : 0;
      size += Array.isArray(current) ? count(entries[index])
        : quoted(entries[index] as string) + 1 + count((current as Record<string, unknown>)[entries[index] as string]);
      if (size > MAX_PARAMETER_BYTES) break;
    }
    return size;
  };
  return count(value);
}

function wireStep(value: unknown, queued: boolean): ForgeStep {
  const source = record(value);
  closed(source, queued ? ['action', 'parameters', 'localId'] : ['action', 'parameters']);
  const action = text(own(source, 'action'), 384);
  const parameters = copyData(own(source, 'parameters')) as Record<string, unknown>;
  record(parameters);
  if (Object.keys(parameters).length > MAX_PARAMETERS || bytes(parameters) > MAX_PARAMETER_BYTES) {
    throw new Error('Action parameters exceed the existing 32 fields or 128,000 JSON bytes.');
  }
  return { action, parameters };
}

function queueIds(queue: readonly QueuedForgeStep[], requireNonempty = false): string[] {
  if (!Array.isArray(queue) || queue.length > MAX_STEPS || requireNonempty && queue.length === 0) throw new Error('A save requires between 1 and 64 queued actions.');
  const ids = arrayData(queue, MAX_STEPS).map(step => text(own(record(step), 'localId'), 128));
  if (new Set(ids).size !== ids.length) throw new Error('Queued action identities must be unique.');
  return ids;
}

function scopeValue(value: ForgeSaveScope): ForgeSaveScope {
  const source = record(value);
  closed(source, ['projectId', 'accountEpoch', 'accountToken', 'viewEpoch']);
  const projectId = text(own(source, 'projectId'), 128);
  const accountEpoch = own(source, 'accountEpoch');
  const viewEpoch = own(source, 'viewEpoch');
  const accountToken = own(source, 'accountToken');
  if (typeof accountToken !== 'string' || !Number.isSafeInteger(accountEpoch) || Number(accountEpoch) < 0
      || !Number.isSafeInteger(viewEpoch) || Number(viewEpoch) < 0) throw new Error('The current editor scope is invalid.');
  return { projectId, accountEpoch: Number(accountEpoch), accountToken, viewEpoch: Number(viewEpoch) };
}

export function queueForgeStep(localId: string, step: ForgeStep): QueuedForgeStep {
  return freezeData({ ...wireStep(step, false), localId: text(localId, 128) });
}

/** Local IDs are deliberately absent from the existing closed server request. */
export function forgeQueueWireSteps(queue: readonly QueuedForgeStep[]): ForgeStep[] {
  queueIds(queue);
  return arrayData(queue, MAX_STEPS).map(step => wireStep(step, true));
}

function documentValue(projectId: string, document: ForgeDocument): ForgeDocument {
  const identity = text(projectId, 128);
  const original = copyData(document) as ForgeDocument;
  record(original);
  if (original.schema !== 'skeleton.game.frontier_studio_document.v1' || original.project_id !== identity
      || !Number.isSafeInteger(original.expected_version) || original.expected_version < 1 || !SHA.test(original.source_sha256)) {
    throw new Error('The save does not match the current project source.');
  }
  return original;
}

/** Closed data-only boundary for callers that do not use the session queue. */
export function cloneForgeEditInput(projectId: string, document: ForgeDocument,
                                    steps: readonly ForgeStep[]): { document: ForgeDocument; steps: ForgeStep[] } {
  const entries = arrayData(steps, MAX_STEPS, 1);
  const original = documentValue(projectId, document);
  return freezeData({ document: original, steps: entries.map(step => wireStep(step, false)) });
}

export function beginForgeSave(scope: ForgeSaveScope, document: ForgeDocument,
                               queue: readonly QueuedForgeStep[], requestId: string): ForgePendingSave {
  const identity = scopeValue(scope);
  const original = documentValue(identity.projectId, document);
  const stepIds = queueIds(queue, true);
  const snapshot = freezeData({ scope: identity, projectId: identity.projectId, document: original,
    steps: forgeQueueWireSteps(queue), stepIds, requestId: text(requestId, 512) });
  return Object.freeze({ snapshot, uncertain: false });
}

/** A proven pre-dispatch rejection can release only a never-uncertain attempt. */
export function failForgeSave(pending: ForgePendingSave, provenPreDispatch: boolean): ForgePendingSave | null {
  if (typeof pending?.uncertain !== 'boolean' || typeof provenPreDispatch !== 'boolean') throw new Error('Invalid save recovery state.');
  if (!pending.uncertain && provenPreDispatch) return null;
  return Object.freeze({ snapshot: pending.snapshot, uncertain: true });
}

export function forgeSaveScopeMatches(snapshot: ForgeSaveSnapshot, current: ForgeSaveScope): boolean {
  const identity = scopeValue(current);
  return snapshot.scope.projectId === identity.projectId && snapshot.scope.accountEpoch === identity.accountEpoch
    && snapshot.scope.accountToken === identity.accountToken && snapshot.scope.viewEpoch === identity.viewEpoch;
}

function sameData(first: unknown, second: unknown): boolean {
  if (first === second) return true;
  if (!first || !second || typeof first !== 'object' || typeof second !== 'object') return false;
  if (Array.isArray(first) || Array.isArray(second)) return Array.isArray(first) && Array.isArray(second)
    && first.length === second.length && first.every((value, index) => sameData(value, second[index]));
  const a = first as Record<string, unknown>, b = second as Record<string, unknown>;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.prototype.hasOwnProperty.call(b, key) && sameData(a[key], b[key]));
}

export function confirmForgeSave(pending: ForgePendingSave, queue: readonly QueuedForgeStep[],
                                 current: ForgeSaveScope): QueuedForgeStep[] {
  if (!forgeSaveScopeMatches(pending.snapshot, current)) throw new Error('The account or project changed. This save cannot clear the current draft.');
  const ids = queueIds(queue);
  const wire = forgeQueueWireSteps(queue);
  const originals = new Map(pending.snapshot.stepIds.map((id, index) => [id, pending.snapshot.steps[index]]));
  for (let index = 0; index < ids.length; index += 1) {
    const original = originals.get(ids[index]);
    if (original && !sameData(original, wire[index])) throw new Error('A queued action identity changed. Its newer draft was retained.');
  }
  return queue.filter(step => !originals.has(step.localId));
}
