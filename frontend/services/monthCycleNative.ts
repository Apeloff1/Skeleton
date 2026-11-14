/**
 * React Native adapter for durable work-cycle metadata. The same injected
 * AsyncStorage identity participates in the ledger's physical write fence.
 * This stores only opaque job identifiers and observation receipts: never
 * prompts, checkpoints, tokens, generated content, or credentials.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppState } from 'react-native';
import { MonthCycleRecovery } from './monthCycleRecovery';
import {
  MonthCycleForegroundDriver, type MonthCycleForegroundOptions,
} from './monthCycleForeground';
import { MonthCycleLedger } from './monthCycleLedger';

export function createNativeMonthCycleLedger(namespace: string): MonthCycleLedger {
  return new MonthCycleLedger(AsyncStorage, namespace);
}

/**
 * Construct an opt-in foreground observation host after the authenticated
 * account namespace is resolved. The owner must call `start()` and hold its
 * disposer. This never installs a daemon or OS background task.
 */
export function createNativeMonthCycleForegroundDriver(
  recovery: MonthCycleRecovery,
  options: MonthCycleForegroundOptions = {},
): MonthCycleForegroundDriver {
  return new MonthCycleForegroundDriver({
    currentState: AppState.currentState,
    addEventListener: (_kind, listener) =>
      AppState.addEventListener('change', state => listener(state)),
  }, recovery, options);
}
