import type { CapturedSource, CrawlEvent, CrawlSession } from '../../../product/crawlerClient';

export type EmeraldPhase = 'inspect' | 'navigate' | 'fetch' | 'index' | 'error' | 'land';
export type EmeraldCue = Readonly<{ sequence: number; phase: EmeraldPhase; target: string; captured: boolean }>;
export type EmeraldTarget = Readonly<{ url: string | null; sourceId: string | null; captured: boolean }>;
export type EmeraldProjection = Readonly<{
  sessionId: string; watermark: number; initialized: boolean; cue: EmeraldCue | null;
  target: EmeraldTarget | null; resourceKey: string; pending: CrawlEvent | null; acknowledged: readonly string[];
  availability: 'waiting' | 'live' | 'stale' | 'inactive'; revision: number;
}>;
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const ACTIVE = new Set(['queued','ready','running']);
const TERMINAL = new Set(['paused','cancelled','completed','budget_exhausted','failed','interrupted']);
const PHASES: Readonly<Record<string, EmeraldPhase>> = {
  dispatch_reserved: 'fetch', robots: 'inspect', redirect: 'navigate',
  captured: 'inspect', duplicate: 'inspect', rejected: 'error', error: 'error',
  interrupted_dispatch: 'error', pause: 'land', resume: 'inspect', cancel: 'land',
  stopped: 'land', completed: 'land',
};
export function initialEmerald(sessionId: string): EmeraldProjection {
  return {sessionId, watermark: 0, initialized: false, cue: null, target: null,
    resourceKey: '', pending: null, acknowledged: [], availability: 'waiting', revision: 0};
}
function safeUrl(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 4096) return null;
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') && !url.username && !url.password ? value : null;
  } catch { return null; }
}
function sourceId(value: unknown): string | null {
  return typeof value === 'string' && ID.test(value) ? value : null;
}
function evidence(event: CrawlEvent, sources: readonly CapturedSource[]): CapturedSource | undefined {
  const id = sourceId(event.source_id), url = safeUrl(event.url);
  if (!id || !url) return undefined;
  return sources.slice(0,64).find(row => row.source_id === id && DIGEST.test(row.content_digest)
    && (row.url === url || row.canonical_url === url));
}
function targetFor(event: CrawlEvent, captured = false): EmeraldTarget {
  return {url: safeUrl(event.url), sourceId: sourceId(event.source_id), captured};
}
function localTarget(target: EmeraldTarget | null, seq: number): string {
  // No source URLs, text, account IDs or credentials cross into the animation runtime.
  return target?.sourceId ? 'source:' + target.sourceId : 'event:' + seq;
}
export function projectEmerald(
  previous: EmeraldProjection,
  session: CrawlSession,
  events: readonly CrawlEvent[],
  sources: readonly CapturedSource[],
  observed: boolean,
  stale: boolean,
): EmeraldProjection {
  let state = previous.sessionId === session.session_id ? previous : initialEmerald(session.session_id);
  const fresh = observed && !stale;
  const active = session.consent_current && ACTIVE.has(session.status);
  const availability = !fresh ? observed ? 'stale' : 'waiting' : active ? 'live' : 'inactive';
  if (!fresh) return {...state, availability, cue:null, target:null, resourceKey:'', pending:null};
  const valid = events.slice(-64).filter(e => Number.isSafeInteger(e.sequence) && e.sequence > 0);
  const last = valid[valid.length - 1];
  // The first observed history is a baseline, not new work. Reloads never replay smoke.
  if (!state.initialized) {
    return {...state, initialized:true, watermark:last?.sequence ?? 0, availability,
      target:active && last ? targetFor(last) : null};
  }
  if (last && last.sequence < state.watermark) return {...state, availability:'stale', cue:null, target:null, resourceKey:'', pending:null};
  let pending = state.pending;
  let newest = state.watermark;
  let target = state.target;
  let phase: EmeraldPhase | null = null;
  let captured = false;
  let ack = state.acknowledged;
  let resourceKey = state.resourceKey;
  for (const event of valid) {
    if (event.sequence <= newest) continue;
    newest = event.sequence;
    if (!Object.prototype.hasOwnProperty.call(PHASES,event.kind)) continue;
    const nextTarget = targetFor(event);
    const sameResource = !!resourceKey && !!target && ((!!nextTarget.url && nextTarget.url === target.url) || (!!nextTarget.sourceId && nextTarget.sourceId === target.sourceId));
    if (!sameResource) resourceKey = localTarget(nextTarget,event.sequence);
    target = nextTarget;
    phase = PHASES[event.kind];
    if (event.kind === 'captured') pending = event;
    else if (event.kind !== 'duplicate' && event.kind !== 'completed') pending = null;
  }
  // Late-arriving source inventory can acknowledge only the latest outstanding capture.
  // A capture acknowledgement is decorative and is NOT review, distillation, XP or model training.
  if (pending && session.consent_current && (active || session.status === 'completed')) {
    const row = evidence(pending,sources);
    if (row) {
      const key = row.source_id + ':' + row.content_digest;
      if (!ack.includes(key)) {
        ack = [...ack.slice(-63),key];
        target = targetFor(pending,true);
        phase = 'index'; captured = true; resourceKey ||= localTarget(target,pending.sequence);
      }
      pending = null;
    }
  }
  if (!active && !(captured && session.status === 'completed') && !(state.cue?.captured && session.status === 'completed' && session.consent_current && newest===state.watermark)) {
    pending = null; target = null;
    if (state.availability === 'live' || phase !== null || TERMINAL.has(session.status) && state.availability !== 'inactive') phase = 'land';
    else phase = null;
  }
  const revision = phase ? state.revision + 1 : state.revision;
  return {...state, availability, watermark:newest, target, resourceKey, pending, acknowledged:ack, revision,
    cue:phase ? {sequence:revision,phase,target:resourceKey || 'rest',captured} : state.cue};
}
