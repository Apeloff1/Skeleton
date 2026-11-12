/**
 * Source-only Dragon research continuity witness.
 *
 * This is a client-side stale-result guard, NOT a network/rights credential.
 * The canonical API has already verified the Atlas digest, source policy,
 * release holds and authenticated Mongo re-read before returning a report.
 * A snapshot witness binds the UI receipt to the observed owned session
 * revision. Sharing must re-read that session over the existing auth client.
 */
import type { CrawlAtlasReport, CrawlSession } from '../../product/crawlerClient';

export type PilotSnapshotWitness = Readonly<{
  sessionId: string;
  sessionVersion: number;
  atlasDigest: string;
  snapshotDigest: string;
  sourcePolicyDigest: string;
  runSequence: number;
  qualificationDigest: string;
}>;

const DIGEST = /^[a-f0-9]{64}$/;

/** Capture a digest-only witness from a *verified* response and local revision. */
export function bindPilotSnapshot(
  session: CrawlSession, report: CrawlAtlasReport,
): PilotSnapshotWitness {
  const pilot = report?.pilot_qualification;
  if (!session || !report || !pilot || session.consent_current !== true ||
    !Number.isSafeInteger(session.version) || session.version < 1 ||
    session.status === 'cancelled' || report.session_id !== session.session_id ||
    pilot.atlas_digest !== report.atlas_digest ||
    pilot.snapshot_digest !== report.snapshot_digest ||
    pilot.source_policy_digest !== report.source_policy?.digest ||
    pilot.run_sequence !== report.run_sequence ||
    pilot.read_only !== true || pilot.source_only !== true ||
    pilot.recheck_mongo_authority_before_any_followup !== true ||
    pilot.release_authorized !== false ||
    pilot.publication_authorized !== false || pilot.training_authorized !== false ||
    ![pilot.atlas_digest, pilot.snapshot_digest, pilot.source_policy_digest,
      pilot.qualification_digest].every(value => typeof value === 'string' && DIGEST.test(value)) ||
    !Number.isSafeInteger(pilot.run_sequence) || pilot.run_sequence < 0) {
    throw new Error('Research evidence cannot be bound to the current owned session.');
  }
  return Object.freeze({
    sessionId: session.session_id,
    sessionVersion: session.version,
    atlasDigest: pilot.atlas_digest,
    snapshotDigest: pilot.snapshot_digest,
    sourcePolicyDigest: pilot.source_policy_digest,
    runSequence: pilot.run_sequence,
    qualificationDigest: pilot.qualification_digest,
  });
}

/**
 * Insist on a fresh canonical session read before the user explicitly shares
 * metadata. Never treat this as live policy reauthorization; the receipt is an
 * as-of snapshot. Any actual source use requires an independent policy recheck.
 */
export function requireCurrentPilotSnapshot(
  witness: PilotSnapshotWitness | null,
  displayed: CrawlSession | null,
  latest: CrawlSession,
  report: CrawlAtlasReport | null,
): void {
  if (!witness || !displayed || !latest || !report || !report.pilot_qualification ||
    !displayed.consent_current || !latest.consent_current ||
    displayed.session_id !== witness.sessionId ||
    latest.session_id !== witness.sessionId ||
    displayed.version !== witness.sessionVersion ||
    latest.version !== witness.sessionVersion ||
    latest.status === 'cancelled' ||
    report.session_id !== witness.sessionId ||
    report.atlas_digest !== witness.atlasDigest ||
    report.snapshot_digest !== witness.snapshotDigest ||
    report.source_policy?.digest !== witness.sourcePolicyDigest ||
    report.run_sequence !== witness.runSequence ||
    report.pilot_qualification.qualification_digest !== witness.qualificationDigest ||
    report.pilot_qualification.release_authorized !== false) {
    throw new Error('The receipt is no longer bound to the current session. Reinspect Atlas before sharing.');
  }
}
