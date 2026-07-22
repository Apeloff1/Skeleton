/**
 * Stability Layer Hook v11.4
 * Error boundaries, crash recovery, and graceful degradation
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { Alert, Platform } from 'react-native';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';
import AsyncStorage from '@react-native-async-storage/async-storage';

interface StabilityState {
  isOnline: boolean;
  connectionType: string | null;
  hasError: boolean;
  lastError: Error | null;
  recoveryAttempts: number;
  isRecovering: boolean;
}

const RECOVERY_KEY = '@codedock_recovery_state';
const MAX_RECOVERY_ATTEMPTS = 3;

export function useStability() {
  const [state, setState] = useState<StabilityState>({
    isOnline: true,
    connectionType: null,
    hasError: false,
    lastError: null,
    recoveryAttempts: 0,
    isRecovering: false,
  });

  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Network monitoring
  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((netState: NetInfoState) => {
      setState(prev => ({
        ...prev,
        isOnline: netState.isConnected ?? true,
        connectionType: netState.type,
      }));
    });

    return () => unsubscribe();
  }, []);

  // Save state for recovery
  const saveRecoveryState = useCallback(async (data: any) => {
    try {
      await AsyncStorage.setItem(RECOVERY_KEY, JSON.stringify({
        timestamp: Date.now(),
        data,
      }));
    } catch (e) {
      console.warn('Failed to save recovery state:', e);
    }
  }, []);

  // Load recovery state
  const loadRecoveryState = useCallback(async () => {
    try {
      const saved = await AsyncStorage.getItem(RECOVERY_KEY);
      if (saved) {
        const { timestamp, data } = JSON.parse(saved);
        // Only use recovery data if less than 1 hour old
        if (Date.now() - timestamp < 3600000) {
          return data;
        }
      }
    } catch (e) {
      console.warn('Failed to load recovery state:', e);
    }
    return null;
  }, []);

  // Clear recovery state
  const clearRecoveryState = useCallback(async () => {
    try {
      await AsyncStorage.removeItem(RECOVERY_KEY);
    } catch (e) {
      console.warn('Failed to clear recovery state:', e);
    }
  }, []);

  // Handle errors gracefully
  const handleError = useCallback((error: Error, context?: string) => {
    console.error(`[Stability] Error in ${context || 'unknown'}:`, error);

    setState(prev => ({
      ...prev,
      hasError: true,
      lastError: error,
      recoveryAttempts: prev.recoveryAttempts + 1,
    }));

    // Auto-clear error after 5 seconds
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current);
    }
    errorTimeoutRef.current = setTimeout(() => {
      setState(prev => ({ ...prev, hasError: false }));
    }, 5000);

    // Show alert for critical errors after max attempts
    if (state.recoveryAttempts >= MAX_RECOVERY_ATTEMPTS - 1) {
      Alert.alert(
        'Something went wrong',
        'The app encountered an issue. Some features may be limited.',
        [{ text: 'OK' }]
      );
    }
  }, [state.recoveryAttempts]);

  // Attempt recovery
  const attemptRecovery = useCallback(async (recoveryFn: () => Promise<void>) => {
    if (state.recoveryAttempts >= MAX_RECOVERY_ATTEMPTS) {
      console.warn('[Stability] Max recovery attempts reached');
      return false;
    }

    setState(prev => ({ ...prev, isRecovering: true }));

    try {
      await recoveryFn();
      setState(prev => ({
        ...prev,
        hasError: false,
        lastError: null,
        isRecovering: false,
      }));
      return true;
    } catch (e) {
      setState(prev => ({
        ...prev,
        isRecovering: false,
        recoveryAttempts: prev.recoveryAttempts + 1,
      }));
      return false;
    }
  }, [state.recoveryAttempts]);

  // Reset error state
  const resetError = useCallback(() => {
    setState(prev => ({
      ...prev,
      hasError: false,
      lastError: null,
      recoveryAttempts: 0,
    }));
  }, []);

  // Wrap async operations for safety
  const safeAsync = useCallback(async <T,>(
    operation: () => Promise<T>,
    fallback: T,
    context?: string
  ): Promise<T> => {
    try {
      return await operation();
    } catch (e) {
      handleError(e as Error, context);
      return fallback;
    }
  }, [handleError]);

  return {
    ...state,
    handleError,
    attemptRecovery,
    resetError,
    safeAsync,
    saveRecoveryState,
    loadRecoveryState,
    clearRecoveryState,
  };
}
