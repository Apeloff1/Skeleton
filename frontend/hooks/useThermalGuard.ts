/**
 * ╔══════════════════════════════════════════════════════════════════════════╗
 * ║    useThermalGuard — React Hook for Device Heat Management              ║
 * ║                                                                          ║
 * ║    Integrates battery awareness, activity tracking, stagger queue,      ║
 * ║    stutterstep delays, and auto-throttle into a single hook              ║
 * ║                                                                          ║
 * ║    Usage:                                                                ║
 * ║      const { thermalState, staggerFetch, isThrottled } = useThermalGuard(); ║
 * ╚══════════════════════════════════════════════════════════════════════════╝
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { AppState, type AppStateStatus, Platform } from 'react-native';
import {
  getThermalGuard,
  ThermalGuard,
  ThermalState,
  ThermalLevel,
} from '../utils/thermalGuard';

export interface ThermalGuardHook {
  /** Current thermal state of the device guard */
  thermalState: ThermalState;
  /** Current thermal level: cool | warm | hot | critical */
  thermalLevel: ThermalLevel;
  /** Whether the app is being throttled */
  isThrottled: boolean;
  /** Current stutterstep delay in ms */
  stutterDelay: number;
  /** Session duration in minutes */
  sessionMinutes: number;
  /** Stagger-fetched request (dedup + queue + thermal aware) */
  staggerFetch: <T>(key: string, fetcher: () => Promise<T>, options?: {
    priority?: number;
    cacheTtlMs?: number;
    skipCache?: boolean;
  }) => Promise<T>;
  /** Record user activity (call on taps, navigations, etc.) */
  recordActivity: () => void;
  /** Force a system cooldown (purge caches, flush queues) */
  forceCooldown: () => void;
  /** Get thermal-adjusted animation duration */
  getAnimDuration: (base: number) => number;
  /** Whether a modal should render its content (thermal-aware lazy) */
  shouldRenderHeavy: boolean;
  /** The raw ThermalGuard instance */
  guard: ThermalGuard;
}

const DEFAULT_STATE: ThermalState = {
  level: 'cool',
  score: 0,
  activeRequests: 0,
  totalRequestsLastMinute: 0,
  stutterDelayMs: 150,
  isThrottled: false,
  lastActivityBurst: 0,
  sessionMinutes: 0,
  memoryPressure: 'low',
  cacheEntries: 0,
};

export function useThermalGuard(): ThermalGuardHook {
  const guardRef = useRef<ThermalGuard>(getThermalGuard());
  const guard = guardRef.current;
  const [thermalState, setThermalState] = useState<ThermalState>(DEFAULT_STATE);

  // Subscribe to thermal state changes
  useEffect(() => {
    const unsubscribe = guard.subscribe(setThermalState);
    // Initial state
    setThermalState(guard.getState());
    return unsubscribe;
  }, [guard]);

  // Battery integration — native only; updates must preserve the last
  // observed level AND charging state rather than inventing either value.
  useEffect(() => {
    if (Platform.OS === 'web') return;

    let disposed = false;
    let battSub: { remove: () => void } | null = null;
    let chargeSub: { remove: () => void } | null = null;
    const reading = { level: 1, charging: false };

    const init = async () => {
      try {
        const BatteryModule = require('expo-battery');
        const [level, state] = await Promise.all([
          BatteryModule.getBatteryLevelAsync(),
          BatteryModule.getBatteryStateAsync(),
        ]);
        if (disposed) return;
        if (Number.isFinite(level) && level >= 0 && level <= 1) reading.level = level;
        reading.charging = state === BatteryModule.BatteryState.CHARGING ||
          state === BatteryModule.BatteryState.FULL;
        guard.setBattery(reading.level, reading.charging);

        if (disposed) return;
        battSub = BatteryModule.addBatteryLevelListener(({ batteryLevel }: { batteryLevel: number }) => {
          if (disposed || !Number.isFinite(batteryLevel) || batteryLevel < 0 || batteryLevel > 1) return;
          reading.level = batteryLevel;
          guard.setBattery(reading.level, reading.charging);
        });
        chargeSub = BatteryModule.addBatteryStateListener(({ batteryState }: { batteryState: number }) => {
          if (disposed) return;
          reading.charging = batteryState === BatteryModule.BatteryState.CHARGING ||
            batteryState === BatteryModule.BatteryState.FULL;
          guard.setBattery(reading.level, reading.charging);
        });
      } catch {
        battSub?.remove();
        chargeSub?.remove();
        battSub = null;
        chargeSub = null;
      }
    };

    void init();
    return () => {
      disposed = true;
      battSub?.remove();
      chargeSub?.remove();
    };
  }, [guard]);

  // Honor the actual initial background state, not only subsequent changes.
  useEffect(() => {
    guard.setAppBackground(AppState.currentState !== 'active');
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      guard.setAppBackground(next !== 'active');
    });
    return () => sub.remove();
  }, [guard]);

  // Periodic state refresh (every 10s)
  useEffect(() => {
    const interval = setInterval(() => {
      setThermalState(guard.getState());
    }, 10000);
    return () => clearInterval(interval);
  }, [guard]);

  // Stagger fetch
  const staggerFetch = useCallback(<T,>(
    key: string,
    fetcher: () => Promise<T>,
    options?: { priority?: number; cacheTtlMs?: number; skipCache?: boolean }
  ): Promise<T> => {
    guard.recordActivity();
    return guard.fetch(key, fetcher, options);
  }, [guard]);

  // Record activity
  const recordActivity = useCallback(() => {
    guard.recordActivity();
  }, [guard]);

  // Force cooldown
  const forceCooldown = useCallback(() => {
    guard.forceCooldown();
    setThermalState(guard.getState());
  }, [guard]);

  // Thermal-adjusted animation duration
  const getAnimDuration = useCallback((base: number): number => {
    switch (thermalState.level) {
      case 'critical': return 0;
      case 'hot': return Math.round(base * 0.3);
      case 'warm': return Math.round(base * 0.7);
      default: return base;
    }
  }, [thermalState.level]);

  // Whether heavy content should render
  const shouldRenderHeavy = thermalState.level !== 'critical';

  return {
    thermalState,
    thermalLevel: thermalState.level,
    isThrottled: thermalState.isThrottled,
    stutterDelay: thermalState.stutterDelayMs,
    sessionMinutes: thermalState.sessionMinutes,
    staggerFetch,
    recordActivity,
    forceCooldown,
    getAnimDuration,
    shouldRenderHeavy,
    guard,
  };
}

export default useThermalGuard;
