# Local Jeeves Docker — offline Chroma index-file custody

**Review-only; not a functioning vector-database restore.** This extension
to the verified cold archive and byte-rehydration path never starts Chroma,
unpickles its index metadata, loads HNSW graph code, connects to Docker,
or touches production volumes.

## Why a clean SQLite file is not enough

Chroma can persist its system metadata in `chroma.sqlite3` and its HNSW
vector index in UUID-named directories. A clean SQLite integrity check
does not prove `header.bin`, `data_level0.bin`, `length.bin`,
`link_lists.bin` or `index_metadata.pickle` were restored completely.

This qualification intentionally supports **only the known historical
local-persistent HNSW segment format**. The required vector type is
`urn:chroma:segment/vector/hnsw-local-persisted`. Newer or different Chroma
storage formats fail closed instead of being called recovered.

## Operator

```sh
python scripts/local_ai_docker.py --mode cpu audit-restored-chroma \
  --source /private/offline-archive \
  --destination /private/new-rehydrated-copy \
  --expected-receipt-sha256 VERIFIED_COLD_ARCHIVE_RECEIPT_SHA256
```

This is read-only against **already-created private host copies**, never
the source Docker volumes. The gate first runs the independent complete
archive and rehydration byte verification. The Chroma role must be
present alongside the four other canonical app state roles.

## Verified facts

1. Validate private, singly-linked `chroma.sqlite3` with the full SQLite
   integrity/foreign-key checks and no `-wal`, `-shm` or `-journal`
   sidecars. Use query-only immutable SQLite, disabled loadable
   extensions, and bounded read operations.
2. Query only the bounded fixed `segments` catalog, require known
   segment scopes, unique UUIDv4 identities, and exact local-persistent
   HNSW vector type; reject unknown formats.
3. Match physical UUID directories exactly to the catalog's persistent
   vector segment IDs. Missing or unreferenced directories fail closed.
4. Require the five named HNSW binary files in each directory. Reject
   extra/missing files, symlinks, non-private modes, invalid header
   lengths, oversized metadata and unbounded file counts or sizes.
5. Hash each binary with SHA-256 using a constant-memory 4-MiB stream,
   `O_NOFOLLOW` file admission, per-file inode/size/timestamp checks,
   and a bounded overall deadline. **Never unpickle metadata.**
6. Re-read the SQLite catalog after hashing and require unchanged
   catalog, physical directory identities and no newly appearing
   recognized SQLite journal sidecar.

The receipt contains only counts and SHA-256 fingerprints; no private
filenames, user records, SQL rows or Mongo hosts. A database with zero
persisted HNSW segments reports an **unqualified** vector index.

Even a passing binary custody receipt unconditionally reports:
`pickle_deserialized=false`,
`hnsw_graph_load_qualified=false`,
`chroma_logical_replay_qualified=false`,
`mongo_consistency_verified=false`,
`cross_store_snapshot_atomic=false`,
`application_restore_qualified=false`,
`protected_jeeves_chat_qualified=false`,
and `release_authorized=false`.

The HNSW pointer graph, actual vector-search behavior, concurrent writes,
Mongo epoch alignment, source quiescence and cross-store application
recovery are **not** established by checking index file hashes.

## Focused source qualification

```sh
python -m compileall -q \
  scripts/local_ai_restored_chroma.py \
  skeleton/testing/test_local_ai_restored_chroma.py \
  scripts/local_ai_docker.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_restored_chroma.py \
  skeleton/testing/test_local_ai_restored_sqlite.py \
  skeleton/testing/test_local_ai_data_rehydration.py
```

Hostile fixture tests create only disposable synthetic SQLite catalogs
and index binaries. No test loads native Chroma indexes or reaches
production data, and source test success alone is not physical recovery
evidence.

**Draft review only. No merge, release, live volume modification,
actor migration or GGUF chat qualification.**
