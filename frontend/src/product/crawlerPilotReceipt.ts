/** Canonical exact-byte verification for the pilot's metadata-only exit receipt.
 * Integrity hash binds the receipt body; it cannot grant authority or replace
 * the backend's authenticated Mongo/policy validation.
 */
import type { CrawlAtlasReport, CrawlPilotQualification } from './crawlerClient';

function canonical(value: unknown, depth: number): string {
  if (depth > 16) throw new Error('Pilot receipt nesting exceeds its finite bound.');
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value) && Number.isSafeInteger(value)) return JSON.stringify(value);
  if (Array.isArray(value)) {
    if (value.length > 128) throw new Error('Pilot receipt array exceeds its finite bound.');
    return '[' + value.map(item => canonical(item, depth + 1)).join(',') + ']';
  }
  if (!value || typeof value !== 'object') throw new Error('Pilot receipt contains an unsupported value.');
  const map = value as Record<string, unknown>;
  const keys = Object.keys(map).sort();
  if (keys.length > 128) throw new Error('Pilot receipt object exceeds its finite bound.');
  return '{' + keys.map(key => {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
      throw new Error('Pilot receipt has a forbidden metadata key.');
    }
    return JSON.stringify(key) + ':' + canonical(map[key], depth + 1);
  }).join(',') + '}';
}
export function canonicalPilotReceipt(body: unknown): string {
  const data = canonical(body, 0);
  if (data.length > 16384) throw new Error('Pilot receipt exceeds its finite byte envelope.');
  return data;
}

export function pilotReceiptBody(value: CrawlPilotQualification): Record<string, unknown> {
  const { qualification_digest: _excluded, ...body } = value;
  return body;
}

/** User-portable metadata-only copy; never includes captured page bodies or tokens. */
export function portablePilotReceipt(report: CrawlAtlasReport): string {
  const pilot = report.pilot_qualification;
  if (!pilot || pilot.release_authorized !== false || pilot.publication_authorized !== false
    || pilot.training_authorized !== false || pilot.read_only !== true
    || pilot.atlas_digest !== report.atlas_digest
    || pilot.snapshot_digest !== report.snapshot_digest) {
    throw new Error('A current verified pilot receipt is required before sharing.');
  }
  return JSON.stringify({
    schema: 'skeleton.dragon.user_pilot_receipt.v1',
    disclaimer: 'Advisory source-only metadata. No publication, training, network or release authority.',
    created_from: {
      atlas_digest: report.atlas_digest,
      source_snapshot_digest: report.snapshot_digest,
      policy_digest: report.source_policy.digest,
      run_sequence: report.run_sequence,
    },
    pilot_status: pilot.pilot_status,
    internal_checks: pilot.checks.map(item => ({
      code: item.code, status: item.status, next_action: item.next_action,
    })),
    external_release_checks: pilot.external_release_checks.map(item => ({
      code: item.code, status: 'not_qualified' as const,
    })),
    qualification_digest: pilot.qualification_digest,
    release_authorized: false,
    publication_authorized: false,
    training_authorized: false,
  }, null, 2);
}
