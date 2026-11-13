# Persistence package deprecation (issue #4122)

TD ruling (Jenkins) on #4122 / draft PR #4267: **deprecation is docstring-only.**

`skeleton.persistence` is the single canonical persistence package. The old packages stay
importable and unchanged in behaviour:

| Old package | Deprecated in favour of | Status |
|---|---|---|
| `skeleton.persist` | `skeleton.persistence.core` | star-import compatibility shim over the canonical modules |
| `skeleton.storage` | `skeleton.persistence.storage` (planned) | real code; byte-identical twin in `skeleton/ai/runtime/storage` |
| `skeleton.state` | `skeleton.persistence.state` (planned) | real code; byte-identical twin in `skeleton/ai/runtime/state` |

Each frozen module carries:

- a `Deprecated: use skeleton.persistence.X` line in its module docstring (with the real or planned
  target), next to the existing `FROZEN (issue #4122)` notice;
- a module-level marker `__deprecated__ = "skeleton.persistence"`.

There is **no `DeprecationWarning`** and **no new re-export shim**.
`skeleton/testing/test_persistence_freeze_guard.py` keeps enforcing warning-free imports and
forbids `skeleton/persistence` from importing the frozen packages.

## Twins and parity

The storage/state modules and their `skeleton/ai/runtime` twins got identical edits, so
`scripts/check_p3t2_storage_candidate.py` (byte equality) and
`scripts/check_byte_identical_modules.py` (twin groups keyed by path set) stay green for them.
Moving storage/state into `skeleton.persistence` is a separate follow-up. It moves both twins in
one PR and keeps parity green the whole time (see the follow-up issue linked from #4267).

## Ratchet

`tests/test_persistence_import_ratchet_4122.py` lists the remaining importers of the old packages
as an allowlist. Any new importer fails the test. When an importer is migrated, its allowlist
entry must be removed (a stale entry fails too), so the count can only go down.
