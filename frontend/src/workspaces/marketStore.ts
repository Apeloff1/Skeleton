import AsyncStorage from '@react-native-async-storage/async-storage';

export type MarketSourceKind = 'url' | 'news' | 'filing' | 'research' | 'note';

export type MarketSource = {
  id: string;
  title: string;
  locator: string;
  kind: MarketSourceKind;
  observedAt: string;
  createdAt: string;
};

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
  sourceIds: string[];
  createdAt: string;
};

export type MarketWorkspaceSnapshot = {
  schemaVersion: 2;
  watchlist: MarketWatchItem[];
  sources: MarketSource[];
  signals: MarketSignal[];
};

const KEY = '@codedock:market-intelligence:v2';
const LEGACY_KEY = '@codedock:market-intelligence:v1';
const MAX_WATCHLIST = 200;
const MAX_SIGNALS = 500;
const MAX_SOURCES = 500;
const VALID_SIGNAL = new Set<MarketSignal['signal']>(['bullish', 'neutral', 'bearish']);
const VALID_SOURCE_KIND = new Set<MarketSourceKind>(['url', 'news', 'filing', 'research', 'note']);

export const emptyMarketWorkspace = (): MarketWorkspaceSnapshot => ({
  schemaVersion: 2,
  watchlist: [],
  sources: [],
  signals: [],
});

const validIso = (value: unknown): string => {
  if (typeof value === 'string' && Number.isFinite(Date.parse(value))) return value;
  return new Date().toISOString();
};

const cleanText = (value: unknown, maxLength: number): string => {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
};

const normalizeWatchItem = (value: unknown): MarketWatchItem | null => {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Partial<MarketWatchItem>;
  const symbol = normalizeSymbol(cleanText(raw.symbol, 12));
  if (!symbol) return null;
  const createdAt = validIso(raw.createdAt);
  return {
    id: cleanText(raw.id, 120) || `${Date.parse(createdAt)}-${symbol}`,
    symbol,
    thesis: cleanText(raw.thesis, 1000),
    createdAt,
  };
};

const normalizeSource = (value: unknown): MarketSource | null => {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Partial<MarketSource>;
  const title = cleanText(raw.title, 300);
  const locator = cleanText(raw.locator, 1500);
  if (!title && !locator) return null;
  const createdAt = validIso(raw.createdAt);
  const kind = typeof raw.kind === 'string' && VALID_SOURCE_KIND.has(raw.kind as MarketSourceKind)
    ? raw.kind as MarketSourceKind
    : 'note';
  return {
    id: cleanText(raw.id, 120) || `${Date.parse(createdAt)}-source`,
    title: title || locator.slice(0, 80),
    locator,
    kind,
    observedAt: validIso(raw.observedAt),
    createdAt,
  };
};

const normalizeSignal = (value: unknown, knownSourceIds: Set<string>): MarketSignal | null => {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Partial<MarketSignal>;
  const symbol = normalizeSymbol(cleanText(raw.symbol, 12));
  const evidence = cleanText(raw.evidence, 3000);
  if (!symbol || !evidence) return null;
  const signal = typeof raw.signal === 'string' && VALID_SIGNAL.has(raw.signal as MarketSignal['signal'])
    ? raw.signal as MarketSignal['signal']
    : 'neutral';
  const createdAt = validIso(raw.createdAt);
  const sourceIds = Array.isArray(raw.sourceIds)
    ? [...new Set(raw.sourceIds.filter((id): id is string => typeof id === 'string' && knownSourceIds.has(id)))].slice(0, 20)
    : [];
  return {
    id: cleanText(raw.id, 120) || `${Date.parse(createdAt)}-${symbol}`,
    symbol,
    signal,
    evidence,
    sourceIds,
    createdAt,
  };
};

const safeParse = (raw: string | null): MarketWorkspaceSnapshot => {
  if (!raw) return emptyMarketWorkspace();
  try {
    const parsed = JSON.parse(raw) as Partial<MarketWorkspaceSnapshot>;
    const sources = Array.isArray(parsed.sources)
      ? parsed.sources.map(normalizeSource).filter((item): item is MarketSource => Boolean(item)).slice(0, MAX_SOURCES)
      : [];
    const sourceIds = new Set(sources.map(source => source.id));
    return {
      schemaVersion: 2,
      watchlist: Array.isArray(parsed.watchlist)
        ? parsed.watchlist.map(normalizeWatchItem).filter((item): item is MarketWatchItem => Boolean(item)).slice(0, MAX_WATCHLIST)
        : [],
      sources,
      signals: Array.isArray(parsed.signals)
        ? parsed.signals.map(item => normalizeSignal(item, sourceIds)).filter((item): item is MarketSignal => Boolean(item)).slice(0, MAX_SIGNALS)
        : [],
    };
  } catch {
    return emptyMarketWorkspace();
  }
};

export async function loadMarketWorkspace(): Promise<MarketWorkspaceSnapshot> {
  const current = await AsyncStorage.getItem(KEY);
  if (current) return safeParse(current);

  const legacy = await AsyncStorage.getItem(LEGACY_KEY);
  const migrated = safeParse(legacy);
  if (legacy) await saveMarketWorkspace(migrated);
  return migrated;
}

export async function saveMarketWorkspace(snapshot: MarketWorkspaceSnapshot): Promise<void> {
  const normalized = safeParse(JSON.stringify({ ...snapshot, schemaVersion: 2 }));
  await AsyncStorage.setItem(KEY, JSON.stringify(normalized));
}

export function normalizeSymbol(value: string): string {
  return value.trim().toUpperCase().replace(/[^A-Z0-9.\-^]/g, '').slice(0, 12);
}

export function normalizeLocator(value: string): string {
  return value.trim().replace(/\s+/g, ' ').slice(0, 1500);
}

export function addWatchItem(snapshot: MarketWorkspaceSnapshot, symbol: string, thesis: string): MarketWorkspaceSnapshot {
  const normalized = normalizeSymbol(symbol);
  if (!normalized || snapshot.watchlist.some(item => item.symbol === normalized)) return snapshot;
  return {
    ...snapshot,
    watchlist: [{
      id: `${Date.now()}-${normalized}`,
      symbol: normalized,
      thesis: thesis.trim().slice(0, 1000),
      createdAt: new Date().toISOString(),
    }, ...snapshot.watchlist].slice(0, MAX_WATCHLIST),
  };
}

export function addSource(
  snapshot: MarketWorkspaceSnapshot,
  title: string,
  locator: string,
  kind: MarketSourceKind,
  observedAt = new Date().toISOString(),
): MarketWorkspaceSnapshot {
  const cleanTitle = cleanText(title, 300);
  const cleanLocator = normalizeLocator(locator);
  if (!cleanTitle && !cleanLocator) return snapshot;
  const now = new Date().toISOString();
  const source: MarketSource = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: cleanTitle || cleanLocator.slice(0, 80),
    locator: cleanLocator,
    kind,
    observedAt: validIso(observedAt),
    createdAt: now,
  };
  return { ...snapshot, sources: [source, ...snapshot.sources].slice(0, MAX_SOURCES) };
}

export function removeSource(snapshot: MarketWorkspaceSnapshot, sourceId: string): MarketWorkspaceSnapshot {
  if (!snapshot.sources.some(source => source.id === sourceId)) return snapshot;
  return {
    ...snapshot,
    sources: snapshot.sources.filter(source => source.id !== sourceId),
    signals: snapshot.signals.map(signal => ({
      ...signal,
      sourceIds: signal.sourceIds.filter(id => id !== sourceId),
    })),
  };
}

export function addSignal(
  snapshot: MarketWorkspaceSnapshot,
  symbol: string,
  signal: MarketSignal['signal'],
  evidence: string,
  sourceIds: readonly string[] = [],
): MarketWorkspaceSnapshot {
  const normalized = normalizeSymbol(symbol);
  const cleanEvidence = evidence.trim().slice(0, 3000);
  if (!normalized || !cleanEvidence) return snapshot;
  const knownSourceIds = new Set(snapshot.sources.map(source => source.id));
  const linkedSources = [...new Set(sourceIds.filter(id => knownSourceIds.has(id)))].slice(0, 20);
  return {
    ...snapshot,
    signals: [{
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      symbol: normalized,
      signal,
      evidence: cleanEvidence,
      sourceIds: linkedSources,
      createdAt: new Date().toISOString(),
    }, ...snapshot.signals].slice(0, MAX_SIGNALS),
  };
}
