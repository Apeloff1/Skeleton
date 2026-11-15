# Dragon tenfold shard fabric

Stack: #5443. Review-only. No additional network, source, consent, training or retention authority.

## Admission topology

| Plane | Previous | New | Boundary |
| --- | ---: | ---: | --- |
| Structured game dataset DB files | 256 | 2,560 | Independent SQLite files; game-local transactions |
| Hoarder physical volumes per lane | 256 | 2,560 | Independent operator-configured filesystem devices |
| Lead node quota per owner | 20,000,000 | 200,000,000 | Ten indexed logical quota ranges; shared SQLite ledger |
| Lead evidence edge quota per owner | 100,000,000 | 1,000,000,000 | Ten child-ID quota ranges; shared SQLite ledger |

No tenfold throughput, disk capacity, populated rows or live external crawling is established.
Per-request bytes, parser limits, current rights, snapshot row bounds, release queue, game catalogue, native memory and query windows are deliberately unchanged.

## Deployment

1. Stop all old binaries and scheduler processes. Back up the complete SQLite databases and WAL-consistent state. Never permit mixed-version writers.
2. Preserve every existing game-data-XX.sqlite3 file. Each legacy file also becomes a route directory. Existing game histories (including erased version tombstones) pin lane zero. First new game assignment is deterministic and transactionally persisted; missing assigned child shards fail closed. A missing legacy directory with surviving nonzero lanes is held. Back up route directories together with their payload shards. Do not move or rename the files independently.
3. Existing SKL_DRAGON_DATASET_ROOT still works. Ten maintenance slots are advanced per pulse (maximum 20 selected expired versions, same per-shard record deletion budget). A held slot is retried on the next rotation. Logical deletion is not physical secure erase. A full disk or one hot game still needs migration/partitioning within that game.
4. Provision private physical devices and retain all existing volume names and chunk placements. For large configurations use SKL_DRAGON_HOARDER_VOLUMES_JSON_FILE and SKL_DRAGON_HOARDER_BACKUP_VOLUMES_JSON_FILE instead of their inline JSON equivalents, never both. Files must be private, canonical, regular, single-link, stable, and at most 4 MiB. Use existing explicit bootstrap and additive expansion controls. Configuration change while running is held; restart after approved changes. One filesystem device per volume and independent primary/backup custody remain required.
5. Re-run the physical qualification tool at the new topology; an old receipt cannot attest the expanded topology. Verify real restore/failure behavior separately. Probe readback now opens only the probed volume instead of initializing all volumes repeatedly.
6. Lead lane counts are populated lazily from existing indexed ranges in the same write transaction and updated only on newly admitted nodes/edges. Existing IDs, FTS, graph relations, replay witnesses and owner scoping are unchanged. Range skew can hold a lane before the aggregate cap. Large legacy ranges can take time to count. This is a quota partition, not a physically distributed graph; the shared SQLite ledger remains a performance and capacity bottleneck.

## Qualification

Run exact-head backend/tests/test_dragon_lead_graph.py, backend/tests/test_dragon_world_archive_expansion.py, backend/tests/test_dragon_hoarder_media_cold.py and the canonical crawler/security suites. Independently test interrupted startup, concurrent same-game assignment, mixed-version rejection by deployment orchestration, disk-full and device loss, multi-volume topology expansion, physical restore and workload latency at scale. The shared graph, catalogue and manifest indexes need separate distributed migration designs. No release or merge authorization.
