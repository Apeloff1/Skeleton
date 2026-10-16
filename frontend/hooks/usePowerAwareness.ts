/**
 * Device power policy for long-running sessions.
 * All battery events flow through one immutable state update. Subscriptions
 * are removed on unmount, including when asynchronous initialization races it.
 */
import { useState, useEffect, useCallback } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import * as Battery from 'expo-battery';

export type PerformanceMode = 'high' | 'balanced' | 'powersaver';

interface PowerState {
  batteryLevel: number;
  isCharging: boolean;
  isLowPower: boolean;
  performanceMode: PerformanceMode;
  shouldReduceAnimations: boolean;
  shouldReducePolling: boolean;
  appState: AppStateStatus;
}

const DEFAULT_STATE: PowerState = {
  batteryLevel: 1,
  isCharging: false,
  isLowPower: false,
  performanceMode: 'balanced',
  shouldReduceAnimations: false,
  shouldReducePolling: false,
  appState: 'active',
};

function validBatteryLevel(level: number): boolean {
  // Expo reports -1 when battery level is unknown; never mistake it for 0%.
  return Number.isFinite(level) && level >= 0 && level <= 1;
}

function isBatteryCharging(state: Battery.BatteryState): boolean {
  return state === Battery.BatteryState.CHARGING || state === Battery.BatteryState.FULL;
}

export function usePowerAwareness() {
  const [state, setState] = useState<PowerState>(DEFAULT_STATE);

  const updatePerformanceMode = useCallback((level: number, charging: boolean) => {
    if (!validBatteryLevel(level)) return;
    const isLowPower = !charging && level <= 0.30;
    const performanceMode: PerformanceMode = charging || level > 0.50
      ? 'high'
      : isLowPower ? 'powersaver' : 'balanced';
    const shouldReduceAnimations = isLowPower;
    const shouldReducePolling = !charging && level <= 0.15;

    setState(prev => {
      if (prev.batteryLevel === level && prev.isCharging === charging &&
          prev.isLowPower === isLowPower && prev.performanceMode === performanceMode &&
          prev.shouldReduceAnimations === shouldReduceAnimations &&
          prev.shouldReducePolling === shouldReducePolling) return prev;
      return {
        ...prev, batteryLevel: level, isCharging: charging, isLowPower,
        performanceMode, shouldReduceAnimations, shouldReducePolling,
      };
    });
  }, []);

  useEffect(() => {
    let disposed = false;
    let batterySubscription: Battery.Subscription | null = null;
    let chargingSubscription: Battery.Subscription | null = null;
    const reading = { level: DEFAULT_STATE.batteryLevel, charging: DEFAULT_STATE.isCharging };

    const initBattery = async () => {
      try {
        const [level, chargeState] = await Promise.all([
          Battery.getBatteryLevelAsync(),
          Battery.getBatteryStateAsync(),
        ]);
        if (disposed) return;
        if (validBatteryLevel(level)) reading.level = level;
        reading.charging = isBatteryCharging(chargeState);
        updatePerformanceMode(reading.level, reading.charging);

        // A previously unmounted hook must never attach native listeners.
        if (disposed) return;
        batterySubscription = Battery.addBatteryLevelListener(({ batteryLevel }) => {
          if (disposed || !validBatteryLevel(batteryLevel)) return;
          reading.level = batteryLevel;
          updatePerformanceMode(reading.level, reading.charging);
        });
        chargingSubscription = Battery.addBatteryStateListener(({ batteryState }) => {
          if (disposed) return;
          reading.charging = isBatteryCharging(batteryState);
          updatePerformanceMode(reading.level, reading.charging);
        });
      } catch {
        // Battery APIs are optional (web/simulators). Keep safe defaults and
        // tear down a partially established listener, if any.
        batterySubscription?.remove();
        chargingSubscription?.remove();
        batterySubscription = null;
        chargingSubscription = null;
      }
    };

    void initBattery();
    const appStateSubscription = AppState.addEventListener('change', nextState => {
      if (!disposed) {
        setState(prev => prev.appState === nextState ? prev : { ...prev, appState: nextState });
      }
    });

    return () => {
      disposed = true;
      batterySubscription?.remove();
      chargingSubscription?.remove();
      appStateSubscription.remove();
    };
  }, [updatePerformanceMode]);

  const getAnimationDuration = useCallback((baseDuration: number) => {
    if (state.shouldReduceAnimations) return 0;
    if (state.performanceMode === 'powersaver') return baseDuration * 0.5;
    return baseDuration;
  }, [state.shouldReduceAnimations, state.performanceMode]);

  const getPollingInterval = useCallback((baseInterval: number) => {
    if (state.shouldReducePolling) return baseInterval * 3;
    if (state.performanceMode === 'powersaver') return baseInterval * 2;
    return baseInterval;
  }, [state.shouldReducePolling, state.performanceMode]);

  return { ...state, getAnimationDuration, getPollingInterval };
}
