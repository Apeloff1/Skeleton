# Docker local-AI — read-only offline recovery evidence ledger

**Purpose:** One operator-readable, deterministic receipt binding the
independently reverified cold source archive, new private byte-restore
output, real SQLite structural integrity and optional Chroma historical
HNSW binary custody. It is **NOT** a database-level cross-store restore.

## Operator command

```sh
python scripts/local_ai_docker.py --mode cpu audit-offline-recovery-evidence \
  --source /private/offline-archive \
  --destination /private/new-byte-rehydration \
  --expected-receipt-sha256 INDEPENDENT_ARCHIVE_RECEIPT_SHA256
```

This is wholly read-only: no Docker daemon, no image retrieval, no
database process startup, no production volume mount and no file writes.
The two directories must already have been created and individually
qualified by the existing separate cold-copy/rehydration workflow.

## Independent sequence

1. Verify the *original* SHA-256 of the cold archive receipt and every
   recorded original/restored byte via `verify_rehydration`. Admit only
   the exact known receipt schema, the four mandatory app roles and
   optional `chroma_data`, all required hold flags FALSE, private
   per-volume manifest SHA values and exact total file/byte counts.
2. Run the full restored SQLite verification independently. This has
   its own archive recheck, private/singly-linked file admission,
   WAL/SHM/journal denial, real SQLite integrity and foreign-key checks,
   bounded counts and file hash/timestamp comparison.
3. If the source receipt contains Chroma, run the independent offline
   Chroma HNSW custody verifier: immutable metadata SQLite,
   bounded persistent segment catalog, exact UUID directory/file
   inventory, descriptor-relative file hashes and pickle non-execution.
   If Chroma was not part of the original source, do **not** pretend
   an empty vector index was checked.
4. Verify the entire original and restored byte receipt a **second**
   time. The receipt object must be identical to the first; any
   source/restore drift or altered checksum is a hard failure.
5. Compute a domain-separated SHA-256 over a fixed bounded
   metadata envelope: cold source receipt hash, byte-rehydration receipt
   hash, SQLite/Chroma independent digests and counts, and Chroma
   presence. No user records, SQL table names, paths or secrets appear
   in this hash input or output.

Each independent subgate has strict allowed fields and statuses. Empty
SQLite or empty HNSW indexes are recorded as NOT qualified, rather
than interpreted as success. Unsupported Chroma versions, an unverified
source manifest, inconsistent totals, fabricated `j=true` durability,
unknown metadata or receipt authority escalation are denied.

## Guaranteed limitations

The evidence ledger is **unsigned observation metadata**. It is not
proof of an atomic snapshot, idempotent Mongo application operations,
physical Mongo WiredTiger journal replay, aligned Mongo/SQLite/Chroma
transaction boundaries, a valid native HNSW graph, semantic correctness
of embeddings, quiesced external writers, recovery-point objectives,
GGUF inference, protected Jeeves turns or release provenance.

Even when both independent SQLite and Chroma file subgates pass, the
ledger unconditionally emits these false flags:

- `physical_source_writers_quiesced`
- `mongo_wiredtiger_logical_recovery_qualified`
- `sqlite_application_semantics_qualified`
- `chroma_native_vector_query_qualified`
- `cross_store_transaction_coherence_qualified`
- `database_application_restore_qualified`
- `protected_jeeves_chat_qualified`
- `release_authorized`

This preserves the operational distinction between exact file custody
and a safely restorable application. The source does not attempt to
repair or write either database, reset epochs, or resume writers.

## Focused exact-head source acceptance

```sh
python -m compileall -q \
  scripts/local_ai_offline_recovery_ledger.py \
  skeleton/testing/test_local_ai_offline_recovery_ledger.py \
  scripts/local_ai_docker.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_offline_recovery_ledger.py \
  skeleton/testing/test_local_ai_restored_chroma.py \
  skeleton/testing/test_local_ai_restored_sqlite.py \
  skeleton/testing/test_local_ai_data_rehydration.py
```

Hostile tests forge source receipts and per-volume manifests, alter
SQLite/Chroma result schemas and flags, introduce mismatched totals,
change the archive on recheck, or inject secret-bearing failures.
One integrated fixture runs **real SQLite page checks and real HNSW
binary hashes** on private synthetic files while mocking only the
separately tested archive-byte gate.

No source test is a substitute for an operator-controlled physical
restore, independent writer-quiescence witness or protected chat test.

**Draft/review only; no merge, release or production state change.**
