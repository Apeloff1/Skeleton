/**
 * React Native adapter for durable work-cycle metadata. The same injected
 * AsyncStorage identity participates in the ledger's physical write fence.
 * This stores only opaque job identifiers and observation receipts: never
 * prompts, checkpoints, tokens, generated content, or credentials.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { MonthCycleLedger } from './monthCycleLedger';

export function createNativeMonthCycleLedger(namespace: string): MonthCycleLedger {
  return new MonthCycleLedger(AsyncStorage, namespace);
}
