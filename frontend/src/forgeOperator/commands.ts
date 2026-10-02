/**
 * Cockpit command grammar — client mirror of skeleton/context/cockpit.py.
 *
 * The engine's `Cockpit.apply()` is the only mutation path for operator
 * context (era tensor, blend, oracle, helix, generation, archetype pin,
 * composition preview, cortex). This module lets the console:
 *   • tokenise exactly like Python's `shlex.split` (POSIX quoting),
 *   • validate a line against the verb table *and* live catalogues (eras,
 *     generations, archetypes) before it reaches the server,
 *   • offer context-aware completions,
 *   • build shlex-safe command strings from structured controls, and
 *   • explain a result / snapshot delta in operator language.
 *
 * The server stays authoritative: anything we cannot judge locally is sent,
 * and CockpitError responses (with `context.known`) feed back into the
 * catalogue so the next validation is sharper.
 */
import type { CockpitSnapshot, CommandEnvelope } from './types';
import { TENSOR_AXES } from './types';

// ── Tokeniser ──────────────────────────────────────────────────────────

export interface TokenizeResult {
  tokens: string[];
  /** Set when quoting is unbalanced — shlex raises "No closing quotation". */
  error: string | null;
  /** True if the line ends in whitespace (completion targets a new token). */
  trailingSpace: boolean;
}

/** POSIX shlex.split: whitespace-separated, '…' literal, "…" with \\ escapes. */
export function tokenize(line: string): TokenizeResult {
  const tokens: string[] = [];
  let current = '';
  let inToken = false;
  let quote: '"' | "'" | null = null;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (quote === "'") {
      if (ch === "'") quote = null;
      else current += ch;
      continue;
    }
    if (quote === '"') {
      if (ch === '"') quote = null;
      else if (ch === '\\' && i + 1 < line.length && (line[i + 1] === '"' || line[i + 1] === '\\' || line[i + 1] === '$' || line[i + 1] === '`')) {
        current += line[i + 1];
        i += 1;
      } else current += ch;
      continue;
    }
    if (ch === '\\') {
      if (i + 1 < line.length) {
        current += line[i + 1];
        i += 1;
        inToken = true;
      } else {
        return { tokens, error: 'No escaped character', trailingSpace: false };
      }
      continue;
    }
    if (ch === "'" || ch === '"') {
      quote = ch;
      inToken = true;
      continue;
    }
    if (/\s/.test(ch)) {
      if (inToken) {
        tokens.push(current);
        current = '';
        inToken = false;
      }
      continue;
    }
    current += ch;
    inToken = true;
  }
  if (quote) return { tokens, error: 'No closing quotation', trailingSpace: false };
  if (inToken) tokens.push(current);
  return { tokens, error: null, trailingSpace: /\s$/.test(line) };
}

/** Quote one argument so `tokenize` (and shlex) read it back verbatim. */
export function quoteArg(value: string): string {
  if (value === '') return "''";
  if (/^[A-Za-z0-9_@%+=:,./~-]+$/.test(value)) return value;
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

// ── Verb table ─────────────────────────────────────────────────────────

export type ArgKind =
  | 'era'
  | 'axis'
  | 'unit'
  | 'int'
  | 'slot'
  | 'backend'
  | 'generation'
  | 'archetype'
  | 'text';

export interface ArgSpec {
  name: string;
  kind: ArgKind;
  optional?: boolean;
  /** Consumes the remainder of the line (free text). */
  rest?: boolean;
  /** Value the server substitutes when omitted. */
  defaultValue?: string;
}

export type VerbGroup = 'era' | 'forge' | 'oracle' | 'cortex' | 'inspect';

/** Parts of the snapshot a verb can change — used to refresh and to explain. */
export type Effect = 'tensor' | 'blend' | 'oracle' | 'helix' | 'generation' | 'archetype' | 'composition' | 'cortex';

export interface VerbSpec {
  id: string;
  verb: string;
  /** Required second keyword (BIND ERA, EXPORT TRACT); matched case-insensitively. */
  sub?: string[];
  /** Optional second keyword the server tolerates (BLEND [ERA], ROLL [ORACLE]). */
  optionalSub?: string;
  args: ArgSpec[];
  summary: string;
  group: VerbGroup;
  effects: Effect[];
  /** Mutates engine-wide state that other operators will see. */
  shared: boolean;
}

export const SLOTS = ['pfc', 'midbrain', 'left', 'right'] as const;
export const BACKENDS = ['local', 'echo'] as const;

export const VERBS: VerbSpec[] = [
  { id: 'snapshot', verb: 'SNAPSHOT', args: [], summary: 'Return the full cockpit snapshot', group: 'inspect', effects: [], shared: false },
  { id: 'status', verb: 'STATUS', args: [], summary: 'Alias of SNAPSHOT', group: 'inspect', effects: [], shared: false },
  { id: 'bind-era', verb: 'BIND', sub: ['ERA'], args: [{ name: 'era', kind: 'era', optional: true, defaultValue: 'extraction_now' }], summary: 'Load an era dialect into the tensor (clears any blend)', group: 'era', effects: ['tensor', 'blend'], shared: true },
  { id: 'bind-generation', verb: 'BIND', sub: ['GENERATION', 'GEN'], args: [{ name: 'generation', kind: 'generation', optional: true, defaultValue: 'modern' }], summary: 'Pin the hardware generation the forge targets', group: 'forge', effects: ['generation'], shared: true },
  { id: 'bind-archetype', verb: 'BIND', sub: ['ARCHETYPE'], args: [{ name: 'archetype', kind: 'archetype' }], summary: 'Pin the forge archetype (auto/vision = compose from the vision)', group: 'forge', effects: ['archetype'], shared: true },
  { id: 'bind-slot', verb: 'BIND', sub: ['SLOT', 'MODEL'], args: [{ name: 'slot', kind: 'slot' }, { name: 'backend', kind: 'backend', optional: true, defaultValue: 'local' }], summary: 'Bind a cortex slot to a local or echo backend', group: 'cortex', effects: ['cortex'], shared: true },
  { id: 'compose', verb: 'COMPOSE', args: [{ name: 'vision', kind: 'text', rest: true }], summary: 'Preview the blueprint a vision composes into', group: 'forge', effects: ['composition'], shared: true },
  { id: 'set-axis', verb: 'SET', sub: ['AXIS'], args: [{ name: 'axis', kind: 'axis' }, { name: 'value', kind: 'unit' }], summary: 'Set one tensor axis (clamped to 0..1)', group: 'era', effects: ['tensor'], shared: true },
  { id: 'lerp-era', verb: 'LERP', sub: ['ERA'], args: [{ name: 'era', kind: 'era' }, { name: 't', kind: 'unit' }], summary: 'Move the current tensor toward an era by t', group: 'era', effects: ['tensor'], shared: true },
  { id: 'blend-era', verb: 'BLEND', optionalSub: 'ERA', args: [{ name: 'a', kind: 'era' }, { name: 'b', kind: 'era' }, { name: 't', kind: 'unit', optional: true, defaultValue: '0.5' }], summary: 'Blend two eras at t (0 = a, 1 = b)', group: 'era', effects: ['tensor', 'blend'], shared: true },
  { id: 'detect', verb: 'DETECT', args: [{ name: 'text', kind: 'text', rest: true, optional: true }], summary: 'Detect the era from text and bind it', group: 'era', effects: ['tensor', 'blend'], shared: true },
  { id: 'roll', verb: 'ROLL', optionalSub: 'ORACLE', args: [], summary: 'Roll the Magic-8 oracle over the lattice', group: 'oracle', effects: ['oracle'], shared: true },
  { id: 'nick', verb: 'NICK', optionalSub: 'HELIX', args: [], summary: 'Nick the context helix (relax supercoiling)', group: 'oracle', effects: ['helix'], shared: true },
  { id: 'ligate', verb: 'LIGATE', optionalSub: 'HELIX', args: [], summary: 'Ligate the helix (restore topology)', group: 'oracle', effects: ['helix'], shared: true },
  { id: 'think', verb: 'THINK', args: [{ name: 'text', kind: 'text', rest: true, optional: true }], summary: 'Run the cortex on a stimulus in the current era', group: 'cortex', effects: ['cortex'], shared: false },
  { id: 'acquire', verb: 'ACQUIRE', args: [{ name: 'slot', kind: 'slot' }], summary: 'Acquire a slot into the own-system', group: 'cortex', effects: ['cortex'], shared: true },
  { id: 'surpass', verb: 'SURPASS', args: [{ name: 'slot', kind: 'slot' }], summary: 'Let the own-system surpass a slot', group: 'cortex', effects: ['cortex'], shared: true },
  { id: 'train', verb: 'TRAIN', args: [{ name: 'epochs', kind: 'int', optional: true, defaultValue: '1' }], summary: 'Train the cortex for N epochs', group: 'cortex', effects: ['cortex'], shared: true },
  { id: 'recall', verb: 'RECALL', args: [{ name: 'text', kind: 'text', rest: true, optional: true }], summary: 'Recall from cortex memory', group: 'cortex', effects: [], shared: false },
  { id: 'export-tract', verb: 'EXPORT', sub: ['TRACT'], args: [{ name: 'slot', kind: 'slot' }], summary: 'Export a slot tract', group: 'cortex', effects: [], shared: false },
  { id: 'import-tract', verb: 'IMPORT', sub: ['TRACT'], args: [{ name: 'slot', kind: 'slot' }], summary: 'Re-import a tract this cortex holds', group: 'cortex', effects: ['cortex'], shared: true },
  { id: 'own', verb: 'OWN', args: [], summary: 'Inspect the own-system', group: 'cortex', effects: [], shared: false },
  { id: 'shadow', verb: 'SHADOW', args: [], summary: 'Inspect shadow scores and surpassed slots', group: 'cortex', effects: [], shared: false },
];

const VERB_NAMES = Array.from(new Set(VERBS.map((v) => v.verb)));

export function verbById(id: string): VerbSpec | undefined {
  return VERBS.find((v) => v.id === id);
}

/** Resolve the spec the server would dispatch to for these tokens. */
export function resolveVerb(tokens: string[]): { spec: VerbSpec | null; argStart: number } {
  if (!tokens.length) return { spec: null, argStart: 0 };
  const verb = tokens[0].toUpperCase();
  const second = (tokens[1] || '').toUpperCase();
  const candidates = VERBS.filter((v) => v.verb === verb);
  if (!candidates.length) return { spec: null, argStart: 1 };
  const withSub = candidates.find((v) => v.sub && v.sub.includes(second));
  if (withSub) return { spec: withSub, argStart: 2 };
  const plain = candidates.find((v) => !v.sub);
  if (plain) {
    const skip = plain.optionalSub && second === plain.optionalSub ? 2 : 1;
    return { spec: plain, argStart: skip };
  }
  return { spec: null, argStart: 1 };
}

// ── Validation ─────────────────────────────────────────────────────────

export interface Catalog {
  eras: string[];
  generations: string[];
  archetypes: string[];
}

/** Values that are valid even before catalogues load (from the engine source). */
export const BASE_CATALOG: Catalog = {
  eras: ['extraction_now', 'soulslike', 'boomer_shooter', 'arcade_golden_age'],
  generations: ['8bit', '16bit', 'early3d', '64bit', 'earlyhd', 'modern', 'nextgen'],
  archetypes: ['auto', 'combat_loop', 'extraction', 'pipeline', 'vision'],
};

export function mergeCatalog(base: Catalog, extra: Partial<Catalog>): Catalog {
  const merge = (a: string[], b?: string[]) => Array.from(new Set([...a, ...(b || [])]));
  return {
    eras: merge(base.eras, extra.eras),
    generations: merge(base.generations, extra.generations),
    archetypes: merge(base.archetypes, extra.archetypes),
  };
}

export type Severity = 'error' | 'warning' | 'info';

export interface Diagnostic {
  severity: Severity;
  message: string;
  /** Index into tokens, or -1 for the whole line. */
  token: number;
  /** Replacement candidates for the offending token. */
  suggestions?: string[];
}

export interface ParsedCommand {
  line: string;
  tokens: string[];
  spec: VerbSpec | null;
  args: Record<string, string>;
  diagnostics: Diagnostic[];
  /** False when any diagnostic is an error. */
  sendable: boolean;
  /** Canonical, upper-cased verb form the ledger will record. */
  canonical: string;
}

function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (!m) return n;
  if (!n) return m;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i += 1) {
    const cur = [i];
    for (let j = 1; j <= n; j += 1) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[n];
}

/** Closest candidates by prefix, then edit distance (≤ 1/3 of the length). */
export function closest(value: string, candidates: readonly string[], limit = 3): string[] {
  const v = value.toLowerCase();
  const prefixed = candidates.filter((c) => c.toLowerCase().startsWith(v));
  if (prefixed.length && v) return prefixed.slice(0, limit);
  const budget = Math.max(1, Math.floor(v.length / 3));
  return candidates
    .map((c) => ({ c, d: levenshtein(v, c.toLowerCase()) }))
    .filter((x) => x.d <= budget)
    .sort((x, y) => x.d - y.d || x.c.localeCompare(y.c))
    .slice(0, limit)
    .map((x) => x.c);
}

function checkValue(kind: ArgKind, raw: string, catalog: Catalog): Diagnostic | null {
  const lower = raw.toLowerCase();
  const inList = (list: readonly string[], label: string, severity: Severity = 'error'): Diagnostic | null =>
    list.includes(raw) || list.includes(lower)
      ? null
      : { severity, message: `unknown ${label} "${raw}"`, token: -1, suggestions: closest(raw, list) };
  switch (kind) {
    case 'era':
      // Blended ids (a~b@t) are accepted by LERP targets only via names; the
      // catalogue may lag the server, so unknown eras warn instead of block.
      return inList(catalog.eras, 'era', catalog.eras.length > BASE_CATALOG.eras.length ? 'error' : 'warning');
    case 'generation':
      return inList(catalog.generations, 'generation');
    case 'archetype':
      return inList(catalog.archetypes, 'archetype');
    case 'axis':
      return (TENSOR_AXES as readonly string[]).includes(raw)
        ? null
        : { severity: 'error', message: `unknown axis "${raw}"`, token: -1, suggestions: closest(raw, TENSOR_AXES) };
    case 'slot':
      return (SLOTS as readonly string[]).includes(raw)
        ? null
        : { severity: 'warning', message: `"${raw}" is not a canonical slot (${SLOTS.join(', ')})`, token: -1, suggestions: closest(raw, SLOTS) };
    case 'backend':
      return (BACKENDS as readonly string[]).includes(lower)
        ? null
        : { severity: 'warning', message: `backend "${raw}" is treated as local`, token: -1, suggestions: [...BACKENDS] };
    case 'unit': {
      const n = Number(raw);
      if (raw.trim() === '' || !Number.isFinite(n)) return { severity: 'error', message: `"${raw}" is not a number`, token: -1 };
      if (n < 0 || n > 1) return { severity: 'warning', message: `${raw} will be clamped to ${n < 0 ? 0 : 1}`, token: -1 };
      return null;
    }
    case 'int': {
      if (!/^-?\d+$/.test(raw)) return { severity: 'error', message: `"${raw}" is not an integer`, token: -1 };
      if (Number(raw) < 1) return { severity: 'warning', message: 'epochs below 1 do no training', token: -1 };
      return null;
    }
    case 'text':
      return null;
  }
}

export function parseCommand(line: string, catalog: Catalog = BASE_CATALOG): ParsedCommand {
  const { tokens, error } = tokenize(line);
  const diagnostics: Diagnostic[] = [];
  const args: Record<string, string> = {};
  const done = (spec: VerbSpec | null): ParsedCommand => ({
    line,
    tokens,
    spec,
    args,
    diagnostics,
    sendable: !diagnostics.some((d) => d.severity === 'error'),
    canonical: tokens.length ? [tokens[0].toUpperCase(), ...tokens.slice(1)].map(quoteArg).join(' ') : '',
  });

  if (error) {
    diagnostics.push({ severity: 'error', message: error.toLowerCase(), token: -1 });
    return done(null);
  }
  if (!tokens.length) {
    diagnostics.push({ severity: 'error', message: 'empty command', token: -1 });
    return done(null);
  }

  const { spec, argStart } = resolveVerb(tokens);
  if (!spec) {
    const verb = tokens[0].toUpperCase();
    if (VERB_NAMES.includes(verb)) {
      const subs = VERBS.filter((v) => v.verb === verb).flatMap((v) => v.sub || []);
      diagnostics.push({
        severity: 'error',
        message: tokens[1] ? `${verb} does not take "${tokens[1]}"` : `${verb} needs one of: ${subs.join(', ')}`,
        token: tokens[1] ? 1 : 0,
        suggestions: tokens[1] ? closest(tokens[1].toUpperCase(), subs) : subs,
      });
    } else {
      diagnostics.push({ severity: 'error', message: `unknown verb "${tokens[0]}"`, token: 0, suggestions: closest(verb, VERB_NAMES) });
    }
    return done(null);
  }

  const rest = tokens.slice(argStart);
  let i = 0;
  for (const arg of spec.args) {
    if (arg.rest) {
      const text = rest.slice(i).join(' ');
      i = rest.length;
      if (!text && !arg.optional) {
        diagnostics.push({ severity: 'error', message: `${spec.verb} needs <${arg.name}>`, token: -1 });
      } else if (text) {
        args[arg.name] = text;
      }
      continue;
    }
    const raw = rest[i];
    if (raw === undefined) {
      if (!arg.optional) diagnostics.push({ severity: 'error', message: `missing <${arg.name}>`, token: -1 });
      else if (arg.defaultValue !== undefined) {
        args[arg.name] = arg.defaultValue;
        diagnostics.push({ severity: 'info', message: `<${arg.name}> defaults to ${arg.defaultValue}`, token: -1 });
      }
      i += 1;
      continue;
    }
    args[arg.name] = raw;
    const problem = checkValue(arg.kind, raw, catalog);
    if (problem) diagnostics.push({ ...problem, token: argStart + i });
    i += 1;
  }
  if (i < rest.length) {
    diagnostics.push({ severity: 'warning', message: `ignored extra argument${rest.length - i > 1 ? 's' : ''}: ${rest.slice(i).join(' ')}`, token: argStart + i });
  }
  if (spec.id === 'blend-era' && args.a && args.b && args.a === args.b) {
    diagnostics.push({ severity: 'warning', message: 'blending an era with itself is a no-op', token: -1 });
  }
  return done(spec);
}

// ── Completion ─────────────────────────────────────────────────────────

export interface Completion {
  /** Full line after accepting this completion. */
  line: string;
  label: string;
  detail?: string;
}

function valuesFor(kind: ArgKind, catalog: Catalog): string[] {
  switch (kind) {
    case 'era': return catalog.eras;
    case 'generation': return catalog.generations;
    case 'archetype': return catalog.archetypes;
    case 'axis': return [...TENSOR_AXES];
    case 'slot': return [...SLOTS];
    case 'backend': return [...BACKENDS];
    case 'unit': return ['0', '0.25', '0.5', '0.75', '1'];
    case 'int': return ['1', '3', '10'];
    case 'text': return [];
  }
}

export function complete(line: string, catalog: Catalog = BASE_CATALOG, limit = 8): Completion[] {
  const { tokens, error, trailingSpace } = tokenize(line);
  if (error) return [];
  const head = trailingSpace || !tokens.length ? tokens : tokens.slice(0, -1);
  const partial = trailingSpace || !tokens.length ? '' : tokens[tokens.length - 1];
  const prefix = head.map(quoteArg).join(' ');
  const join = (value: string) => `${prefix ? `${prefix} ` : ''}${value} `;
  const match = (values: readonly string[]) =>
    values.filter((v) => v.toLowerCase().startsWith(partial.toLowerCase())).slice(0, limit);

  if (!head.length) {
    const specs = VERBS.filter((v) => v.verb.startsWith(partial.toUpperCase()));
    const seen = new Set<string>();
    const out: Completion[] = [];
    for (const s of specs) {
      const label = s.sub ? `${s.verb} ${s.sub[0]}` : s.verb;
      if (seen.has(label)) continue;
      seen.add(label);
      out.push({ line: `${label} `, label, detail: s.summary });
    }
    return out.slice(0, limit);
  }

  const verb = head[0].toUpperCase();
  const family = VERBS.filter((v) => v.verb === verb);
  if (!family.length) return [];
  if (head.length === 1 && family.some((v) => v.sub)) {
    const subs = family.flatMap((v) => (v.sub ? [{ sub: v.sub[0], spec: v }] : []));
    return subs
      .filter((x) => x.sub.startsWith(partial.toUpperCase()))
      .slice(0, limit)
      .map((x) => ({ line: join(x.sub), label: x.sub, detail: x.spec.summary }));
  }
  const { spec, argStart } = resolveVerb(head.concat(partial ? [partial] : []));
  const target = spec ?? resolveVerb(head).spec;
  if (!target) return [];
  const start = spec ? argStart : resolveVerb(head).argStart;
  const index = head.length - start;
  const arg = target.args[Math.max(0, index)];
  if (!arg || arg.kind === 'text' || index < 0) return [];
  return match(valuesFor(arg.kind, catalog)).map((v) => ({ line: join(v), label: v, detail: `<${arg.name}>` }));
}

// ── Builders (structured controls → shlex-safe lines) ──────────────────

const unit = (t: number) => {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0));
  return String(Math.round(clamped * 1000) / 1000);
};

export const build = {
  bindEra: (era: string) => `BIND ERA ${quoteArg(era)}`,
  bindGeneration: (key: string) => `BIND GENERATION ${quoteArg(key)}`,
  bindArchetype: (name: string) => `BIND ARCHETYPE ${quoteArg(name.trim().toLowerCase())}`,
  bindSlot: (slot: string, backend: 'local' | 'echo' = 'local') => `BIND SLOT ${quoteArg(slot)} ${backend}`,
  setAxis: (axis: string, value: number) => `SET AXIS ${quoteArg(axis)} ${unit(value)}`,
  lerpEra: (era: string, t: number) => `LERP ERA ${quoteArg(era)} ${unit(t)}`,
  blendEra: (a: string, b: string, t: number) => `BLEND ERA ${quoteArg(a)} ${quoteArg(b)} ${unit(t)}`,
  detect: (text: string) => `DETECT ${text.trim()}`,
  compose: (vision: string) => `COMPOSE ${vision.replace(/\s+/g, ' ').trim()}`,
  think: (text: string) => `THINK ${text.trim()}`,
  train: (epochs: number) => `TRAIN ${Math.max(1, Math.floor(epochs))}`,
  roll: () => 'ROLL ORACLE',
  nick: () => 'NICK HELIX',
  ligate: () => 'LIGATE HELIX',
  snapshot: () => 'SNAPSHOT',
};

// ── Explaining results ─────────────────────────────────────────────────

function rec(v: unknown): Record<string, any> {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, any>) : {};
}

const fmt = (n: unknown, digits = 2) => (typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—');

/** One-line operator summary of a successful command envelope. */
export function describeResult(envelope: CommandEnvelope, spec: VerbSpec | null): string {
  const r = rec(envelope.result);
  switch (spec?.id) {
    case 'bind-era':
    case 'lerp-era':
    case 'detect':
      return `era → ${r.era ?? '?'}`;
    case 'blend-era': {
      const b = Array.isArray(r.blend) ? r.blend : [];
      return `blend ${b[0] ?? '?'} → ${b[1] ?? '?'} at t=${fmt(b[2])}`;
    }
    case 'set-axis':
      return `${r.axis} = ${fmt(r.value)}`;
    case 'bind-generation':
      return `generation → ${r.label ?? r.generation}${Array.isArray(r.viewport) ? ` (${r.viewport.join('×')})` : ''}`;
    case 'bind-archetype':
      return `archetype pinned → ${r.archetype}${r.composed ? ' (vision-composed)' : ''}`;
    case 'compose': {
      const features = Array.isArray(r.features) ? r.features : [];
      return r.summary ? String(r.summary) : `${features.length} systems: ${features.join(', ')}`;
    }
    case 'roll':
      return `oracle #${r.index ?? '?'}: ${r.text ?? ''}`;
    case 'nick':
    case 'ligate':
      return `helix σ=${fmt(r.sigma, 3)} · nicked=${r.nicked ?? '?'}`;
    case 'bind-slot':
      return `slot ${r.slot} → ${r.backend}`;
    case 'train':
      return `trained${r.epochs != null ? ` ${r.epochs} epoch(s)` : ''}${r.loss != null ? ` · loss ${fmt(r.loss, 4)}` : ''}`;
    case 'snapshot':
    case 'status':
      return `snapshot · ledger h=${rec(r.ledger).height ?? '?'}`;
    default: {
      const keys = Object.keys(r);
      return keys.length ? `${envelope.verb} → ${keys.slice(0, 4).join(', ')}${keys.length > 4 ? '…' : ''}` : `${envelope.verb} ok`;
    }
  }
}

export interface SnapshotChange {
  field: string;
  before: string;
  after: string;
  /** Signed magnitude for numeric axes; 0 for categorical changes. */
  delta: number;
}

/** What an operator action changed in the shared cockpit (for the console log). */
export function diffSnapshots(before: CockpitSnapshot | null, after: CockpitSnapshot | null, epsilon = 0.0005): SnapshotChange[] {
  if (!before || !after) return [];
  const out: SnapshotChange[] = [];
  const cat = (field: string, a: unknown, b: unknown) => {
    const sa = a == null ? '—' : Array.isArray(a) ? a.join(' / ') : String(a);
    const sb = b == null ? '—' : Array.isArray(b) ? b.join(' / ') : String(b);
    if (sa !== sb) out.push({ field, before: sa, after: sb, delta: 0 });
  };
  cat('era', before.tensor?.era, after.tensor?.era);
  for (const axis of TENSOR_AXES) {
    const a = before.tensor?.axes?.[axis];
    const b = after.tensor?.axes?.[axis];
    if (typeof a === 'number' && typeof b === 'number' && Math.abs(b - a) > epsilon) {
      out.push({ field: `axis.${axis}`, before: fmt(a, 3), after: fmt(b, 3), delta: b - a });
    }
  }
  cat('blend', before.blend, after.blend);
  cat('generation', before.generation, after.generation);
  cat('archetype', before.archetype, after.archetype);
  cat('oracle', before.oracle?.index, after.oracle?.index);
  cat('composition', before.composition?.blueprint_id, after.composition?.blueprint_id);
  if (before.helix && after.helix && Math.abs((after.helix.supercoiling ?? 0) - (before.helix.supercoiling ?? 0)) > epsilon) {
    out.push({ field: 'helix.σ', before: fmt(before.helix.supercoiling, 3), after: fmt(after.helix.supercoiling, 3), delta: after.helix.supercoiling - before.helix.supercoiling });
  }
  const hb = before.ledger?.height ?? 0;
  const ha = after.ledger?.height ?? 0;
  if (ha !== hb) out.push({ field: 'ledger.height', before: String(hb), after: String(ha), delta: ha - hb });
  if (before.ledger?.valid !== after.ledger?.valid) cat('ledger.valid', before.ledger?.valid, after.ledger?.valid);
  return out;
}

/**
 * Commands issued by *someone else* since our last look: the engine keeps the
 * last 20 history lines, so find where our known tail ends in the new list.
 */
export function foreignHistory(known: string[], latest: string[]): string[] {
  if (!known.length) return [];
  for (let overlap = Math.min(known.length, latest.length); overlap > 0; overlap -= 1) {
    const tail = known.slice(known.length - overlap);
    const head = latest.slice(0, overlap);
    if (tail.every((line, idx) => line === head[idx])) return latest.slice(overlap);
  }
  return latest.slice();
}
