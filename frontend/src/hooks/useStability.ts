/**
 * Recovery state for transient UI failures.
 * A single recovery may run per mounted hook; repeated failures are bounded
 * without depending on a stale React render closure.
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { Alert } from 'react-native';
import NetInfo, { type NetInfoState } from '@react-native-community/netinfo';
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
const RECOVERY_TTL_MS = 60 * 60 * 1000;

function normalizeError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

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
  const recoveryAttemptsRef = useRef(0);
  const recoveryInFlightRef = useRef(false);
  const alertIssuedRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    const unsubscribe = NetInfo.addEventListener((netState: NetInfoState) => {
      if (!mountedRef.current) return;
      setState(prev => ({
        ...prev,
        isOnline: netState.isConnected ?? true,
        connectionType: netState.type,
      }));
    });
    return () => {
      mountedRef.current = false;
      unsubscribe();
      if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current);
      errorTimeoutRef.current = null;
    };
  }, []);

  const saveRecoveryState = useCallback(async (data: unknown) => {
    try {
      await AsyncStorage.setItem(RECOVERY_KEY, JSON.stringify({
        timestamp: Date.now(),
        data,
      }));
    } catch (error) {
      console.warn('Failed to save recovery state:', error);
    }
  }, []);

  const loadRecoveryState = useCallback(async () => {
    try {
      const saved = await AsyncStorage.getItem(RECOVERY_KEY);
      if (saved) {
        const receipt: unknown = JSON.parse(saved);
        if (receipt && typeof receipt === 'object') {
          const { timestamp, data } = receipt as { timestamp?: unknown; data?: unknown };
          const now = Date.now();
          if (typeof timestamp === 'number' && Number.isFinite(timestamp) &&
              timestamp >= 0 && timestamp <= now && now - timestamp < RECOVERY_TTL_MS) {
            return data ?? null;
          }
        }
      }
    } catch (error) {
      console.warn('Failed to load recovery state:', error);
    }
    return null;
  }, []);

  const clearRecoveryState = useCallback(async () => {
    try {
      await AsyncStorage.removeItem(RECOVERY_KEY);
    } catch (error) {
      console.warn('Failed to clear recovery state:', error);
    }
  }, []);

  const handleError = useCallback((incoming: unknown, context?: string) => {
    const error = normalizeError(incoming);
    console.error(`[Stability] Error in ${context || 'unknown'}:`, error);
    if (!mountedRef.current) return;

    recoveryAttemptsRef.current = Math.min(MAX_RECOVERY_ATTEMPTS, recoveryAttemptsRef.current + 1);
    const attempts = recoveryAttemptsRef.current;
    setState(prev => ({
      ...prev,
      hasError: true,
      lastError: error,
      recoveryAttempts: attempts,
    }));

    if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current);
    errorTimeoutRef.current = setTimeout(() => {
      errorTimeoutRef.current = null;
      if (mountedRef.current) setState(prev => ({ ...prev, hasError: false }));
    }, 5000);

    if (attempts >= MAX_RECOVERY_ATTEMPTS && !alertIssuedRef.current) {
      alertIssuedRef.current = true;
      Alert.alert(
        'Something went wrong',
        'The app encountered an issue. Some features may be limited.',
        [{ text: 'OK' }],
      );
    }
  }, []);

  const attemptRecovery = useCallback(async (recoveryFn: () => Promise<void>) => {
    if (!mountedRef.current || recoveryInFlightRef.current ||
        recoveryAttemptsRef.current >= MAX_RECOVERY_ATTEMPTS) {
      return false;
    }
    recoveryInFlightRef.current = true;
    setState(prev => ({ ...prev, isRecovering: true }));

    try {
      await recoveryFn();
      if (!mountedRef.current) return false;
      recoveryAttemptsRef.current = 0;
      alertIssuedRef.current = false;
      if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current);
      errorTimeoutRef.current = null;
      setState(prev => ({
        ...prev, hasError: false, lastError: null,
        recoveryAttempts: 0, isRecovering: false,
      }));
      return true;
    } catch (error) {
      if (mountedRef.current) {
        recoveryAttemptsRef.current = Math.min(MAX_RECOVERY_ATTEMPTS, recoveryAttemptsRef.current + 1);
        setState(prev => ({
          ...prev, hasError: true, lastError: normalizeError(error),
          isRecovering: false, recoveryAttempts: recoveryAttemptsRef.current,
        }));
      }
      return false;
    } finally {
      recoveryInFlightRef.current = false;
    }
  }, []);

  const resetError = useCallback(() => {
    if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current);
    errorTimeoutRef.current = null;
    recoveryAttemptsRef.current = 0;
    alertIssuedRef.current = false;
    if (mountedRef.current) {
      setState(prev => ({
        ...prev, hasError: false, lastError: null,
        recoveryAttempts: 0, isRecovering: false,
      }));
    }
  }, []);

  const safeAsync = useCallback(async <T,>(
    operation: () => Promise<T>,
    fallback: T,
    context?: string,
  ): Promise<T> => {
    try {
      return await operation();
    } catch (error) {
      handleError(error, context);
      return fallback;
    }
  }, [handleError]);

  return {
    ...state, handleError, attemptRecovery, resetError, safeAsync,
    saveRecoveryState, loadRecoveryState, clearRecoveryState,
  };
}
