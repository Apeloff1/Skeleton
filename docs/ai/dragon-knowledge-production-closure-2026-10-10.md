# Dragon knowledge production closure — 2026-10-10

Implementation on PR #3605. This is a code/readiness record, NOT evidence that
production tenants, keys, human reviewers, external anchors or data sources are
already configured.

## Existing authoritative integration

Companion UI -> authenticated Academy -> HOAG -> Wiki -> Almanac -> canonical
source revisions -> consented crawler. Parallel systems: dedicated signed
reviewer/approval grants; durable, revocable advisory memory; independently
anchored audit heads; global resource-scheduled crawler.

- dragon_wisdom_authority.py: owner-, issuer-, role-, identity-, organization-,
  target-, time- and nonce-bound HMAC-SHA256 review grants. Wiki reviewer cannot
  be the source author or publisher group. Memory approver must be distinct
  from Wiki reviewer. Keys for the two roles must be different and at least
  256-bit. Trusted issuer MUST authenticate real identities and their
  affiliations; identity_verified is an assertion from that issuer.
- dragon_wisdom_memory.py: owner-scoped, persistent advisory reference index.
  Only separately signed human-approved Wiki receipts are eligible; old
  unsigned legacy approvals are excluded. On every retrieval, current source
  root, revocation, new reviews, queued recrawls and expiry are rechecked.
  Nothing stores model weights, copied game assets or raw source passages.
- dragon_wisdom_custody.py: independent create-only signed head checkpoints
  outside SQLite. Verify full journal prefix and exact current source root.
  Rollback, corrupted anchor, missing head or unchecked new events fail closed.
  HMAC protects data integrity only when keys and anchor storage are independent.
- dragon_recrawl_dispatch.py: short-lived worker grants require shared
  GlobalResourceScheduler admission, tenant, consent, hardware and per-chunk
  preemption checks. Global capacity is returned only after worker stop.
- dragon_recrawl_executor.py: one real source recrawl with the canonical URL
  from ReviewedKnowledgeStore and the SocketBoundFetcher production transport,
  DNS pinned at connection and TLS hostname checked. Robots, HTTPS-only,
  redirects, host, delay, byte budget and live consent provider are enforced.
  Output is an unapproved source-review candidate, not admitted AI memory.
- backend/routes/dragon_academy.py: authenticated read-only knowledge/hoag,
  knowledge/recrawls and knowledge/memory endpoints. No browser source-approval
  or memory-mint operation is added.

## Production configuration / steps

1. Provision SKL_DRAGON_KNOWLEDGE_DB_PATH as an existing absolute durable SQLite
   path with verified source custody, access restrictions and monitored backup.
2. Provision SKL_DRAGON_WISDOM_ANCHOR_DIR on a separate secure volume, and
   SKL_DRAGON_WISDOM_ANCHOR_KEY_HEX from a dedicated managed 256-bit secret.
   Do not reuse Wiki-review or memory-approval signing keys.
3. Independently verify the existing owner journal before the first anchor.
   Initial bootstrap explicitly requires the trusted signer and
   allow_initial_bootstrap=True; do not automate bootstrap after corruption.
4. Set SKL_DRAGON_WISDOM_CUSTODY_REQUIRED=1. Product reads then return 409 on
   unanchored or rolled-back data. New journal events must be independently
   signed before they become visible. Missing configured keys return 503.
5. Integrate real independently authenticated identity provider principals
   with separate Wiki-review and human-approval signer services. Do not expose
   grant issuance through public routes or equate identity_verified=True with
   actual identity proof. Preserve key rotation/revocation evidence.
6. Install a production global resource policy, real hardware telemetry
   provider, current consent reader and bounded worker schedule. Supply the
   real SafeHttpFetcher with DNS-to-socket binding enabled.
7. On captured new source, run independent rights/claim/quote/revision review,
   then import with the expected source-parent digest. Only a new accepted
   canonical revision may resolve the original recrawl order.
8. Independently authorize model-memory training, license reuse, code/asset
   incorporation, game build, and release. Reference-only advisory memories do
   not satisfy any of these gates.

## Disaster-recovery and privacy expectations

- Database rollback behind latest signed external head: reject.
- Source changes without a matching signed root: reject.
- Journal append without current anchor: reject serving until independent seal.
- Missing anchor on non-empty journal: never silently bootstrap.
- On operator key loss, rotate with a reviewed external rollover/dual-key
  process. Preserving prior signatures requires the old verifier key.
- A worker crash must not be recorded as stopped. Source lease recovery and
  global grant reconciliation need an independently tested distributed worker
  owner; local in-memory SessionTask does not solve crash recovery.
- Full owner erasure requires coordinated deletion from source, Wiki, derived
  memory, external anchor metadata, backups and replicas; presently incomplete.
- Audit heads and local HMACs cannot defend against both signing-key compromise
  and destruction of the separate anchor root. External KMS/transparency
  anchoring provides stronger real-world custody.

## Release readiness checklist

- [x] Executable atomic recrawl queue and contradiction-proof review
- [x] Signed role-separated reviewer and approval grant implementation
- [x] Revocable persistent advisory memory and read-only product retrieval
- [x] Signed external head checkpoint/rollback validation implementation
- [x] Dynamic-consent one-shot production transport integration
- [x] Adversarial regression fixtures committed
- [ ] Exact latest-head verification passed across all required checks
- [ ] Production identity signer secrets and human review provisioned
- [ ] Operational anchor-after-write and global scheduler daemon connected
- [ ] Distributed lease recovery, multilineage erasure, and restore drills
- [ ] Approved acquisition sources ingested across all system/era targets
- [ ] Real game builds, real consumer hardware, rights review and release
- [ ] PR #3605 approved, undrafted, fully gated and merged

Checkmarks denote source committed, not host deployment. No amount of
synthetic regression success proves complete datasets or legal clearance.
