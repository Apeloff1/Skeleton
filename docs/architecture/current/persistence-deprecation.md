# Persistence deprecation (#4122), as on main

The full note is `docs/architecture/persistence-deprecation-4122.md`. In short:

- `skeleton.persistence` is the single canonical package.
- `skeleton.persist` → `skeleton.persistence.core`; `skeleton.storage` / `skeleton.state` →
  `skeleton.persistence.storage` / `.state` (planned, #4272).
- **Docstring-only:** each frozen module has a `Deprecated: use skeleton.persistence.X` line and
  `__deprecated__ = "skeleton.persistence"`. There is no `DeprecationWarning` and no new shim.
- `skeleton/testing/test_persistence_freeze_guard.py` enforces warning-free imports and stops
  `skeleton.persistence` from importing the frozen packages. The `skeleton/ai/runtime` twins stay
  byte-identical (`scripts/check_byte_identical_modules.py`).
- `tests/test_persistence_import_ratchet_4122.py` allowlists the remaining importers, and the
  count can only go down.

## References

- `skeleton.persistence:__name__`
- `skeleton.persist:__name__`
- `skeleton.storage:__name__`
- `skeleton.state:__name__`
