# Offline core recovery — 2026-10-13

## Scope

This tranche restores the independent local-data and installer-kit helpers
from the source-pinned offline product branch (PR #3593,
`7f9be557bac3a4108dfc683716b15437de30f547`) onto modern `main`.

Recovered modules:

- `skeleton/app/offline_sqlite_safety.py`: sidecar/link path checks
- `skeleton/app/offline_history.py`: bounded portable transcript backup
- `skeleton/app/offline_readiness.py`: local artifact readiness inspection
- `skeleton/app/offline_library.py`: local document indexing and retrieval
- `skeleton/app/offline_workspace.py`: revisioned SQLite turn persistence
- `skeleton/app/offline_index_queue.py`: bounded offline indexing queue
- `skeleton/app/offline_snapshot.py`: local state snapshot/restore
- `skeleton/app/offline_audit.py`: local database audit
- `scripts/offline_kit.py`: model/wheel kit verification and no-index installation

Existing regression files restored:
`test_offline_sqlite_safety.py`, `test_offline_workspace.py`,
`test_offline_history_backup.py`, and `test_offline_kit.py`.

## Explicit boundaries and next integration

These are offline core primitives, **not** an accepted standalone release.
The old `skeleton/app/offline_cli.py` and
`packaging/windows/offline_cli_entry.py` have **not** been moved because they
depend on the legacy `OfflineGGUFSession` API, which modern
`skeleton/app/local_ai.py` no longer exports. Do not replace the evolved
`local_ai.py`, model-runtime packages, Windows installer, or workflow files
with their older PR #3593 versions.

A later tranche must adapt the CLI to the canonical modern serving interface,
review the local authorization and persistence boundaries, integrate packaging,
run real GGUF/native qualification, and obtain exact-head CI evidence before
claiming the offline product is complete.

A SHA-256 manifest checks integrity of a locally assembled kit, **not**
authenticity of third-party weights, release signatures, or network isolation.
No trained weights are included.
