# Hoarder intra-owner physical manifest write lanes

Review-only change stacked on #5446. Nine new independent SQLite transaction ledgers plus the existing ledger, per explicitly enrolled owner and per primary/backup copy. Existing IDs, tombstones and chunk keys remain in the existing owner ledger. All new IDs use a deterministic ten-way hash route. A missing partition cannot fall back to the original ledger or silently recreate the ledger. Existing cold/media/copy interfaces continue to use the same original manifest identities.

## Provisioning

Stop every writer, scheduler, API replica and importer. Initialize the existing primary and backup stores, and back up routing roots, all manifest ledgers and payload DBs coherently. Finish any owner-level migration before enrolling these write partitions. From backend, for an operator-private 0600 scope JSON:

`python -m core.dragon_manifest_write_lanes --copy primary --scope-json /private/scope.json --offline-writers-stopped`

Repeat for backup. A random persistent epoch selects a private sibling directory with nine shard files. They must remain on the owning ledger's device, preserving the existing primary/backup ledger device separation. Do not downgrade to old binaries after enrollment. Interrupted provisioning before enrollment publication leaves unpublished files; inspect them manually. Do not erase any published directory. Existing owner-level migration intentionally refuses an owner with intra-owner enrollment until a future coherent multi-ledger migration is available.

## Custody and costs

Each nonzero lane uses a separate domain-separated payload owner key; legacy payload owner keys remain unchanged. This keeps chunk reference checks, journaled append, abort, and local garbage collection atomic within each physical ledger. Deduplication remains exact within a lane, not across lanes; repeated content in different lanes can consume extra physical bytes. Usage sums namespace-local unique counts. The existing volume budgets, filesystem reserves and per-object limits remain enforced. Nominal manifest cap becomes ten times the per-ledger limit only if all lanes can reach it; actual media, Mongo relocation and retention authorities are not increased. Cross-lane history merges bounded sorted pages, not an atomic multi-file snapshot. Collection is bounded and round-robin. Payload volume SQLite writers can remain a bottleneck on the same physical device. This is not ten independent machines or a benchmark claim.

## Qualification

Run the new partition fixture and inherited owner migration, manifest, media, cold-primary and security suites at exact head. Qualify the actual devices with independent operator probes, fault injection, coherent restore, full reference audit and real sustained workload before deployment. No live data was moved; no CI/device results are claimed.
