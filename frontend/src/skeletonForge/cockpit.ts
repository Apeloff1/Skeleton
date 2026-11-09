/**
 * Cockpit console helpers for POST /api/skeleton/cockpit.
 * The server is authoritative; this only validates obvious mistakes early
 * and offers command suggestions.
 */

export const COCKPIT_VERBS = [
  'STATUS', 'SNAPSHOT', 'BIND', 'SET', 'LERP', 'BLEND', 'ROLL', 'NICK', 'LIGATE', 'DETECT', 'THINK',
  'ACQUIRE', 'SURPASS', 'TRAIN', 'RECALL', 'EXPORT', 'IMPORT', 'OWN', 'SHADOW', 'COMPOSE',
] as const;

export const COCKPIT_SUGGESTIONS: readonly { label: string; command: string; hint: string }[] = [
  { label: 'Status', command: 'STATUS', hint: 'Snapshot tensor, ledger, archetype and last composition.' },
  { label: 'Compose', command: 'COMPOSE ', hint: 'Preview the vision-derived blueprint.' },
  { label: 'Auto archetype', command: 'BIND ARCHETYPE auto', hint: 'Forge composes systems from the vision.' },
  { label: 'Extraction preset', command: 'BIND ARCHETYPE extraction', hint: 'Pin the canonical extraction loop.' },
  { label: 'Bind era', command: 'BIND ERA ', hint: 'Pin a design era, e.g. soulslike.' },
  { label: 'Roll oracle', command: 'ROLL ORACLE', hint: 'Draw an oracle reading from the lattice.' },
];

export interface CockpitCheck {
  ok: boolean;
  command: string;
  verb: string;
  error: string | null;
}

export function checkCommand(raw: string): CockpitCheck {
  const command = String(raw ?? '').trim().replace(/\s+/g, ' ');
  if (!command) return { ok: false, command, verb: '', error: 'Type a command.' };
  if (command.length > 4200) return { ok: false, command, verb: '', error: 'Command is too long.' };
  const [head, ...rest] = command.split(' ');
  const verb = head.toUpperCase();
  if (!(COCKPIT_VERBS as readonly string[]).includes(verb)) {
    return { ok: false, command, verb, error: `Unknown verb “${head}”. Try STATUS, COMPOSE <vision> or BIND ARCHETYPE auto.` };
  }
  if (verb === 'COMPOSE' && !rest.join(' ').trim()) return { ok: false, command, verb, error: 'COMPOSE needs a vision, e.g. COMPOSE a heist with a butler.' };
  if (verb === 'BIND' && rest[0]?.toUpperCase() === 'ARCHETYPE' && !rest[1]) {
    return { ok: false, command, verb, error: 'BIND ARCHETYPE <name|auto>' };
  }
  return { ok: true, command, verb, error: null };
}

export interface ConsoleEntry {
  id: number;
  command: string;
  ok: boolean;
  /** One-line human summary. */
  summary: string;
  result: unknown;
  at: number;
}

/** Summarise a cockpit result in one line for the console transcript. */
export function summarizeCockpit(command: string, result: any): string {
  if (!result || typeof result !== 'object') return String(result ?? 'ok');
  if (typeof result.summary === 'string') return result.summary;
  if (typeof result.archetype === 'string' && 'composed' in result) {
    return `Archetype pinned: ${result.archetype}${result.composed ? ' (composes from vision)' : ''}`;
  }
  if (typeof result.era === 'string' && !result.tensor?.axes) return `Era: ${result.era}`;
  if (result.tensor && result.ledger) {
    const era = result.tensor?.era ?? '—';
    return `Era ${era} · ledger ${result.ledger?.height ?? 0} blocks${result.ledger?.valid === false ? ' (INVALID)' : ''} · archetype ${result.archetype ?? 'extraction'}`;
  }
  if (typeof result.text === 'string') return result.text;
  const keys = Object.keys(result).slice(0, 4);
  return keys.length ? keys.join(', ') : `${command.split(' ')[0]} ok`;
}

/** Newest-first ring buffer, bounded. */
export function pushEntry(log: ConsoleEntry[], entry: ConsoleEntry, max = 40): ConsoleEntry[] {
  return [entry, ...log].slice(0, max);
}
