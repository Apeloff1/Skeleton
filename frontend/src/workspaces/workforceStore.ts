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
  activeSince: string | null;
  activeState: WorkState;
  sessions: WorkSession[];
  totalSeconds: number;
  coinsEarned: number;
};

const KEY = '@codedock:workforce:v2';
export const COINS_PER_HOUR = 200;
export const COIN_MILESTONES = [10_000, 100_000, 1_000_000] as const;

const emptySnapshot = (): WorkforceSnapshot => ({
  activeSince: null,
  activeState: 'idle',
  sessions: [],
  totalSeconds: 0,
  coinsEarned: 0,
});

const safeParse = (value: string | null): WorkforceSnapshot => {
  if (!value) return emptySnapshot();
  try {
    const parsed = JSON.parse(value) as Partial<WorkforceSnapshot>;
    return {
      activeSince: typeof parsed.activeSince === 'string' ? parsed.activeSince : null,
      activeState: parsed.activeState ?? 'idle',
      sessions: Array.isArray(parsed.sessions) ? parsed.sessions.slice(0, 500) : [],
      totalSeconds: Number.isFinite(parsed.totalSeconds) ? Math.max(0, Number(parsed.totalSeconds)) : 0,
      coinsEarned: Number.isFinite(parsed.coinsEarned) ? Math.max(0, Number(parsed.coinsEarned)) : 0,
    };
  } catch {
    return emptySnapshot();
  }
};

export async function loadWorkforce(): Promise<WorkforceSnapshot> {
  return safeParse(await AsyncStorage.getItem(KEY));
}

export async function saveWorkforce(snapshot: WorkforceSnapshot): Promise<void> {
  const normalized: WorkforceSnapshot = {
    ...snapshot,
    sessions: snapshot.sessions.slice(0, 500),
    totalSeconds: Math.max(0, Math.floor(snapshot.totalSeconds)),
    coinsEarned: Math.max(0, Math.floor(snapshot.coinsEarned)),
  };
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
  const session: WorkSession = {
    id: `${Date.parse(nowIso)}-${Math.random().toString(36).slice(2, 8)}`,
    startedAt: snapshot.activeSince,
    endedAt: nowIso,
    seconds,
    state: snapshot.activeState,
  };

  return {
    activeSince: null,
    activeState: 'idle',
    sessions: [session, ...snapshot.sessions].slice(0, 500),
    totalSeconds: nextTotal,
    coinsEarned: coinsForSeconds(nextTotal),
  };
}

export function transitionWorkState(snapshot: WorkforceSnapshot, nextState: WorkState, nowIso = new Date().toISOString()): WorkforceSnapshot {
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
