/**
 * Dragon authorized source evidence bundle — real user-exportable capture.
 *
 * This exports only data returned by the owner-scoped authoritative source
 * endpoints. Every source is freshly read, explicitly allowed for use and,
 * for body mode, independently authorized by the existing per-source export
 * endpoint. A second session read fences concurrent consent/revision changes.
 * No new crawler fetch, model invocation, rights inference or publication.
 */
import type { CapturedSource, CrawlSession, SourceExport } from './crawlerClient';

export class CrawlerBundleRefused extends Error {
  constructor(message: string) { super(message); this.name = 'CrawlerBundleRefused'; }
}
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const SHA = /^[a-f0-9]{64}$/;
const MAX_SOURCES = 8;
const MAX_BYTES = 1_800_000;
const MAX_BODY_BYTES = 225_000;
const encoder = new TextEncoder();

export type BundleOptions = {
  session: CrawlSession;
  sourceIds: readonly string[];
  includeBodies: boolean;
  signal?: AbortSignal;
  checkScope: () => boolean;
  getSession: (id: string, signal?: AbortSignal) => Promise<CrawlSession>;
  getSource: (session: string, source: string, signal?: AbortSignal) => Promise<CapturedSource>;
  exportSource: (session: string, source: string, format: 'json', signal?: AbortSignal) => Promise<SourceExport>;
  sha256: (text: string) => Promise<string>;
};

function refuse(message: string): never { throw new CrawlerBundleRefused(message); }
function gate(options: BundleOptions): void {
  if (options.signal?.aborted || !options.checkScope())
    refuse('The account or authorization session changed. The evidence bundle was not exported.');
}
function sameSession(first: CrawlSession, other: CrawlSession): boolean {
  return first.session_id === other.session_id
    && first.version === other.version
    && first.consent_current === true && other.consent_current === true
    && first.status === other.status && first.source_count === other.source_count
    && first.counters.requests === other.counters.requests
    && first.counters.documents === other.counters.documents
    && first.counters.bytes === other.counters.bytes;
}

/**
 * Construct an export only after all current reads are verified. Any denial
 * aborts the entire packet; never produce a partial bundle that looks complete.
 * No URL, title, query, cookie or raw media enters metadata-only mode.
 */
export async function buildCrawlerEvidenceBundle(options: BundleOptions): Promise<SourceExport> {
  gate(options);
  const { session, sourceIds, signal, includeBodies } = options;
  if (!session || !ID.test(session.session_id) || !Number.isSafeInteger(session.version)
    || session.version < 1 || session.consent_current !== true
    || typeof includeBodies !== 'boolean' || !Array.isArray(sourceIds)
    || sourceIds.length < 1 || sourceIds.length > MAX_SOURCES
    || sourceIds.some(id => typeof id !== 'string' || !SHA.test(id))
    || new Set(sourceIds).size !== sourceIds.length) refuse('Select 1–8 distinct authorized sources.');
  const before = await options.getSession(session.session_id, signal);
  gate(options);
  if (!sameSession(session, before)) refuse('The source session changed. Refresh before exporting.');
  const selected = [...sourceIds].sort();
  const rows: Record<string, unknown>[] = [];
  const checked = new Map<string, CapturedSource>();
  let totalBodyBytes = 0;
  for (const sourceId of selected) {
    gate(options);
    const record = await options.getSource(session.session_id, sourceId, signal);
    gate(options);
    if (!record || record.source_id !== sourceId || !SHA.test(record.content_digest)
      || record.use_policy?.enabled !== true || record.freshness?.usable !== true
      || record.freshness.state !== 'current'
      || record.freshness.remote_freshness_verified !== false
      || !Number.isSafeInteger(record.use_policy.version)
      || record.use_policy.version < 0) {
      refuse('At least one source is not currently authorized for use or its provenance is invalid.');
    }
    const row: Record<string, unknown> = {
      source_id: sourceId,
      captured_content_sha256: record.content_digest,
      use_policy_version: record.use_policy.version,
      captured_freshness: 'current',
      remote_freshness_verified: false,
    };
    if (includeBodies) {
      // The authoritative export endpoint alone decides whether content
      // may leave the application; the source GET is not export permission.
      const exported = await options.exportSource(session.session_id, sourceId, 'json', signal);
      gate(options);
      if (exported.session_id !== session.session_id || exported.source_id !== sourceId
        || !SHA.test(exported.content_digest)
        || typeof exported.media_type !== 'string'
        || exported.media_type.split(';')[0].trim() !== 'application/json'
        || typeof exported.content !== 'string') refuse('The source export identity is invalid.');
      const bytes = encoder.encode(exported.content).length;
      totalBodyBytes += bytes;
      if (bytes > MAX_BODY_BYTES || totalBodyBytes > MAX_BYTES)
        refuse('The selected sources exceed the bounded portable export size. Select fewer sources.');
      // A source export carries its own payload checksum, distinct from the
      // digest of captured text. The client verifies both independently.
      if (await options.sha256(exported.content) !== exported.content_digest)
        refuse('The authorized source export payload failed its checksum.');
      // The payload's own JSON body must match the *independently re-read*
      // source ID, capture hash and live authorization epoch. Verifying only
      // the envelope SHA would allow a different valid JSON body to be
      // substituted between GET and export.
      let body: Partial<CapturedSource>;
      try {
        body = JSON.parse(exported.content) as Partial<CapturedSource>;
      } catch {
        refuse('The authorized source export is not valid JSON.');
      }
      if (!body || typeof body !== 'object' || Array.isArray(body)
        || body.source_id !== sourceId
        || body.content_digest !== record.content_digest
        || body.use_policy?.enabled !== true
        || body.use_policy?.version !== record.use_policy.version
        || body.freshness?.state !== 'current'
        || body.freshness?.usable !== true
        || body.freshness?.remote_freshness_verified !== false
        || typeof body.text !== 'string' || !body.text.trim()
        || encoder.encode(body.text).length > MAX_BODY_BYTES) {
        refuse('A source changed between the authorized read and export.');
      }
      row.authorized_export_sha256 = exported.content_digest;
      row.authorized_export_media_type = 'application/json';
      row.authorized_export_body = exported.content;
    }
    checked.set(sourceId, record);
    rows.push(row);
  }
  const after = await options.getSession(session.session_id, signal);
  gate(options);
  if (!sameSession(before, after)) refuse('Source consent or campaign revision changed during export.');
  // Re-read each source after the bounded export, not just the campaign:
  // individual use policies may change without a campaign version change.
  for (const sourceId of selected) {
    gate(options);
    const original = checked.get(sourceId);
    const current = await options.getSource(session.session_id, sourceId, signal);
    gate(options);
    if (!original || !current || current.source_id !== sourceId
      || original.use_policy?.enabled !== true
      || current.content_digest !== original.content_digest
      || !SHA.test(current.content_digest)
      || current.use_policy?.enabled !== true
      || current.use_policy.version !== original.use_policy.version
      || current.use_policy.changed_at !== original.use_policy.changed_at
      || current.use_policy.max_age_seconds !== original.use_policy.max_age_seconds
      || current.freshness?.usable !== true
      || current.freshness.state !== 'current'
      || current.freshness.remote_freshness_verified !== false)
      refuse('A source policy, provenance or freshness status changed during export.');
  }
  // A final campaign read fences withdrawal during those source rechecks.
  const confirmed = await options.getSession(session.session_id, signal);
  gate(options);
  if (!sameSession(after, confirmed))
    refuse('Campaign consent or revision changed during final source checks.');
  const packet = {
    schema: 'skeleton.dragon.owner_evidence_bundle.v1',
    mode: includeBodies ? 'authorized_source_bodies' : 'metadata_only',
    session_id: session.session_id,
    session_version: before.version,
    source_count: rows.length,
    sources: rows,
    captured_source_rights_require_revalidation: true,
    remote_freshness_verified: false,
    independent_factual_verification: false,
    release_authorized: false,
    publication_authorized: false,
    training_authorized: false,
  } as const;
  const content = JSON.stringify(packet, null, 2) + '\n';
  if (encoder.encode(content).length > MAX_BYTES + 64_000)
    refuse('The evidence bundle exceeds its approved size.');
  const digest = await options.sha256(content);
  gate(options);
  if (!SHA.test(digest)) refuse('The evidence bundle digest is invalid.');
  return {
    filename: 'dragon-evidence-' + (includeBodies ? 'authorized-' : 'metadata-')
      + session.session_id.slice(0, 48) + '-v' + before.version + '.json',
    media_type: 'application/json',
    session_id: session.session_id,
    source_id: 'bundle',
    content, content_digest: digest,
  };
}
