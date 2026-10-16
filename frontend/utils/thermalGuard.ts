/**
 * ╔══════════════════════════════════════════════════════════════════════════╗
 * ║    THERMAL GUARD ENGINE v1.0 — Stagger + Stutterstep + Redundancy      ║
 * ║                                                                          ║
 * ║    Real device heat management for marathon coding sessions              ║
 * ║    • StaggerQueue: serialized API calls with configurable delays         ║
 * ║    • StutterStep: adaptive backoff that increases under sustained load   ║
 * ║    • Request deduplication with cooldown windows                          ║
 * ║    • Activity tracking with auto-throttle after sustained heavy use      ║
 * ║    • Memory pressure estimation + cache purging                          ║
 * ╚══════════════════════════════════════════════════════════════════════════╝
 */

// ═══════════════ THERMAL LEVELS ═══════════════

export type ThermalLevel = 'cool' | 'warm' | 'hot' | 'critical';

export interface ThermalState {
  level: ThermalLevel;
  score: number;              // 0-100 composite score
  activeRequests: number;
  totalRequestsLastMinute: number;
  stutterDelayMs: number;
  isThrottled: boolean;
  lastActivityBurst: number;  // timestamp
  sessionMinutes: number;
  memoryPressure: 'low' | 'medium' | 'high';
  cacheEntries: number;
}

// ═══════════════ STAGGER QUEUE ═══════════════

interface QueuedRequest {
  id: string;
  fn: () => Promise<any>;
  resolve: (value: any) => void;
  reject: (error: any) => void;
  priority: number; // lower = higher priority
  timestamp: number;
}

class StaggerQueue {
  private queue: QueuedRequest[] = [];
  private processing = false;
  private activeCount = 0;
  // Invalidates a request that has left the queue but is still in its delay.
  private generation = 0;
  // Share the same promise for queued AND actively executing work.
  private readonly pending = new Map<string, Promise<unknown>>();
  private readonly MAX_QUEUE_LENGTH = 256;
  private maxConcurrent: number;
  private baseDelayMs: number;
  private currentDelayMs: number;
  private requestLog: number[] = [];      // timestamps of recent requests
  private readonly REQUEST_WINDOW = 60000; // 1 minute

  constructor(maxConcurrent = 2, baseDelayMs = 150) {
    this.maxConcurrent = maxConcurrent;
    this.baseDelayMs = baseDelayMs;
    this.currentDelayMs = baseDelayMs;
  }

  get activeRequests() { return this.activeCount; }
  get queueLength() { return this.queue.length; }
  get currentDelay() { return this.currentDelayMs; }

  getRequestsLastMinute(): number {
    const cutoff = Date.now() - this.REQUEST_WINDOW;
    this.requestLog = this.requestLog.filter(t => t > cutoff);
    return this.requestLog.length;
  }

  /** Add a request to the stagger queue */
  enqueue<T>(id: string, fn: () => Promise<T>, priority = 5): Promise<T> {
    const existing = this.pending.get(id);
    if (existing) return existing as Promise<T>;

    // Refuse additional work at saturation instead of retaining an unbounded
    // queue or growing a chain of duplicate .resolve callbacks in memory.
    if (this.queue.length >= this.MAX_QUEUE_LENGTH) {
      return Promise.reject(new Error('Thermal request queue saturated'));
    }

    const promise = new Promise<T>((resolve, reject) => {
      this.queue.push({
        id, fn, resolve, reject,
        priority: Number.isFinite(priority) ? priority : 5,
        timestamp: Date.now(),
      });
      this.queue.sort((a, b) => a.priority - b.priority);
      void this.process();
    });
    this.pending.set(id, promise);
    // No unhandled rejection from the cleanup observer; identity guards
    // against a replacement with the same key after cancellation.
    const release = () => { if (this.pending.get(id) === promise) this.pending.delete(id); };
    void promise.then(release, release);
    return promise;
  }

  /** Set thermal-aware delay multiplier */
  setThermalMultiplier(level: ThermalLevel) {
    switch (level) {
      case 'cool': this.currentDelayMs = this.baseDelayMs; break;
      case 'warm': this.currentDelayMs = this.baseDelayMs * 1.5; break;
      case 'hot': this.currentDelayMs = this.baseDelayMs * 3; break;
      case 'critical': this.currentDelayMs = this.baseDelayMs * 6; break;
    }
  }

  setMaxConcurrent(n: number) {
    if (!Number.isFinite(n)) return;
    this.maxConcurrent = Math.max(1, Math.min(4, Math.trunc(n)));
  }

  private async process() {
    if (this.processing) return;
    this.processing = true;
    try {
      while (this.queue.length > 0) {
        if (this.activeCount >= this.maxConcurrent) {
          await new Promise<void>(resolve => setTimeout(resolve, 50));
          continue;
        }

        const item = this.queue.shift();
        if (!item) break;
        const generation = this.generation;
        if (this.currentDelayMs > 0) {
          await new Promise<void>(resolve => setTimeout(resolve, this.currentDelayMs));
        }

        // A cooldown may have flushed the queue during the stagger delay.
        // Never launch a request whose caller was already cancelled.
        if (generation !== this.generation) {
          item.reject(new Error('Queue flushed'));
          continue;
        }

        this.activeCount++;
        this.requestLog.push(Date.now());
        if (this.requestLog.length > 512) this.getRequestsLastMinute();
        if (this.requestLog.length > 512) this.requestLog.splice(0, this.requestLog.length - 512);
        // Schedule user-supplied callbacks on the promise chain: even a
        // synchronous throw must settle its caller and release the slot.
        void Promise.resolve().then(item.fn).then(item.resolve, item.reject).finally(() => {
          this.activeCount--;
        });
      }
    } finally {
      this.processing = false;
      if (this.queue.length > 0) void this.process();
    }
  }

  /** Flush all queued requests (cancel them) */
  flush() {
    this.generation++;
    for (const item of this.queue) {
      item.reject(new Error('Queue flushed'));
    }
    this.queue = [];
  }
}

// ═══════════════ DEDUPLICATION CACHE ═══════════════

interface CacheEntry {
  data: any;
  timestamp: number;
  ttl: number;
}

class DeduplicationCache {
  private cache = new Map<string, CacheEntry>();
  private maxEntries: number;

  constructor(maxEntries = 100) {
    this.maxEntries = maxEntries;
  }

  get size() { return this.cache.size; }

  get(key: string): any | null {
    const entry = this.cache.get(key);
    if (!entry) return null;
    if (Date.now() - entry.timestamp > entry.ttl) {
      this.cache.delete(key);
      return null;
    }
    return entry.data;
  }

  set(key: string, data: any, ttlMs = 5000) {
    // Evict oldest if at capacity
    if (this.cache.size >= this.maxEntries) {
      const oldestKey = this.cache.keys().next().value;
      if (oldestKey) this.cache.delete(oldestKey);
    }
    this.cache.set(key, { data, timestamp: Date.now(), ttl: ttlMs });
  }

  /** Purge expired entries */
  purge(): number {
    const now = Date.now();
    let purged = 0;
    for (const [key, entry] of this.cache) {
      if (now - entry.timestamp > entry.ttl) {
        this.cache.delete(key);
        purged++;
      }
    }
    return purged;
  }

  /** Full clear */
  clear() {
    this.cache.clear();
  }
}

// ═══════════════ ACTIVITY TRACKER ═══════════════

class ActivityTracker {
  private events: number[] = [];
  private sessionStart: number;
  private readonly BURST_WINDOW = 10000;  // 10 seconds
  private readonly BURST_THRESHOLD = 15;  // actions in window = burst
  private readonly SUSTAINED_WINDOW = 300000; // 5 minutes
  private readonly SUSTAINED_THRESHOLD = 100; // actions in 5 min = sustained heavy

  constructor() {
    this.sessionStart = Date.now();
  }

  record() {
    this.events.push(Date.now());
    // Bound memory even if a high-frequency input produces thousands of
    // events inside the same ten-minute window.
    if (this.events.length > 512) {
      const cutoff = Date.now() - 600000;
      this.events = this.events.filter(t => t > cutoff).slice(-2048);
    }
  }

  get sessionMinutes(): number {
    return Math.floor((Date.now() - this.sessionStart) / 60000);
  }

  get isBurst(): boolean {
    const cutoff = Date.now() - this.BURST_WINDOW;
    return this.events.filter(t => t > cutoff).length >= this.BURST_THRESHOLD;
  }

  get isSustainedHeavy(): boolean {
    const cutoff = Date.now() - this.SUSTAINED_WINDOW;
    return this.events.filter(t => t > cutoff).length >= this.SUSTAINED_THRESHOLD;
  }

  get recentActivityRate(): number {
    const cutoff = Date.now() - 60000; // last minute
    return this.events.filter(t => t > cutoff).length;
  }

  /** Calculate thermal contribution from activity (0-40) */
  get heatContribution(): number {
    let heat = 0;
    if (this.isBurst) heat += 20;
    if (this.isSustainedHeavy) heat += 15;
    // Session length contributes (marathon penalty)
    const hours = this.sessionMinutes / 60;
    if (hours > 2) heat += Math.min(hours * 2, 10);
    return Math.min(heat, 40);
  }
}

// ═══════════════ MAIN THERMAL GUARD ═══════════════

export class ThermalGuard {
  readonly queue: StaggerQueue;
  readonly cache: DeduplicationCache;
  readonly activity: ActivityTracker;

  private _thermalLevel: ThermalLevel = 'cool';
  private _batteryLevel: number = 1;
  private _isCharging: boolean = false;
  private _appInBackground: boolean = false;
  private _purgeTimer: ReturnType<typeof setInterval> | null = null;
  private _listeners: Set<(state: ThermalState) => void> = new Set();

  constructor() {
    this.queue = new StaggerQueue(2, 150);
    this.cache = new DeduplicationCache(100);
    this.activity = new ActivityTracker();

    // Periodic cache purge every 30s
    this._purgeTimer = setInterval(() => {
      this.cache.purge();
      this._recalculate();
    }, 30000);
  }

  /** Subscribe to thermal state changes */
  subscribe(listener: (state: ThermalState) => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  private _notify() {
    const state = this.getState();
    for (const listener of this._listeners) {
      listener(state);
    }
  }

  /** Update battery info from usePowerAwareness */
  setBattery(level: number, charging: boolean) {
    // Expo may report -1 for an unknown battery state. Treat it as missing,
    // not a 0% battery that would force perpetual thermal throttling.
    if (!Number.isFinite(level) || level < 0 || level > 1) return;
    this._batteryLevel = level;
    this._isCharging = charging;
    this._recalculate();
  }

  /** Update app foreground/background */
  setAppBackground(inBackground: boolean) {
    this._appInBackground = inBackground;
    if (inBackground) {
      // Immediately throttle when backgrounded
      this.queue.setMaxConcurrent(1);
      this.queue.setThermalMultiplier('critical');
    } else {
      this._recalculate();
    }
  }

  /** Record user activity (call on interactions, navigations, etc.) */
  recordActivity() {
    this.activity.record();
  }

  /** Staggered fetch with dedup + thermal awareness */
  async fetch<T>(
    key: string,
    fetcher: () => Promise<T>,
    options?: { priority?: number; cacheTtlMs?: number; skipCache?: boolean }
  ): Promise<T> {
    const { priority = 5, cacheTtlMs = 5000, skipCache = false } = options || {};

    // Check dedup cache first
    if (!skipCache) {
      const cached = this.cache.get(key);
      if (cached !== null) return cached as T;
    }

    try {
      const result = await this.queue.enqueue(key, fetcher, priority);
      if (Number.isFinite(cacheTtlMs) && cacheTtlMs > 0) {
        this.cache.set(key, result, Math.min(cacheTtlMs, 60_000));
      }
      return result;
    } finally {
      // Failed/cancelled requests still change resource pressure.
      this._recalculate();
    }
  }

  /** Get current thermal state */
  getState(): ThermalState {
    const score = this._calculateScore();
    return {
      level: this._thermalLevel,
      score,
      activeRequests: this.queue.activeRequests,
      totalRequestsLastMinute: this.queue.getRequestsLastMinute(),
      stutterDelayMs: this.queue.currentDelay,
      isThrottled: this._thermalLevel === 'hot' || this._thermalLevel === 'critical',
      lastActivityBurst: this.activity.isBurst ? Date.now() : 0,
      sessionMinutes: this.activity.sessionMinutes,
      memoryPressure: this._estimateMemoryPressure(),
      cacheEntries: this.cache.size,
    };
  }

  private _calculateScore(): number {
    let score = 0;

    // Activity heat (0-40)
    score += this.activity.heatContribution;

    // Battery penalty (0-25)
    if (!this._isCharging) {
      if (this._batteryLevel <= 0.15) score += 25;
      else if (this._batteryLevel <= 0.30) score += 15;
      else if (this._batteryLevel <= 0.50) score += 8;
    }

    // Request pressure (0-20)
    const reqsPerMin = this.queue.getRequestsLastMinute();
    if (reqsPerMin > 30) score += 20;
    else if (reqsPerMin > 15) score += 10;
    else if (reqsPerMin > 8) score += 5;

    // Queue depth (0-15)
    if (this.queue.queueLength > 10) score += 15;
    else if (this.queue.queueLength > 5) score += 8;

    // Background penalty
    if (this._appInBackground) score += 10;

    return Math.min(score, 100);
  }

  private _recalculate() {
    const score = this._calculateScore();
    let level: ThermalLevel;

    if (score >= 75) level = 'critical';
    else if (score >= 50) level = 'hot';
    else if (score >= 25) level = 'warm';
    else level = 'cool';

    const changed = level !== this._thermalLevel;
    this._thermalLevel = level;

    // Adjust queue parameters
    this.queue.setThermalMultiplier(this._appInBackground ? 'critical' : level);

    if (this._appInBackground || level === 'critical') {
      this.queue.setMaxConcurrent(1);
    } else if (level === 'hot') {
      this.queue.setMaxConcurrent(1);
    } else if (level === 'warm') {
      this.queue.setMaxConcurrent(2);
    } else {
      this.queue.setMaxConcurrent(3);
    }

    if (changed) {
      this._notify();
    }
  }

  private _estimateMemoryPressure(): 'low' | 'medium' | 'high' {
    const cacheSize = this.cache.size;
    const queueSize = this.queue.queueLength;
    if (cacheSize > 80 || queueSize > 15) return 'high';
    if (cacheSize > 40 || queueSize > 8) return 'medium';
    return 'low';
  }

  /** Force cooldown - purge caches, flush queue, reset throttle */
  forceCooldown() {
    this.cache.clear();
    this.queue.flush();
    this._thermalLevel = 'cool';
    this.queue.setThermalMultiplier(this._appInBackground ? 'critical' : 'cool');
    this.queue.setMaxConcurrent(this._appInBackground ? 1 : 3);
    this._notify();
  }

  /** Cleanup */
  destroy() {
    if (this._purgeTimer) clearInterval(this._purgeTimer);
    this.queue.flush();
    this.cache.clear();
    this._listeners.clear();
  }
}

// ═══════════════ SINGLETON ═══════════════

let _instance: ThermalGuard | null = null;

export function getThermalGuard(): ThermalGuard {
  if (!_instance) {
    _instance = new ThermalGuard();
  }
  return _instance;
}

// ═══════════════ HELPERS ═══════════════

/** Stagger an array of async functions with delays between each */
export async function staggeredExecute<T>(
  tasks: Array<{ id: string; fn: () => Promise<T>; priority?: number }>,
  delayBetweenMs = 200
): Promise<T[]> {
  const guard = getThermalGuard();
  const results: T[] = [];

  for (const task of tasks) {
    const result = await guard.fetch(task.id, task.fn, {
      priority: task.priority ?? 5,
      cacheTtlMs: 10000,
    });
    results.push(result);
    // Additional stutter between tasks
    if (delayBetweenMs > 0) {
      await new Promise(r => setTimeout(r, delayBetweenMs));
    }
  }

  return results;
}

/** Get a thermal-aware animation duration */
export function thermalAnimationDuration(baseDuration: number): number {
  const guard = getThermalGuard();
  const state = guard.getState();
  switch (state.level) {
    case 'critical': return 0;       // No animations
    case 'hot': return baseDuration * 0.3;
    case 'warm': return baseDuration * 0.7;
    default: return baseDuration;
  }
}
