# Dragon physical owner-ledger partitions

Stacked on the tenfold dataset and volume fabric. This change enables ten distinct SQLite files for the corpus/lead/release transaction plane and ten files for each primary and backup manifest plane. It is deliberately **owner partitioned**, not a distributed graph for one account. Intra-owner cap and hotspot limits remain.

## Offline provisioning

Stop **all** existing writers (API replicas, schedulers, import CLIs, cleanup workers). Back up each existing root and its WAL-consistent data. Use private operator-owned absolute directories, preferably on separate appropriately provisioned filesystem devices. The first of ten paths must be the existing root; the other nine must not exist. Do not point another Dragon storage plane at any shard.

From backend, with the existing Python environment:

- `python -m core.dragon_owner_shards --plane corpus --offline-writers-stopped /private/corpus/root.db /private/corpus/lane1.db ... /private/corpus/lane9.db`
- `python -m core.dragon_owner_shards --plane manifest --offline-writers-stopped /private/primary/root.db /private/primary/lane1.db ... /private/primary/lane9.db`
- Repeat the manifest command for the independent backup root and its nine new files.

The ellipsis is illustrative; supply all ten literal paths. The corpus root remains configured via SKL_DRAGON_GAME_CORPUS_DB_PATH; the manifest roots remain configured via their existing environment variables. Set SKL_DRAGON_CORPUS_SHARDS_REQUIRED=1 and SKL_DRAGON_MANIFEST_SHARDS_REQUIRED=1 for fully provisioned deployments to reject missing root topology. Never use the flags to simulate provisioning. A topology is published in one root transaction only after child markers exist. Interrupted provisioning can leave unpublished child files; inspect and clean those manually, never delete a published shard.

## Guarantees and limits

- Stable owner hash routing plus persisted assignments. Existing canonical owners and tombstones stay in the original root; new owners are assigned across ten lanes. No row moves or ID regeneration. Single owner placement preserves atomic outbox/FTS/catalogue/graph joins and owner-wide manifest chunk reference accounting.
- Root router and markers must be present. Missing or mismatched child files are held, not recreated or redirected. Private path, symlink, link count and sidecar checks protect operator-controlled storage; this is not a malicious same-UID sandbox.
- APIs, CLI imports, source binding and media metadata route through the same owner placement. The worldwide discovery subscription and origin guard remain global, with feed metadata projected to the owner's routed corpus. No new network concurrency, consent or rights.
- Release, lead and media maintenance cursors rotate independently and durably. A failed child is held and the cursor advances; each scheduler retains its previous maximum per-pulse workload. Thus ten lanes may increase revisit latency; tune only after measurement. Global dataset cleanup remains separate.
- Manifest shards share a physical payload pool per copy lane. Owner-wide deduplication and garbage checks stay local to the owner ledger. Primary/backup qualification requires no common ledger device between the two sets. Sharded topology changes invalidate an older topology-bound probe, so requalify before new cold relocation. In-progress cold staging may need explicit recovery because its pinned qualification digest changes.
- Back up the routing root, all child ledgers and the payload volumes as one coordinated set. No live downgrade to an old binary. No automatic repartition of an existing hot owner, no consensus replication, no multi-machine filesystem qualification, no distributed single-owner edge/manifest index, no physical capacity or throughput claim.

## Qualification

Run backend/tests/test_dragon_owner_shards.py and inherited world archive, lead graph, media/cold and security suites at the exact final head. Independently exercise crash between child creation and topology publication, route-root loss, coherent restore, same-owner competing writers, all device mount combinations, global origin pacing, physical backup/restore and scale soak. Source-only tests are not proof of actual deployed storage. Review only; do not merge or release.
