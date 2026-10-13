/**
 * Pure cockpit snapshot / history helpers for CockpitPanel.
 * Formats SNAPSHOT fields and diffSnapshots changes in operator language.
 */
import type { Catalog, SnapshotChange, VerbSpec } from './commands';
import { BASE_CATALOG, describeResult, diffSnapshots, mergeCatalog, parseCommand } from './commands';
import type { CockpitSnapshot, CommandEnvelope, TensorAxis } from './types';
import { TENSOR_AXES } from './types';

export interface SnapshotSummary {
  era: string;
  fingerprint: string;
  dominant: string;
  blend: string;
  generation: string;
  archetype: string;
  oracle: string;
  helix: string;
  ledger: string;
  composition: string;
  historyCount: number;
  axesPreview: string;
}

export interface HistoryEntry {
  id: number;
  command: string;
  ok: boolean;
  /** One-line operator summary (describeResult or error). */
  summary: string;
  /** Human labels for snapshot deltas. */
  changes: string[];
  at: number;
}

const FIELD_LABELS: Record<string, string> = {
  era: 'era',
  blend: 'blend',
  generation: 'generation',
  archetype: 'archetype',
  oracle: 'oracle',
  composition: 'composition',
  'helix.σ': 'helix σ',
  'ledger.height': 'ledger height',
  'ledger.valid': 'ledger valid',
};

function num(n: unknown, digits = 2): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

function rec(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

/** True when value looks like a full Cockpit.snapshot() payload. */
export function isCockpitSnapshot(value: unknown): value is CockpitSnapshot {
  const r = rec(value);
  if (!r) return false;
  const tensor = rec(r.tensor);
  const ledger = rec(r.ledger);
  return !!(tensor && ledger && typeof tensor.era === 'string');
}

/**
 * Pull a snapshot out of a cockpit API body.
 * Bodies are usually `{ ok, verb, result }` where SNAPSHOT/STATUS put the
 * snapshot in `result`; tolerate a bare snapshot too.
 */
export function extractSnapshot(data: unknown): CockpitSnapshot | null {
  if (isCockpitSnapshot(data)) return data as CockpitSnapshot;
  const r = rec(data);
  if (!r) return null;
  if (isCockpitSnapshot(r.result)) return r.result as CockpitSnapshot;
  return null;
}

/** Coerce API success body into a CommandEnvelope when possible. */
export function asCommandEnvelope(data: unknown, fallbackVerb = ''): CommandEnvelope | null {
  const r = rec(data);
  if (!r) return null;
  if (typeof r.ok === 'boolean' && typeof r.verb === 'string') {
    return { ok: !!r.ok, verb: String(r.verb), result: r.result };
  }
  if (isCockpitSnapshot(data)) {
    return { ok: true, verb: fallbackVerb || 'SNAPSHOT', result: data };
  }
  return null;
}

export function formatDominant(
  dominant: CockpitSnapshot['tensor']['dominant'] | null | undefined,
  max = 3,
): string {
  if (!Array.isArray(dominant) || !dominant.length) return '—';
  return dominant
    .slice(0, max)
    .map((d) => `${d.axis}=${num(d.value, 2)}`)
    .join(' · ');
}

export function formatBlend(blend: CockpitSnapshot['blend'] | null | undefined): string {
  if (!blend || !Array.isArray(blend) || blend.length < 2) return '—';
  const t = blend.length >= 3 ? num(blend[2], 2) : '—';
  return `${blend[0]} → ${blend[1]} @ ${t}`;
}

export function formatOracle(oracle: CockpitSnapshot['oracle'] | null | undefined): string {
  if (!oracle) return '—';
  const text = oracle.text ? String(oracle.text) : '';
  const idx = oracle.index != null ? `#${oracle.index}` : '#?';
  return text ? `${idx}: ${text}` : idx;
}

export function formatHelix(helix: CockpitSnapshot['helix'] | null | undefined): string {
  if (!helix) return '—';
  return `σ=${num(helix.supercoiling, 3)} · nicked=${helix.nicked ?? '—'} · Lk=${num(helix.linking_number, 2)}`;
}

export function formatLedger(ledger: CockpitSnapshot['ledger'] | null | undefined): string {
  if (!ledger) return '—';
  const valid = ledger.valid === false ? 'INVALID' : 'ok';
  return `h=${ledger.height ?? 0} · ${valid}`;
}

export function formatAxesPreview(axes: Record<string, number> | null | undefined, max = 4): string {
  if (!axes) return '—';
  const ranked = (TENSOR_AXES as readonly TensorAxis[])
    .map((axis) => ({ axis, value: axes[axis] }))
    .filter((x) => typeof x.value === 'number' && Number.isFinite(x.value))
    .sort((a, b) => (b.value as number) - (a.value as number))
    .slice(0, max);
  if (!ranked.length) return '—';
  return ranked.map((x) => `${x.axis}=${num(x.value, 2)}`).join(' · ');
}

/** Flatten a live snapshot into CockpitPanel readout fields. */
export function summarizeSnapshot(snap: CockpitSnapshot | null | undefined): SnapshotSummary | null {
  if (!snap?.tensor) return null;
  const compositionId = snap.composition?.blueprint_id;
  return {
    era: snap.tensor.era || '—',
    fingerprint: snap.tensor.fingerprint || '—',
    dominant: formatDominant(snap.tensor.dominant),
    blend: formatBlend(snap.blend),
    generation: snap.generation || '—',
    archetype: snap.archetype || '—',
    oracle: formatOracle(snap.oracle),
    helix: formatHelix(snap.helix),
    ledger: formatLedger(snap.ledger),
    composition: compositionId ? String(compositionId) : '—',
    historyCount: Array.isArray(snap.history) ? snap.history.length : 0,
    axesPreview: formatAxesPreview(snap.tensor.axes),
  };
}

/** Operator label for one SnapshotChange field. */
export function changeFieldLabel(field: string): string {
  if (FIELD_LABELS[field]) return FIELD_LABELS[field];
  if (field.startsWith('axis.')) return field.slice(5);
  return field;
}

/** One-line human text for a snapshot delta. */
export function formatSnapshotChange(change: SnapshotChange): string {
  const label = changeFieldLabel(change.field);
  if (change.delta !== 0 && change.field.startsWith('axis.')) {
    const sign = change.delta > 0 ? '+' : '';
    return `${label} ${change.before} → ${change.after} (${sign}${num(change.delta, 3)})`;
  }
  if (change.delta !== 0 && change.field === 'helix.σ') {
    const sign = change.delta > 0 ? '+' : '';
    return `${label} ${change.before} → ${change.after} (${sign}${num(change.delta, 3)})`;
  }
  if (change.delta !== 0 && change.field === 'ledger.height') {
    const sign = change.delta > 0 ? '+' : '';
    return `${label} ${change.before} → ${change.after} (${sign}${change.delta})`;
  }
  return `${label} ${change.before} → ${change.after}`;
}

export function formatSnapshotChanges(changes: SnapshotChange[], max = 8): string[] {
  return changes.slice(0, max).map(formatSnapshotChange);
}

export function historyA11yLabel(entry: HistoryEntry): string {
  const status = entry.ok ? 'ok' : 'failed';
  const delta = entry.changes.length
    ? `, ${entry.changes.length} change${entry.changes.length === 1 ? '' : 's'}`
    : '';
  return `${entry.command}: ${status}, ${entry.summary}${delta}`;
}

/**
 * Build the operator summary line for a successful command history row.
 * Prefers describeResult; falls back to verb ok.
 */
export function explainCommandResult(
  envelope: CommandEnvelope | null,
  spec: VerbSpec | null,
  command: string,
): string {
  if (envelope) return describeResult(envelope, spec);
  const verb = command.trim().split(/\s+/)[0]?.toUpperCase() || 'command';
  return `${verb} ok`;
}

/** Diff helper re-export for panels/tests that only import this module. */
export function snapshotDiff(
  before: CockpitSnapshot | null,
  after: CockpitSnapshot | null,
): SnapshotChange[] {
  return diffSnapshots(before, after);
}

function catalogFromEras(eras?: string[]): Catalog {
  if (!eras?.length) return BASE_CATALOG;
  return mergeCatalog(BASE_CATALOG, { eras });
}

/** Local validation message for the command line (first error diagnostic). */
export function validationMessage(line: string, eras?: string[]): string | null {
  const parsed = parseCommand(line, catalogFromEras(eras));
  if (parsed.sendable) return null;
  const err = parsed.diagnostics.find((d) => d.severity === 'error');
  if (!err) return 'Command is not sendable.';
  const tip = err.suggestions?.length ? ` (try ${err.suggestions.join(', ')})` : '';
  return `${err.message}${tip}`;
}

export const COCKPIT_QUICK_COMMANDS: readonly { label: string; command: string; hint: string }[] = [
  { label: 'Snapshot', command: 'SNAPSHOT', hint: 'Refresh the live cockpit snapshot' },
  { label: 'Status', command: 'STATUS', hint: 'Alias of SNAPSHOT' },
  { label: 'Roll oracle', command: 'ROLL ORACLE', hint: 'Draw an oracle reading' },
  { label: 'Bind era', command: 'BIND ERA ', hint: 'Pin a design era' },
  { label: 'Auto archetype', command: 'BIND ARCHETYPE auto', hint: 'Compose from vision' },
];
