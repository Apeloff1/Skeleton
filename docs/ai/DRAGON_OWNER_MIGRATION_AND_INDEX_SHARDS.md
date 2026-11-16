# Dragon legacy migration and intra-owner search partitions

Stacked on #5445. Review-only source. No live migration or physical capacity claim.

## Existing owner cutover

After provisioning ten ledgers, stop all application replicas, CLI writers, schedulers and cleanup processes, and take a coherent backup of root, children, and payload devices. Use an operator-only 0600 scope JSON containing tenant_id and owner_id.

Run from backend:

`python -m core.dragon_owner_migration --root /private/corpus/root.db --plane corpus --scope-json /private/scope.json --destination 4 --offline-writers-stopped`

For manifests, run the equivalent command against each independent primary and backup manifest root with its own intended destination. Every existing owner is moved as a unit; an owner in lane 0 can move to lanes 1–9. Non-root-to-non-root moves are intentionally not implemented. The payload remains on the original named volumes; only manifest metadata moves. A durable copying intent gates runtime routing and maintenance across the plane. Bounded row reads feed exact logical SHA-256 witnesses; target commit precedes source logical deletion plus route publication in one root transaction. A crash after target copy leaves an explicit hold. Re-run with identical plane/scope/destination and both files present to verify the copy and finish. Conflicting destination rows are held; never overwrite or delete them automatically. No automatic rollback, live migration, simulated array, secure disk erasure or concurrent old writer protection is claimed. A full owner's transaction may require substantial WAL/storage and maintenance time; qualify disk reserve beforehand. Source locator FTS internal row IDs are remapped, while exact logical search rows and all canonical identities are retained. Existing global origin subscriptions remain at root. Derived owner-search enrollment is invalidated at migration.

## Single-owner physical search

Set SKL_DRAGON_LEAD_INDEX_ROOT to an existing private operator directory. This is optional, derived candidate metadata only, never preserved source content or training truth. From backend:

`python -m core.dragon_lead_index_shards --scope-json /private/scope.json --acknowledge-metadata-index --pulse 10`

Each owner has a random epoch and ten independent hashed-range SQLite FTS files. Source triggers capture inserted/deleted/search-field changes in a bounded-batch delta mechanism. An initial resumable keyset scan is followed by revision catchup; the existing lead scheduler advances one enrolled lane per relevant pulse. No 10x scheduler request rate or new network permission. Queries use the physical index only if all ten lane revisions and lineage stamps agree with the same canonical read snapshot. Results are merged by identity and hydrated from the canonical graph; stale/missing/corrupt shards fall back to canonical FTS. Old deltas are pruned only after commit, with a retained floor. Restored or divergent source/index snapshots must be re-enrolled with --reset-derived-index (new epoch); manually archive/remove obsolete private epoch directories after stopping writers. No automatic secure deletion. Initial scanning, catchup and storage must be measured on real hardware; write churn may cause sustained canonical fallback. This splits search indexes for a single owner, not the writable lead/edge ledger or manifest transaction plane. It does not create physical capacity or benchmark evidence.

## Qualification

Run backend/tests/test_dragon_owner_shards.py and inherited lead graph, world archive, media/cold, security and CI suites. Use separately approved offline migration and physical fault/restore tests; owner data and device files were not moved by this source change. Verify exact-head CI before merge or release.
