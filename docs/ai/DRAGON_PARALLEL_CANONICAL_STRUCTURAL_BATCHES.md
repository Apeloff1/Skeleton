# Parallel canonical structural graph batches

This opt-in source implementation extends canonical graph sharding with independent structural writes, not merely a secondary index. The release catalogue outbox, non-snapshot Steam expansion queue and built-in bootstrap inventory are now consumed by a bounded durable reservation protocol. Only jobs previously admitted through existing owner/corpus/feed authority are considered; no network fetch, entitlement, capture or external source grant is delegated.

## Reservation and settlement

One root journal per corpus root stores a bounded, hash-witnessed immutable plan, with before/after node and edge rows, job witnesses, per-owner/per-lane quota deltas, dataset candidates and expansion job intents. Planning uses the coordinated authoritative read/transaction and enforces existing caps before publication. Invalid jobs are held without partial row admission. Up to 32 jobs or 128 bootstrap inventory rows, 512 records and 4 MiB plan bytes are permitted per batch. Bootstrap cursor/revision advancement is published in the same settlement transaction. Readers and coordinated graph writers hold while the plan is pending. Root triggers fence dependent counters, directory, owner and replay mutations. Snapshot revocation remains available via the root grant ledger. A lane worker holds a shared root policy lock and writes its canonical nodes, child-local evidence, FTS and receipt with one independent rollback-journal transaction. Up to four lanes execute concurrently. Exact pre/post witnesses, lane identities, journal modes and device-space reserves are enforced. No root write lock during lane apply. Settlement verifies all lane receipts, exact post-state and original queued job witnesses before atomically publishing directory, reserved quota deltas, candidates, expansion work and terminal job states. A crash after some lane commits leaves a durable hold, not a partially public graph. Replaying committed lanes validates the original post-state and does not increment counts again.

## Operations

Fresh canonical graph provisioning enables the structural journal; existing canonical graph layouts require offline enablement, with all old writers stopped and a coherent backup:
- python -m core.dragon_graph_authority enable-structural-writers --root /private/corpus/root.db --offline-writers-stopped
- python -m core.dragon_graph_authority structural-status --root /private/corpus/root.db
- python -m core.dragon_graph_authority recover-structural --root /private/corpus/root.db

Recovery resumes only an existing reservation. Missing, replaced or damaged files/receipts remain held; restore a coherent authorized backup or inspect exact custody. Do not clear pending state, remove receipts, downgrade binaries, or restore a subset of the eleven graph/root files. A pending structural batch may temporarily block graph browsing and owner configuration; this prioritizes consistent publication over availability. Source work already reserved remains metadata-only. Snapshot-granted imports/expansions and feed-page ingestion still use the coordinated transaction path to preserve grant and page-chain semantics. Independent apply is not distributed consensus, arbitrary concurrent multi-batch admission, or a throughput guarantee; root reservation and settlement remain serialized.

## Qualification

The existing read-only Dragon Atlas backend workflow explicitly invokes this fixture with prior canonical and physical storage suites. The fixtures cover overlap of two real separate SQLite lane writer transactions, partial commit/replay, exact quota settlement, scope and invalid-source boundaries, missing shard, tampered plan and no-new-work recovery. They are not real deployment, power-cut or storage-capacity results. Actual device and exact-head CI evidence are still required.
