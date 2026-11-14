/** Explicit, bounded selection; the server independently rechecks every source. */
import type { CapturedSource } from './crawlerClient';

const HASH = /^[a-f0-9]{64}$/;
export const DRAGON_BUNDLE_MAX_SOURCES = 8;

export function eligibleForEvidenceBundle(source: CapturedSource): boolean {
  return HASH.test(source.source_id)
    && HASH.test(source.content_digest)
    && source.use_policy?.enabled === true
    && Number.isSafeInteger(source.use_policy?.version)
    && (source.use_policy?.version ?? -1) >= 0
    && source.freshness?.usable === true
    && source.freshness?.state === 'current'
    && source.freshness?.remote_freshness_verified === false;
}

export function toggleEvidenceBundleSelection(
  selected: readonly string[], source: CapturedSource,
): string[] {
  if (selected.includes(source.source_id)) {
    return selected.filter(id => id !== source.source_id);
  }
  if (!eligibleForEvidenceBundle(source))
    throw new Error('This source is not eligible for current authorized export.');
  if (selected.length >= DRAGON_BUNDLE_MAX_SOURCES)
    throw new Error('Select no more than eight approved sources per bundle.');
  return [...selected, source.source_id];
}
