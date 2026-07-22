/**
 * Power & Hardware Awareness Hook v11.4
 * Monitors battery, memory, and adjusts app behavior accordingly
 */

import { useState, useEffect, useCallback } from 'react';
import { AppState, AppStateStatus, Platform } from 'react-native';
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

export function usePowerAwareness() {
  const [state, setState] = useState<PowerState>(DEFAULT_STATE);

  const updatePerformanceMode = useCallback((level: number, charging: boolean) => {
    let mode: PerformanceMode = 'balanced';
    let reduceAnimations = false;
    let reducePolling = false;
    let isLowPower = false;

    if (charging) {
      mode = 'high';
    } else if (level <= 0.15) {
      mode = 'powersaver';
      reduceAnimations = true;
      reducePolling = true;
      isLowPower = true;
    } else if (level <= 0.30) {
      mode = 'powersaver';
      reduceAnimations = true;
      isLowPower = true;
    } else if (level <= 0.50) {
      mode = 'balanced';
    } else {
      mode = 'high';
    }

    setState(prev => ({
      ...prev,
      batteryLevel: level,
      isCharging: charging,
      isLowPower,
      performanceMode: mode,
      shouldReduceAnimations: reduceAnimations,
      shouldReducePolling: reducePolling,
    }));
  }, []);

  useEffect(() => {
    let batterySubscription: Battery.Subscription | null = null;
    let chargingSubscription: Battery.Subscription | null = null;

    const initBattery = async () => {
      try {
        const level = await Battery.getBatteryLevelAsync();
        const charging = await Battery.getBatteryStateAsync();
        const isCharging = charging === Battery.BatteryState.CHARGING || charging === Battery.BatteryState.FULL;
        updatePerformanceMode(level, isCharging);

        batterySubscription = Battery.addBatteryLevelListener(({ batteryLevel }) => {
          setState(prev => {
            updatePerformanceMode(batteryLevel, prev.isCharging);
            return prev;
          });
        });

        chargingSubscription = Battery.addBatteryStateListener(({ batteryState }) => {
          const charging = batteryState === Battery.BatteryState.CHARGING || batteryState === Battery.BatteryState.FULL;
          setState(prev => {
            updatePerformanceMode(prev.batteryLevel, charging);
            return prev;
          });
        });
      } catch (e) {
        // Battery API not available - use defaults
        console.log('Battery API not available');
      }
    };

    initBattery();

    // App state listener
    const appStateSubscription = AppState.addEventListener('change', (nextState) => {
      setState(prev => ({ ...prev, appState: nextState }));
    });

    return () => {
      batterySubscription?.remove();
      chargingSubscription?.remove();
      appStateSubscription.remove();
    };
  }, [updatePerformanceMode]);

  // Helper functions
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

  return {
    ...state,
    getAnimationDuration,
    getPollingInterval,
  };
}
