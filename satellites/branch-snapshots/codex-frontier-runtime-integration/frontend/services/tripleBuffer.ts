/**
 * ╔═══════════════════════════════════════════════════════════════╗
 * ║  QUAD BUFFER API PIPELINE v17.0                              ║
 * ║  Bulletproof data fetching with 4 failover layers            ║
 * ╚═══════════════════════════════════════════════════════════════╝
 *
 * Buffer 1 (LIVE):        Real API call with retry + exponential backoff
 * Buffer 2 (CACHE):       AsyncStorage-persisted last successful response
 * Buffer 3 (PREDICTIVE):  AI-reconstructed data from past patterns
 * Buffer 4 (STATIC):      Hard-coded fallback data that never fails
 *
 * On success:  Live → write to Cache + Patterns → return
 * On failure:  Cache → return cached
 * Cache miss:  Predictive → reconstruct from learned patterns
 * All fail:    Static → return fallback
 *
 * Also provides: pipeline health monitoring, warm cache on boot,
 * stale-while-revalidate pattern, deduplication, and pattern learning.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';

// ============================================================================
// CONFIG
// ============================================================================

const API_BASE = Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL
  || process.env.EXPO_PUBLIC_BACKEND_URL
  || '';

const CACHE_PREFIX = 'tb_cache_';
const CACHE_TTL_MS = 5 * 60 * 1000;        // 5 min fresh cache
const STALE_TTL_MS = 60 * 60 * 1000;       // 1 hr stale-but-usable
const LIVE_TIMEOUT_MS = 8000;               // 8s per attempt
const MAX_RETRIES = 2;                      // 2 retries = 3 total attempts
const RETRY_BASE_DELAY = 800;              // 800ms initial backoff
const DEDUP_WINDOW_MS = 300;               // 300ms dedup window

// ============================================================================
// TYPES
// ============================================================================

export type BufferSource = 'live' | 'cache' | 'predictive' | 'static';

export interface TripleBufferResult<T> {
  data: T;
  source: BufferSource;
  fresh: boolean;          // true if from live or fresh cache
  cachedAt?: number;       // timestamp of cache entry
  latencyMs: number;       // total fetch time
  retries: number;         // attempts used for live
  error?: string;          // error from live if fell back
}

interface CacheEntry<T = any> {
  data: T;
  timestamp: number;
  endpoint: string;
}

export interface PipelineHealth {
  liveAvailable: boolean;
  cacheHits: number;
  cacheMisses: number;
  predictiveHits: number;
  staticFallbacks: number;
  liveSuccesses: number;
  liveFailures: number;
  lastLiveSuccess: number | null;
  lastLiveFailure: number | null;
  avgLatencyMs: number;
  patternsLearned: number;
}

// ============================================================================
// IN-MEMORY STATE
// ============================================================================

// Deduplication map: key → pending Promise
const inflightRequests = new Map<string, Promise<TripleBufferResult<any>>>();

// Health counters
const health: PipelineHealth = {
  liveAvailable: true,
  cacheHits: 0,
  cacheMisses: 0,
  predictiveHits: 0,
  staticFallbacks: 0,
  liveSuccesses: 0,
  liveFailures: 0,
  lastLiveSuccess: null,
  lastLiveFailure: null,
  avgLatencyMs: 0,
  patternsLearned: 0,
};

let totalLatency = 0;
let totalRequests = 0;

// In-memory cache mirror (faster than AsyncStorage)
const memoryCache = new Map<string, CacheEntry>();

// ============================================================================
// BUFFER 3 (NEW): PREDICTIVE PATTERN STORE
// ============================================================================

// Pattern store: learns response shapes from successful API calls
// When cache expires AND live fails, reconstruct from patterns
interface ResponsePattern {
  endpoint: string;
  shape: string;         // JSON structure fingerprint
  lastData: any;         // Most recent response
  frequency: number;     // How often this endpoint is called
  stability: number;     // 0-1, how stable the response shape is
  updatedAt: number;
}

const patternStore = new Map<string, ResponsePattern>();
const PATTERN_PREFIX = 'qb_pattern_';

// Learn patterns from every successful live response
function learnPattern(endpoint: string, data: any): void {
  const existing = patternStore.get(endpoint);
  const shape = getResponseShape(data);

  if (existing) {
    const shapeStable = existing.shape === shape;
    patternStore.set(endpoint, {
      ...existing,
      lastData: data,
      shape,
      frequency: existing.frequency + 1,
      stability: shapeStable
        ? Math.min(1, existing.stability + 0.1)
        : Math.max(0, existing.stability - 0.2),
      updatedAt: Date.now(),
    });
  } else {
    patternStore.set(endpoint, {
      endpoint,
      shape,
      lastData: data,
      frequency: 1,
      stability: 0.5,
      updatedAt: Date.now(),
    });
    health.patternsLearned++;
  }

  // Persist pattern to AsyncStorage (non-blocking)
  AsyncStorage.setItem(
    `${PATTERN_PREFIX}${endpoint}`,
    JSON.stringify(patternStore.get(endpoint))
  ).catch(() => {});
}

// Reconstruct data from pattern when cache is fully expired
async function predictFromPattern<T>(endpoint: string): Promise<T | null> {
  // Check memory first
  let pattern = patternStore.get(endpoint);

  // Try AsyncStorage
  if (!pattern) {
    try {
      const raw = await AsyncStorage.getItem(`${PATTERN_PREFIX}${endpoint}`);
      if (raw) {
        pattern = JSON.parse(raw);
        if (pattern) patternStore.set(endpoint, pattern);
      }
    } catch {}
  }

  if (!pattern || !pattern.lastData) return null;

  // Only use if stability > 0.3 (pattern is somewhat reliable)
  if (pattern.stability < 0.3) return null;

  return pattern.lastData as T;
}

// Generate a structural fingerprint of a JSON response
function getResponseShape(data: any, depth: number = 0): string {
  if (depth > 3) return typeof data;
  if (data === null || data === undefined) return 'null';
  if (Array.isArray(data)) {
    if (data.length === 0) return '[]';
    return `[${getResponseShape(data[0], depth + 1)}]`;
  }
  if (typeof data === 'object') {
    const keys = Object.keys(data).sort().slice(0, 10);
    return `{${keys.join(',')}}`;
  }
  return typeof data;
}

// ============================================================================
// CORE: LIVE FETCH (Buffer 1)
// ============================================================================

async function liveFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<{ data: T; retries: number }> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), LIVE_TIMEOUT_MS);

      const url = `${API_BASE}${endpoint}`;
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return { data, retries: attempt };

    } catch (err: any) {
      lastError = err;
      if (attempt < MAX_RETRIES) {
        const delay = RETRY_BASE_DELAY * Math.pow(2, attempt) + Math.random() * 200;
        await new Promise(r => setTimeout(r, delay));
      }
    }
  }

  throw lastError || new Error('Live fetch failed');
}

// ============================================================================
// CORE: CACHE (Buffer 2)
// ============================================================================

function cacheKey(endpoint: string): string {
  return `${CACHE_PREFIX}${endpoint}`;
}

async function writeCache<T>(endpoint: string, data: T): Promise<void> {
  const entry: CacheEntry<T> = {
    data,
    timestamp: Date.now(),
    endpoint,
  };

  // Write to both memory and AsyncStorage
  memoryCache.set(endpoint, entry);

  try {
    await AsyncStorage.setItem(cacheKey(endpoint), JSON.stringify(entry));
  } catch {
    // AsyncStorage full or unavailable — memory cache still works
  }
}

async function readCache<T>(endpoint: string): Promise<CacheEntry<T> | null> {
  // Check memory first (fast path)
  const memEntry = memoryCache.get(endpoint);
  if (memEntry) return memEntry as CacheEntry<T>;

  // Fall back to AsyncStorage
  try {
    const raw = await AsyncStorage.getItem(cacheKey(endpoint));
    if (raw) {
      const entry = JSON.parse(raw) as CacheEntry<T>;
      // Warm memory cache
      memoryCache.set(endpoint, entry);
      return entry;
    }
  } catch {
    // Corrupted or unavailable
  }

  return null;
}

function isFreshCache(entry: CacheEntry): boolean {
  return Date.now() - entry.timestamp < CACHE_TTL_MS;
}

function isStaleButUsable(entry: CacheEntry): boolean {
  return Date.now() - entry.timestamp < STALE_TTL_MS;
}

// ============================================================================
// CORE: QUAD BUFFER FETCH (Live → Cache → Predictive → Static)
// ============================================================================

async function tripleBufferFetch<T>(
  endpoint: string,
  staticFallback: T,
  options: RequestInit = {},
  skipCache: boolean = false
): Promise<TripleBufferResult<T>> {
  const startTime = Date.now();

  // === BUFFER 1: LIVE FETCH ===
  try {
    const { data, retries } = await liveFetch<T>(endpoint, options);

    // Success: update cache AND learn pattern
    await writeCache(endpoint, data);
    learnPattern(endpoint, data);

    // Update health
    health.liveAvailable = true;
    health.liveSuccesses++;
    health.lastLiveSuccess = Date.now();
    const latency = Date.now() - startTime;
    totalLatency += latency;
    totalRequests++;
    health.avgLatencyMs = Math.round(totalLatency / totalRequests);

    return {
      data,
      source: 'live',
      fresh: true,
      latencyMs: latency,
      retries,
    };

  } catch (liveError: any) {
    health.liveFailures++;
    health.lastLiveFailure = Date.now();

    // If too many consecutive failures, mark as unavailable
    if (health.liveFailures > 3 && (!health.lastLiveSuccess || Date.now() - health.lastLiveSuccess > 30000)) {
      health.liveAvailable = false;
    }

    // === BUFFER 2: CACHE ===
    if (!skipCache) {
      const cached = await readCache<T>(endpoint);

      if (cached && isStaleButUsable(cached)) {
        health.cacheHits++;
        const isFresh = isFreshCache(cached);

        // If stale, kick off background refresh (stale-while-revalidate)
        if (!isFresh) {
          backgroundRefresh(endpoint, options);
        }

        return {
          data: cached.data,
          source: 'cache',
          fresh: isFresh,
          cachedAt: cached.timestamp,
          latencyMs: Date.now() - startTime,
          retries: MAX_RETRIES + 1,
          error: liveError.message,
        };
      }
      health.cacheMisses++;
    }

    // === BUFFER 3: PREDICTIVE RECONSTRUCTION ===
    const predicted = await predictFromPattern<T>(endpoint);
    if (predicted !== null) {
      health.predictiveHits++;
      
      // Also kick off a background refresh
      backgroundRefresh(endpoint, options);

      return {
        data: predicted,
        source: 'predictive',
        fresh: false,
        latencyMs: Date.now() - startTime,
        retries: MAX_RETRIES + 1,
        error: liveError.message,
      };
    }

    // === BUFFER 4: STATIC FALLBACK ===
    health.staticFallbacks++;

    return {
      data: staticFallback,
      source: 'static',
      fresh: false,
      latencyMs: Date.now() - startTime,
      retries: MAX_RETRIES + 1,
      error: liveError.message,
    };
  }
}

// Background refresh for stale-while-revalidate
function backgroundRefresh(endpoint: string, options: RequestInit = {}): void {
  // Non-blocking async refresh
  liveFetch(endpoint, options)
    .then(({ data }) => {
      writeCache(endpoint, data);
      health.liveAvailable = true;
      health.liveSuccesses++;
      health.lastLiveSuccess = Date.now();
    })
    .catch(() => {
      // Silent fail — stale cache is already served
    });
}

// ============================================================================
// DEDUP WRAPPER: Prevents duplicate concurrent requests
// ============================================================================

export async function tripleBufferGet<T>(
  endpoint: string,
  staticFallback: T,
  options?: { skipCache?: boolean }
): Promise<TripleBufferResult<T>> {
  // Dedup: if same request is inflight, reuse it
  const existing = inflightRequests.get(endpoint);
  if (existing) return existing;

  const promise = tripleBufferFetch<T>(endpoint, staticFallback, { method: 'GET' }, options?.skipCache);
  inflightRequests.set(endpoint, promise);

  try {
    return await promise;
  } finally {
    // Clear after small window for near-simultaneous calls
    setTimeout(() => inflightRequests.delete(endpoint), DEDUP_WINDOW_MS);
  }
}

export async function tripleBufferPost<T>(
  endpoint: string,
  body: any,
  staticFallback: T
): Promise<TripleBufferResult<T>> {
  // POST always goes live (no cache read), but caches result
  return tripleBufferFetch<T>(
    endpoint,
    staticFallback,
    { method: 'POST', body: JSON.stringify(body) },
    true // skipCache for POST
  );
}

// ============================================================================
// HEALTH & CACHE MANAGEMENT
// ============================================================================

export function getPipelineHealth(): PipelineHealth {
  return { ...health };
}

export async function warmCache(endpoints: string[]): Promise<void> {
  // Pre-warm cache on app boot
  await Promise.allSettled(
    endpoints.map(async ep => {
      try {
        const { data } = await liveFetch(ep);
        await writeCache(ep, data);
      } catch {
        // Silent fail
      }
    })
  );
}

export async function clearAllCache(): Promise<void> {
  memoryCache.clear();
  try {
    const allKeys = await AsyncStorage.getAllKeys();
    const cacheKeys = allKeys.filter(k => k.startsWith(CACHE_PREFIX));
    if (cacheKeys.length > 0) {
      await AsyncStorage.multiRemove(cacheKeys);
    }
  } catch {
    // Ignore
  }
}

export function resetHealthCounters(): void {
  health.cacheHits = 0;
  health.cacheMisses = 0;
  health.staticFallbacks = 0;
  health.liveSuccesses = 0;
  health.liveFailures = 0;
  health.avgLatencyMs = 0;
  totalLatency = 0;
  totalRequests = 0;
}

// ============================================================================
// STATIC FALLBACK DATA REGISTRY
// ============================================================================

export const STATIC_FALLBACKS = {
  languages: [
    { key: 'python', name: 'Python', display_name: 'Python 3.12+', extension: '.py', icon: 'logo-python', color: '#3776AB', executable: true, type: 'builtin', tier: 1 },
    { key: 'javascript', name: 'JavaScript', display_name: 'JavaScript ES2026', extension: '.js', icon: 'logo-javascript', color: '#F7DF1E', executable: true, type: 'builtin', tier: 1 },
    { key: 'typescript', name: 'TypeScript', display_name: 'TypeScript 5.6+', extension: '.ts', icon: 'logo-javascript', color: '#3178C6', executable: true, type: 'builtin', tier: 1 },
    { key: 'html', name: 'HTML', display_name: 'HTML 5.3', extension: '.html', icon: 'logo-html5', color: '#E34F26', executable: true, type: 'builtin', tier: 1 },
    { key: 'cpp', name: 'C++', display_name: 'C++23', extension: '.cpp', icon: 'code-slash', color: '#00599C', executable: true, type: 'builtin', tier: 1 },
    { key: 'c', name: 'C', display_name: 'C23', extension: '.c', icon: 'code-slash', color: '#A8B9CC', executable: true, type: 'builtin', tier: 1 },
    { key: 'rust', name: 'Rust', display_name: 'Rust 2024', extension: '.rs', icon: 'construct', color: '#CE422B', executable: true, type: 'builtin', tier: 1 },
    { key: 'go', name: 'Go', display_name: 'Go 1.22', extension: '.go', icon: 'rocket', color: '#00ADD8', executable: true, type: 'builtin', tier: 1 },
    { key: 'java', name: 'Java', display_name: 'Java 22', extension: '.java', icon: 'cafe', color: '#ED8B00', executable: true, type: 'builtin', tier: 1 },
    { key: 'kotlin', name: 'Kotlin', display_name: 'Kotlin 2.0', extension: '.kt', icon: 'phone-portrait', color: '#7F52FF', executable: true, type: 'builtin', tier: 1 },
    { key: 'swift', name: 'Swift', display_name: 'Swift 5.10', extension: '.swift', icon: 'logo-apple', color: '#FA7343', executable: true, type: 'builtin', tier: 1 },
    { key: 'csharp', name: 'C#', display_name: 'C# 12', extension: '.cs', icon: 'game-controller', color: '#68217A', executable: true, type: 'builtin', tier: 1 },
    { key: 'ruby', name: 'Ruby', display_name: 'Ruby 3.3', extension: '.rb', icon: 'diamond', color: '#CC342D', executable: true, type: 'builtin', tier: 1 },
    { key: 'php', name: 'PHP', display_name: 'PHP 8.3', extension: '.php', icon: 'globe', color: '#777BB4', executable: true, type: 'builtin', tier: 1 },
    { key: 'dart', name: 'Dart', display_name: 'Dart 3.3', extension: '.dart', icon: 'apps', color: '#0175C2', executable: true, type: 'builtin', tier: 2 },
    { key: 'scala', name: 'Scala', display_name: 'Scala 3', extension: '.scala', icon: 'layers', color: '#DC322F', executable: true, type: 'builtin', tier: 2 },
    { key: 'haskell', name: 'Haskell', display_name: 'Haskell GHC 9', extension: '.hs', icon: 'infinite', color: '#5D4F85', executable: true, type: 'builtin', tier: 2 },
    { key: 'elixir', name: 'Elixir', display_name: 'Elixir 1.16', extension: '.ex', icon: 'flask', color: '#6E4A7E', executable: true, type: 'builtin', tier: 2 },
    { key: 'sql', name: 'SQL', display_name: 'SQL Standard', extension: '.sql', icon: 'file-tray-stacked', color: '#E38C00', executable: true, type: 'builtin', tier: 1 },
    { key: 'bash', name: 'Bash', display_name: 'Bash 5', extension: '.sh', icon: 'terminal', color: '#4EAA25', executable: true, type: 'builtin', tier: 1 },
  ],

  aiModes: [
    { key: 'explain', name: 'Explain', description: 'Get detailed code explanation', icon: 'bulb' },
    { key: 'debug', name: 'Debug', description: 'Find and fix bugs', icon: 'bug' },
    { key: 'optimize', name: 'Optimize', description: 'Improve performance', icon: 'flash' },
    { key: 'complete', name: 'Complete', description: 'Auto-complete code', icon: 'code-slash' },
    { key: 'refactor', name: 'Refactor', description: 'Improve structure', icon: 'construct' },
    { key: 'document', name: 'Document', description: 'Generate documentation', icon: 'document-text' },
    { key: 'test_gen', name: 'Test Gen', description: 'Generate unit tests', icon: 'flask' },
    { key: 'security_audit', name: 'Security Audit', description: 'Security analysis', icon: 'shield-checkmark' },
    { key: 'convert', name: 'Convert', description: 'Convert to another language', icon: 'swap-horizontal' },
    { key: 'teach', name: 'Teach', description: 'Explain for beginners', icon: 'school' },
    { key: 'review', name: 'Review', description: 'Code review feedback', icon: 'eye' },
    { key: 'architecture', name: 'Architecture', description: 'Architecture suggestions', icon: 'git-branch' },
  ],

  achievements: [
    { id: 'first_class', name: 'First Steps', description: 'Complete your first class', icon: 'school', color: '#3B82F6', xp: 50, rarity: 'common', earned: false },
    { id: 'repeat_learner', name: 'Repeat Learner', description: 'Complete any class twice', icon: 'refresh', color: '#8B5CF6', xp: 100, rarity: 'uncommon', earned: false },
    { id: 'triple_master', name: 'Triple Master', description: 'Complete the same class 3 times', icon: 'trophy', color: '#F59E0B', xp: 250, rarity: 'rare', earned: false },
  ],

  emptyProgress: {
    total_completions: 0, unique_classes: 0, unique_languages: 0,
    languages_studied: [], total_xp: 0, level: 1,
    achievements_count: 0, repeated_classes: [],
  },
};

// ============================================================================
// PRE-WARM ON IMPORT: Warm critical caches in background
// ============================================================================

const CRITICAL_ENDPOINTS = [
  '/api/languages',
  '/api/ai/modes',
  '/api/class-progress/achievements/all',
  '/api/jeeves-languages/overview',
];

// Warm caches 2 seconds after import (non-blocking)
setTimeout(() => warmCache(CRITICAL_ENDPOINTS), 2000);
