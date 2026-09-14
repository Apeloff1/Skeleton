import AsyncStorage from '@react-native-async-storage/async-storage';

export type MarketWatchItem = {
  id: string;
  symbol: string;
  thesis: string;
  createdAt: string;
};

export type MarketSignal = {
  id: string;
  symbol: string;
  signal: 'bullish' | 'neutral' | 'bearish';
  evidence: string;
  createdAt: string;
};

export type MarketWorkspaceSnapshot = {
  watchlist: MarketWatchItem[];
  signals: MarketSignal[];
};

const KEY = '@codedock:market-intelligence:v1';
const EMPTY: MarketWorkspaceSnapshot = { watchlist: [], signals: [] };

export async function loadMarketWorkspace(): Promise<MarketWorkspaceSnapshot> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<MarketWorkspaceSnapshot>;
    return {
      watchlist: Array.isArray(parsed.watchlist) ? parsed.watchlist.slice(0, 200) : [],
      signals: Array.isArray(parsed.signals) ? parsed.signals.slice(0, 500) : [],
    };
  } catch {
    return EMPTY;
  }
}

export async function saveMarketWorkspace(snapshot: MarketWorkspaceSnapshot): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify({
    watchlist: snapshot.watchlist.slice(0, 200),
    signals: snapshot.signals.slice(0, 500),
  }));
}

export function normalizeSymbol(value: string): string {
  return value.trim().toUpperCase().replace(/[^A-Z0-9.\-^]/g, '').slice(0, 12);
}

export function addWatchItem(snapshot: MarketWorkspaceSnapshot, symbol: string, thesis: string): MarketWorkspaceSnapshot {
  const normalized = normalizeSymbol(symbol);
  if (!normalized || snapshot.watchlist.some(item => item.symbol === normalized)) return snapshot;
  return {
    ...snapshot,
    watchlist: [{
      id: `${Date.now()}-${normalized}`,
      symbol: normalized,
      thesis: thesis.trim(),
      createdAt: new Date().toISOString(),
    }, ...snapshot.watchlist].slice(0, 200),
  };
}

export function addSignal(
  snapshot: MarketWorkspaceSnapshot,
  symbol: string,
  signal: MarketSignal['signal'],
  evidence: string,
): MarketWorkspaceSnapshot {
  const normalized = normalizeSymbol(symbol);
  if (!normalized || !evidence.trim()) return snapshot;
  return {
    ...snapshot,
    signals: [{
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      symbol: normalized,
      signal,
      evidence: evidence.trim(),
      createdAt: new Date().toISOString(),
    }, ...snapshot.signals].slice(0, 500),
  };
}
