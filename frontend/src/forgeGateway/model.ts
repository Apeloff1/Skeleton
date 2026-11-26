/**
 * Pure view-model for builds started through the backend forge gateway
 * (`/api/forge-gateway/*`). No I/O here, so it is unit-testable in Node.
 */
export type Playtest = 'off' | 'auto' | 'require';

export const MAX_BRIEF_CHARS = 4000;
export const TERMINAL = ['succeeded', 'failed', 'cancelled', 'dead_letter'] as const;

export interface BuildAck {
  execution_id: string;
  job_id?: string;
  status: string;
  status_ref: string;
  replayed?: boolean;
}

export interface BuildView {
  execution_id: string;
  status: string;
  progress?: number | null;
  message?: string | null;
  attempts?: number;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export type Phase = 'queued' | 'running' | 'succeeded' | 'failed';

export interface BuildSummary {
  phase: Phase;
  percent: number;
  stage: string;
  title: string | null;
  genre: string | null;
  proof: string | null;
  playtest: string | null;
  stubbed: string[];
  error: string | null;
}

export const EXAMPLE_BRIEFS: readonly { label: string; brief: string }[] = [
  { label: 'Platformer', brief: 'A small platformer. Fantasy: a fox on rain-slick rooftops. Core loop: run and jump from roof to roof until the far gate. Scope: small prototype.' },
  { label: 'Top-down shooter', brief: 'A small top-down shooter. Fantasy: neon sewer drones. Core loop: move, aim and clear enemy packs, then spend salvage. Scope: small prototype.' },
  { label: 'Roguelike RPG', brief: 'A small roguelike RPG. Fantasy: a cinder delve that forgets dead explorers. Core loop: enter rooms, fight, pay the vendor and follow the quest hook. Scope: small prototype.' },
];

/** Validate a brief exactly like the gateway does; returns an error message or null. */
export function validateBrief(raw: string): string | null {
  const brief = raw.trim();
  if (!brief) return 'Describe the game you want to build.';
  if (brief.length > MAX_BRIEF_CHARS) return `Keep the description under ${MAX_BRIEF_CHARS} characters.`;
  return null;
}

const str = (value: unknown): string | null => (typeof value === 'string' && value.trim() ? value.trim() : null);

export function isTerminal(status: string | undefined | null): boolean {
  return !!status && (TERMINAL as readonly string[]).includes(status);
}

/** Collapse an engine status document into what the screen shows. */
export function summarise(view: BuildView | null | undefined): BuildSummary {
  const status = view?.status ?? 'queued';
  const raw = typeof view?.progress === 'number' && Number.isFinite(view.progress) ? view.progress : 0;
  const percent = Math.round(Math.max(0, Math.min(1, raw)) * 100);
  const result = (view?.result && typeof view.result === 'object' ? view.result : {}) as Record<string, unknown>;
  const spec = (result.spec && typeof result.spec === 'object' ? result.spec : {}) as Record<string, unknown>;
  const playtest = result.playtest && typeof result.playtest === 'object' ? str((result.playtest as Record<string, unknown>).status) : null;
  const stubbed = Array.isArray(result.stubbed) ? result.stubbed.filter((s): s is string => typeof s === 'string').slice(0, 20) : [];
  const builtOk = status === 'succeeded' && result.ok !== false;
  const phase: Phase = builtOk ? 'succeeded'
    : isTerminal(status) ? 'failed'
      : status === 'queued' ? 'queued' : 'running';
  const error = phase === 'failed'
    ? str(view?.error) ?? str(result.error) ?? (status === 'succeeded' ? 'The build did not prove its core loop.' : 'The build did not finish.')
    : null;
  return {
    phase,
    percent: phase === 'succeeded' ? 100 : percent,
    stage: str(view?.message) ?? (phase === 'queued' ? 'Waiting for a builder…' : phase === 'running' ? 'Building…' : phase === 'succeeded' ? 'Done' : 'Stopped'),
    title: str(spec.title),
    genre: str(spec.genre)?.replace(/_/g, ' ') ?? null,
    proof: str(result.proof),
    playtest,
    stubbed,
    error,
  };
}

/** Polling backoff: quick at first, then settle at 2 s; honour Retry-After when given. */
export function nextPollDelay(attempt: number, retryAfterS?: number | null): number {
  if (retryAfterS && retryAfterS > 0) return Math.min(30_000, retryAfterS * 1000);
  return Math.min(2000, 600 + attempt * 200);
}

/** A per-submit idempotency key so a retried tap never starts a duplicate build. */
export function newIdempotencyKey(random: () => number = Math.random, now: () => number = Date.now): string {
  const rand = Array.from({ length: 16 }, () => Math.floor(random() * 36).toString(36)).join('');
  return `ng-${now().toString(36)}-${rand}`;
}

/** Human message for gateway HTTP failures (never shows raw server text for 5xx). */
export function gatewayErrorMessage(status: number, detail: string | null): string {
  if (status === 0) return 'You appear to be offline. Check your connection and try again.';
  if (status === 401) return 'Sign in to build games.';
  if (status === 403) return 'Your account cannot start builds. Ask an admin for editor access.';
  if (status === 404) return 'This build was not found. It may belong to another account or the server restarted.';
  if (status === 422) return detail || 'Check the description and try again.';
  if (status === 429) return 'Too many builds started. Wait a minute and try again.';
  if (status === 503) return 'Game building is not available on this server right now.';
  if (status === 504) return 'The game engine did not answer in time. Try again.';
  return 'The game engine is unavailable. Try again shortly.';
}
