# Canonical Dragon graph authority: physical ten-lane local transactions

Stacked on #5447. Canonical full node records, evidence edges and FTS indexes move into ten SQLite files. Node identity determines its lane; evidence follows its child to preserve a local foreign key. Root retains only the key/URL directory for dependent foreign keys, canonical snapshot/grants, review operations, quotas, release settlement and commit sequence. The directory's legacy non-key columns contain sentinels, never graph evidence. The old root node, edge and FTS tables are absent after cutover.

## Atomicity contract and trade-off

SQLite ATTACH provides atomic multi-file commits for disk-backed main database in rollback journal mode, not WAL (https://sqlite.org/lang_attach.html; https://www.sqlite.org/atomiccommit.html). Every graph client attaches ten files before its transaction, checks identities, enforces DELETE journaling and EXTRA synchronization on all eleven, and updates the root fence with every graph mutation (including replay/touch). Root-dependent state and physical graph mutations use the same transaction. Existing corpus and release queue connections respect the root journal fence. Writes remain coordinated through one SQLite writer per corpus root. This is physical canonical data partitioning, not ten independent writers, consensus, network replication, or a throughput claim. Local filesystem/VFS durability is assumed; network mounts are unsupported. Device-level/power-loss qualification is separate. Historical snapshots and grants remain root authority; no source use/training permission expands.

## Operator provisioning and recovery

Stop all API replicas, schedulers, importers, cleanup and older binaries. Take one coherent backup of the root, existing owner-shard roots, payloads and related stores. Complete owner-level migrations first. For each corpus root to convert, use ten distinct unused private absolute paths on operator-controlled local filesystems. This is one offline multi-file migration transaction; node/edge rows are streamed and fingerprinted, FTS rebuilt, graph placement/FK/counter/directory witnesses checked, then old root authority tables are removed atomically with publication. Sufficient scratch disk/reserve, lock time and rollback-journal space must be qualified in advance; this is not an online or segmented transfer.

From backend:
- python -m core.dragon_graph_authority provision --root /private/corpus/root.db --offline-writers-stopped /private/graph/lane0.db ... /private/graph/lane9.db
- python -m core.dragon_graph_authority qualify --root /private/corpus/root.db --full
- python -m core.dragon_graph_authority probe --root /private/corpus/root.db --bytes-per-lane 1048576 --acknowledge-device-writes

Supply all ten literal paths, not the ellipsis. For a topology fully provisioned on every applicable owner-root, set SKL_DRAGON_CANONICAL_GRAPH_REQUIRED=1 to reject a restored root lacking authority metadata. Leave it unset during initial provisioning. A missing/wrong shard, unexpected journal mode, or incomplete topology holds the graph: no canonical fallback. Do not downgrade or start an old binary. Failed migration before commit leaves root authority unchanged and may leave unpublished child files; inspect them before selecting fresh paths. A successfully committed topology requires coherent restore of all eleven databases, never a single-file restore. Subsequent owner-level migration refuses active source/destination graph topologies. Derived FTS and edge enrollment is invalidated on cutover; canonical pages and edges use physical shards directly.

The write probe creates random non-game canary bytes (4 KiB–16 MiB per lane), commits all shards plus root witness, reopens and verifies exact bytes, atomically removes only probe records and verifies cleanup. It accounts for shared filesystem devices and retains a free-space floor. An interrupted committed probe can be located using pending-probes --root ... and verified/cleaned via recover-probe --root ... --id ... . Never remove a mismatched probe manually without custody review. Bounded device I/O evidence is not maximum capacity or simulated power-loss qualification. Full integrity audit may be expensive.

## Qualification gates

Run focused canonical graph, prior owner migration, lead graph/index/edge, release queue, corpus, storage and security tests at exact head. Separately run production-device offline migration, coherent independent backup/restore, power-cut/kill injection, disk-pressure and sustained concurrency/scale qualification. Source changes and fixtures alone do not establish workload speed or physical capacity. Review only; no merge or release authorization.
