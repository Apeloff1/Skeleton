# Acquisition lineage and cold retention continuation

Implementation sign-off: Codex, 2026-10-10. Scope: PR #3605 continuation only.
This document does not grant enterprise qualification, acquisition rights,
training authority, approved corpus completion or release permission.

## Delivered behavior

The sequential almanac worker verifies the complete receipt prefix both before
leasing a stage and before accepting its output. Checks bind the current source
registry digest, owner, source, URL, stage order, input/output hashes, timestamps,
non-training status and each stage's required policy/extraction/analysis fields.
Missing, extra, oversized, altered or future receipts deny advancement without
spending an attempt or changing a lease. A discovery-metadata revision invalidates
the old prefix. Existing blocked-job recovery preserves valid receipts and
restarts policy; it refuses to archive corrupt receipts. Hashes remain integrity
identities, not authenticated signatures or legal authorization.

Canonical conversation retention now invokes tenant-scoped projection cleanup,
including an empty parent retention plan. Each call removes at most 128 expired
checkpoints and 128 expired negative fences. Checkpoint postings are erased in
the same SQLite write snapshot. Indexed key-only selection avoids materializing
private payloads. The result exposes expired_checkpoints, more_due and batch_limit;
operators can schedule repeated canonical retention sweeps to drain cold rows.
Live fences, active checkpoints and other tenants remain unchanged. Cleanup
failure prevents a successful retention response and can be retried. Synchronous
SQLite connections must retain their configured short busy timeout; the async
250 ms wrapper cannot interrupt arbitrary synchronous native work.

Admission rejects expired or more-than-seven-day checkpoint lifetimes at the
store boundary as well as in the current-policy binding. Historical tests now
supply their explicit fixture clock rather than relying on wall time.

## Construction and operations

L00–L03: existing game-builder, retrieval and Mongo conversation owners retain
authority. No new service, credential boundary, provider, consent or scheduler.
L04–L05: write-snapshot lineage validation and bounded atomic expiry.
L06–L07: tenant isolation, no receipt laundering, rollback on failure, repeated
idempotent cleanup and original negative-fence behavior.
L08–L09: content-free batch counts and bounded payload/materialization/row costs.
L10: real SQLite reopen, receipt corruption and actual retention-owner tests.
L11–L12: additive expiry indexes; rollback removes the cleanup consumer and can
remove indexes, never restores expired private data. The operator still supplies
current consent, durable SQLite, independent source approval and retention
scheduling. No new timer or detached worker is installed.
L13: independent identity, licensed corpus, distributed recovery, consumer-device
qualification and exact-head hosted acceptance remain open.

## Local validation

The Dragon regression run passed 1,016 tests with 19 native/environment skips.
The final focused almanac/resource/provider checks passed 73 tests. The backend
conversation/runtime/governance/Academy run passed 66 tests. Architecture,
construction, capability interfaces, state topology, enterprise-superiority
schema and source-current implementation dossiers pass. The mandatory provider
scan and hosted checks are recorded separately after they finish.

These checks prove the stated implementation increment, not all 20 active PRs
or complete game-production/AI product qualification.
