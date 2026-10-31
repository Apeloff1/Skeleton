/** Private creator/buyer assertions come from the existing authenticated owner. */
import { getAuthEpoch, resolveStorageTenantIdentity } from '../auth/gameforgeAuth';

export function creatorRequestCurrent(epoch: number, signal?: AbortSignal): boolean {
  return !signal?.aborted && epoch === getAuthEpoch();
}

export async function resolveCreatorPrincipal(
  signal?: AbortSignal, expectedEpoch = getAuthEpoch(),
): Promise<string> {
  if (!creatorRequestCurrent(expectedEpoch, signal)) throw new Error('Creator account observation cancelled.');
  const identity = await resolveStorageTenantIdentity();
  if (!creatorRequestCurrent(expectedEpoch, signal)) throw new Error('Creator account observation cancelled.');
  const principal = identity.principalId;
  if (typeof principal !== 'string' || !principal.trim() || principal === 'anonymous') {
    throw new Error('Sign in to open your creator account.');
  }
  return principal;
}
