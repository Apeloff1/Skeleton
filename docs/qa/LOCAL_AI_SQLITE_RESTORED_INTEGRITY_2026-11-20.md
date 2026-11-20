# Docker local AI — independently verified SQLite restore integrity

**Scope:** Offline, read-only integrity of existing *new private
rehydration directories*. This is not a Docker volume restore, a
production database connection or an atomic Mongo/SQLite/Chroma backup.

## Source-backed operation

Before the module can inspect any SQLite file it must independently call
the existing `verify_rehydration` for all originally archived and
restored bytes. That prerequisite validates the original cold-copy
receipt SHA-256, exact source manifests, independently rehashed files,
private target identity and the byte-rehydration receipt. A failed
prerequisite is a hard denial, not a warning.

The new operator command is:

```sh
python scripts/local_ai_docker.py --mode cpu audit-restored-sqlite \
  --source /private/offline-app-archive \
  --destination /private/new-restored-app-copy \
  --expected-receipt-sha256 INDEPENDENT_COLD_RECEIPT_SHA256 \
  --max-databases 32
```

It DOES NOT run `docker exec`, start a container, mount a live data volume,
modify archive contents, open a network connection or migrate actor epochs.
It only inspects already rehydrated private host files.

## Threat and failure coverage

- A bounded two-pass scan of the existing
  `backend_data`, `skeleton_data` and optional `chroma_data` roles
  identifies up to 32 `.sqlite`, `.sqlite3` or `.db` files.
- All recognized `-wal`, `-shm` and `-journal` sidecars are denied
  **before** any SQLite connection. Reading an immutable database while
  disregarding an uncheckpointed WAL would create a false consistency
  claim, so this tool never does so.
- Each database must be a private, single-linked regular file within a
  2-GiB per-file cap. Path symlinks and special files are refused by the
  inherited bounded volume walker.
- A `file:` URI connection uses SQLite's read-only/immutable flags.
  `PRAGMA query_only=ON`, `trusted_schema=OFF`, disabled extension
  loading, and a bounded progress/deadline window defend the audit
  without creating or modifying SQLite files.
- A complete `PRAGMA integrity_check` and
  `PRAGMA foreign_key_check` must both report no structural
  inconsistencies. Every inspected SQLite file is independently hashed
  before and after to detect changed bytes and file identity.
- A no-database archive is reported as **not** integrity qualified, not
  as a vacuous success. Count overflow, missing cold receipt, unreadable
  file, secret-bearing exception, malformed source or SQLite corruption
  all fail closed.

The receipt contains only counted databases and bytes, a domain-separated
aggregate data digest, and bounded booleans. No filenames, schema names,
private messages, tenant IDs, passwords or Mongo hostnames appear in
operator output.

## What this does not prove

A structurally valid SQLite snapshot does not prove checkpoint timing,
application-level idempotency, exact cross-store logical transaction
boundaries, replay of message/tool commits, Mongo WiredTiger recovery,
Chroma index/vector consistency or a coherent multi-store restore.
Those are **separate** acceptance gates requiring independent physical
recovery, writer-quiescence and producer/consumer evidence.

Every receipt requires:
`mongo_consistency_verified=false`,
`chroma_consistency_verified=false`,
`cross_store_snapshot_atomic=false`,
`application_restore_qualified=false`,
`protected_jeeves_chat_qualified=false`, and
`release_authorized=false`.

## Source qualification

```sh
python -m compileall -q \
  scripts/local_ai_restored_sqlite.py \
  skeleton/testing/test_local_ai_restored_sqlite.py \
  scripts/local_ai_docker.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_restored_sqlite.py \
  skeleton/testing/test_local_ai_cold_backup.py \
  skeleton/testing/test_local_ai_volume_copy.py \
  skeleton/testing/test_local_ai_data_rehydration.py
```

Source tests create only disposable private synthetic SQLite files inside
the test fixture and exercise actual SQLite page integrity rather than
mocking SQLite. Other fixtures emulate the previously verified source
receipt to challenge denial/entry conditions; no physical production
Docker or database test has been performed by these unit fixtures.

**Draft/review only. Do not merge, release, or modify production volumes.**
