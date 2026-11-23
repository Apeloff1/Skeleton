# Offline Mongo WiredTiger custody and three-store evidence

**Review-only. Read-only. No production MongoDB or Docker state changes.**

This source extends the existing verified cold archive, private byte
rehydration, real SQLite integrity and historical Chroma HNSW file custody
with an independent MongoDB WiredTiger file-envelope witness. It is
specifically NOT a mongod recovery procedure or release qualification.

## Operator commands

```sh
python scripts/local_ai_docker.py --mode cpu audit-restored-mongo \
  --source /private/existing-cold-archive \
  --destination /private/already-rehydrated-copy \
  --expected-receipt-sha256 INDEPENDENT_ARCHIVE_RECEIPT_SHA256

python scripts/local_ai_docker.py --mode cpu audit-offline-three-store \
  --source /private/existing-cold-archive \
  --destination /private/already-rehydrated-copy \
  --expected-receipt-sha256 INDEPENDENT_ARCHIVE_RECEIPT_SHA256
```

Both operations use **separate existing private host directories**, never
active Docker volumes. No daemon access, container start, credential use,
file mutation, BSON deserialization, WiredTiger page parsing, journaling
replay, Chroma native index load, or GGUF inference is performed.

## MongoDB static file custody

The Mongo source gate runs `verify_rehydration` at the beginning and end.
That verifier independently recomputes the original archive receipt and
restored file hashes with immutable role names and private ownership.

The new gate then inspects only the existing `mongo_data` role:

* Requires the five supported historical WiredTiger marker files:
  `WiredTiger`, `WiredTiger.turtle`, `WiredTiger.wt`,
  `_mdb_catalog.wt`, and `storage.bson`.
* Recognizes a bounded fixed set of additional WiredTiger metadata
  names, `collection-*.wt` and `index-*.wt` data files.
* Supports an optional `journal` directory with only a conservative
  numbered WiredTiger Log/Preplog/Tmplog file-naming format.
* Reports the count and hash of observed journal files as **unreplayed
  bytes**, not as recovered transactions, majority-durable data, or
  a known-consistent checkpoint.
* Tolerates optional diagnostic metadata only as a verified cold-copy
  role; it does not parse or print it.
* Denies unexpected file names or directories, symlinks, hardlinks,
  special files, public permissions, malformed roles, false recovery
  claims, missing required catalogs, excessive entries, unstable inode
  identity and changes detected on final cold rehash.
* Uses Linux `O_DIRECTORY` and `O_NOFOLLOW` to anchor the Mongo data and
  journal directory descriptors. Every file is opened with descriptor-
  relative `openat` semantics and SHA-256 streamed in 4-MiB blocks
  within finite file, aggregate-byte, entry-count and time caps.

The source recognizes only a **conservative historical layout**. A
MongoDB version with another valid WiredTiger layout may be rejected
until independently qualified. No parser of the binary files is
implemented; therefore a file with correct name and bytes can still
contain a corrupted MongoDB catalog or an incompatible storage engine.

## New versioned three-store evidence ledger

The previous read-only SQLite/Chroma ledger is retained intact. The
new `local_ai_offline_three_store.py` ledger validates that predecessor's
exact receipt contract, separately runs the new WiredTiger file-envelope
inspector, then re-verifies the entire original and restored archive.

The v2 digest binds fixed, strictly checked evidence only:

- Independent cold archive receipt SHA-256 and byte rehydration receipt;
- SQLite/Chroma predecessor evidence digest and count witnesses;
- Mongo file-envelope SHA-256, file count and journal count.

Its domain-separated SHA-256 is **unsigned observation metadata**.
It never grants merge, release, application state restoration, or
cross-store atomicity.

Every v2 receipt unconditionally denies:
`mongod_logical_replay_qualified`,
`mongo_majority_journal_durability_qualified`,
`source_writer_quiescence_verified`,
`sqlite_semantic_recovery_qualified`,
`native_chroma_graph_query_qualified`,
`cross_store_transaction_coherence_qualified`,
`application_restore_qualified`,
`protected_jeeves_chat_qualified` and
`release_authorized`.

## What remains necessary for actual recovery

A safe next phase requires separately authorized, truly disposable
restored copies on a real test host; a MongoDB-compatible recovery
process run only against those copies, not the source archive; actual
WiredTiger startup/log replay evidence and non-invasive logical
catalog reads; Chroma native vector-query/rebuild qualification; and
an independently measured cross-store writer-quiescence point with
committed actor-epoch boundaries and idempotent replay.

**This source is not that procedure.** Correct archived bytes alone
cannot prove that Mongo/SQLite/Chroma shared an atomic restore point.

## Focused source qualification

```sh
python -m compileall -q \
  scripts/local_ai_restored_mongo.py \
  scripts/local_ai_offline_three_store.py \
  scripts/local_ai_docker.py \
  skeleton/testing/test_local_ai_restored_mongo.py \
  skeleton/testing/test_local_ai_offline_three_store.py

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_restored_mongo.py \
  skeleton/testing/test_local_ai_offline_three_store.py \
  skeleton/testing/test_local_ai_offline_recovery_ledger.py \
  skeleton/testing/test_local_ai_restored_chroma.py \
  skeleton/testing/test_local_ai_restored_sqlite.py
```

Fixtures create only dummy WiredTiger-named files and journal bytes
inside private temporary directories; they do not create or connect to
a real MongoDB storage engine. Other fixtures challenge source drift,
forged replay and release flags, unknown file layouts, linked files,
unbounded catalog inventories, and unauthorized Docker usage.

**Draft review only. No release, merge, real database mutation, snapshot
claim or production migration.**
