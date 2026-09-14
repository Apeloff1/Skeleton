import AsyncStorage from '@react-native-async-storage/async-storage';

export type WorkState = 'idle' | 'working' | 'break' | 'food' | 'smoke';

export type WorkSession = {
  id: string;
  startedAt: string;
  endedAt: string | null;
  seconds: number;
  state: WorkState;
  note?: string;
};

export type WorkforceSnapshot = {
  schemaVersion: 3;
  activeSince: string | null;
  activeState: WorkState;
  sessions: WorkSession[];
  totalSeconds: number;
  productiveSeconds: number;
  pauseSeconds: number;
  coinsEarned: number;
};

const KEY = '@codedock:workforce:v3';
const LEGACY_KEY = '@codedock:workforce:v2';
const MAX_SESSIONS = 500;
const VALID_STATES = new Set<WorkState>(['idle', 'working', 'break', 'food', 'smoke']);

export const COINS_PER_HOUR = 200;
export const COIN_MILESTONES = [10_000, 100_000, 1_000_000] as const;

export const emptyWorkforceSnapshot = (): WorkforceSnapshot => ({
  schemaVersion: 3,
  activeSince: null,
  activeState: 'idle',
  sessions: [],
  totalSeconds: 0,
  productiveSeconds: 0,
  pauseSeconds: 0,
  coinsEarned: 0,
});

const finiteNonNegative = (value: unknown, fallback = 0): number => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(0, Math.floor(numeric)) : fallback;
};

const validIso = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  return Number.isFinite(Date.parse(value)) ? value : null;
};

const normalizeState = (value: unknown, fallback: WorkState = 'idle'): WorkState => {
  return typeof value === 'string' && VALID_STATES.has(value as WorkState)
    ? value as WorkState
    : fallback;
};

const normalizeSession = (value: unknown): WorkSession | null => {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Partial<WorkSession>;
  const startedAt = validIso(raw.startedAt);
  const endedAt = validIso(raw.endedAt);
  const state = normalizeState(raw.state);
  if (!startedAt || state === 'idle') return null;

  const inferredSeconds = endedAt
    ? durationSeconds(startedAt, Date.parse(endedAt))
    : 0;

  return {
    id: typeof raw.id === 'string' && raw.id.trim() ? raw.id : `${Date.parse(startedAt)}-legacy`,
    startedAt,
    endedAt,
    seconds: finiteNonNegative(raw.seconds, inferredSeconds),
    state,
    note: typeof raw.note === 'string' && raw.note.trim() ? raw.note.trim().slice(0, 500) : undefined,
  };
};

const safeParse = (value: string | null): WorkforceSnapshot => {
  if (!value) return emptyWorkforceSnapshot();

  try {
    const parsed = JSON.parse(value) as Partial<WorkforceSnapshot>;
    const sessions = Array.isArray(parsed.sessions)
      ? parsed.sessions.map(normalizeSession).filter((session): session is WorkSession => Boolean(session)).slice(0, MAX_SESSIONS)
      : [];

    const knownProductive = sessions
      .filter(session => session.state === 'working')
      .reduce((sum, session) => sum + session.seconds, 0);
    const knownPause = sessions
      .filter(session => session.state !== 'working')
      .reduce((sum, session) => sum + session.seconds, 0);
    const knownTotal = knownProductive + knownPause;

    const totalSeconds = Math.max(finiteNonNegative(parsed.totalSeconds), knownTotal);
    const productiveSeconds = Math.min(
      totalSeconds,
      Math.max(finiteNonNegative(parsed.productiveSeconds), knownProductive),
    );
    const pauseSeconds = Math.min(
      Math.max(0, totalSeconds - productiveSeconds),
      Math.max(finiteNonNegative(parsed.pauseSeconds), knownPause),
    );

    const activeState = normalizeState(parsed.activeState);
    const activeSince = activeState === 'idle' ? null : validIso(parsed.activeSince);
    const normalizedActiveState = activeSince ? activeState : 'idle';

    // Preserve already-earned legacy coins during the v2 -> v3 migration while
    // ensuring all future accrual is based on productive time only.
    const legacyCoins = finiteNonNegative(parsed.coinsEarned);
    const productiveCoins = coinsForSeconds(productiveSeconds);

    return {
      schemaVersion: 3,
      activeSince,
      activeState: normalizedActiveState,
      sessions,
      totalSeconds,
      productiveSeconds,
      pauseSeconds,
      coinsEarned: Math.max(legacyCoins, productiveCoins),
    };
  } catch {
    return emptyWorkforceSnapshot();
  }
};

export async function loadWorkforce(): Promise<WorkforceSnapshot> {
  const current = await AsyncStorage.getItem(KEY);
  if (current) return safeParse(current);

  const legacy = await AsyncStorage.getItem(LEGACY_KEY);
  const migrated = safeParse(legacy);
  if (legacy) await saveWorkforce(migrated);
  return migrated;
}

export async function saveWorkforce(snapshot: WorkforceSnapshot): Promise<void> {
  const normalized = safeParse(JSON.stringify({ ...snapshot, schemaVersion: 3 }));
  await AsyncStorage.setItem(KEY, JSON.stringify(normalized));
}

export function durationSeconds(startIso: string | null, nowMs = Date.now()): number {
  if (!startIso) return 0;
  const start = Date.parse(startIso);
  if (!Number.isFinite(start)) return 0;
  return Math.max(0, Math.floor((nowMs - start) / 1000));
}

export function coinsForSeconds(seconds: number): number {
  return Math.floor((Math.max(0, seconds) / 3600) * COINS_PER_HOUR);
}

export function closeActiveSession(snapshot: WorkforceSnapshot, nowIso = new Date().toISOString()): WorkforceSnapshot {
  if (!snapshot.activeSince || snapshot.activeState === 'idle') return snapshot;

  const seconds = durationSeconds(snapshot.activeSince, Date.parse(nowIso));
  const nextTotal = snapshot.totalSeconds + seconds;
  const nextProductive = snapshot.productiveSeconds + (snapshot.activeState === 'working' ? seconds : 0);
  const nextPause = snapshot.pauseSeconds + (snapshot.activeState === 'working' ? 0 : seconds);
  const session: WorkSession = {
    id: `${Date.parse(nowIso)}-${Math.random().toString(36).slice(2, 8)}`,
    startedAt: snapshot.activeSince,
    endedAt: nowIso,
    seconds,
    state: snapshot.activeState,
  };

  return {
    schemaVersion: 3,
    activeSince: null,
    activeState: 'idle',
    sessions: [session, ...snapshot.sessions].slice(0, MAX_SESSIONS),
    totalSeconds: nextTotal,
    productiveSeconds: nextProductive,
    pauseSeconds: nextPause,
    coinsEarned: Math.max(snapshot.coinsEarned, coinsForSeconds(nextProductive)),
  };
}

export function transitionWorkState(snapshot: WorkforceSnapshot, nextState: WorkState, nowIso = new Date().toISOString()): WorkforceSnapshot {
  if (snapshot.activeState === 'idle' && nextState !== 'working') return snapshot;

  const closed = closeActiveSession(snapshot, nowIso);
  if (nextState === 'idle') return closed;

  return {
    ...closed,
    activeSince: nowIso,
    activeState: nextState,
  };
}

export function getNextMilestone(coins: number): number | null {
  return COIN_MILESTONES.find(milestone => milestone > coins) ?? null;
}

export function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return [hours, minutes, secs].map(value => String(value).padStart(2, '0')).join(':');
}
