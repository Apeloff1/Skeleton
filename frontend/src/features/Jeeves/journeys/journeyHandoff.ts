/** Use the existing one-shot Workbench handoff, bound to a verified chat account. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getAuthEpoch, getAuthToken } from '../../../auth/gameforgeAuth';
import type { WorkspaceController } from '../WorkspaceController';
import type { ChatHandoff } from '../workbench/types';
import { consumeHandoff } from '../workbench/handoff';
import { HASH, isObject } from './journeyDraft';
export function accountBoundHandoff(value: ChatHandoff, scopeKey: string): ChatHandoff & { account_scope_key: string } {
  if (!HASH.test(scopeKey)) throw new Error('The chat account scope is invalid.');
  return { ...value, account_scope_key: scopeKey };
}
export async function consumeAccountWorkbenchHandoff(scope: { key: string; token: string }, controller: WorkspaceController) {
  const epoch = getAuthEpoch();
  const current = () => { if (epoch !== getAuthEpoch() || scope.token !== getAuthToken()) throw new Error('The handoff account changed.'); };
  return consumeHandoff({
    async getItem(key) {
      current(); const raw = await AsyncStorage.getItem(key); current();
      if (raw === null) return null;
      try { const value: unknown = JSON.parse(raw); return isObject(value) && value.account_scope_key === scope.key ? raw : null; }
      catch { return null; }
    },
    async setItem() { throw new Error('The handoff consumer cannot write drafts.'); },
    async removeItem(key) { current(); await AsyncStorage.removeItem(key); current(); },
  }, controller);
}
