# Artifact Plane

Packet: GB-8 Track E (this document also names GB-9 / GB-8b / GB-11 so later
packets have a single citation). Parent program: #80.

Git does not hold the 103 MB Godot blob. Clone without LFS must still import
Python. Missing binaries return `found=0` cards. They must not raise.

## Lanes

| Lane | Path | Packet | Rule |
|---|---|---|---|
| Track E tests | `tests/legacy_root/` | GB-8 | move root `*_test.py` / `test_*.py`; do not delete |
| Track E scripts | `scripts/archive_root_tests/` | GB-8 | alternate archive for non-pytest root scripts |
| SEVEN_BY docs | `docs/archive/seven_by/` | GB-8b | not in the same PR as GB-8 |
| Godot binary | LFS or external URL + pointer file | GB-9 | pointer in git; blob out of regular Git |
| Plane audit | `docs/lineage/plane_audit.md` | GB-11 | KEEP / SHIM / FOLD / QUARANTINE only |

Companion policy for size/LFS/release artifacts: `docs/ARTIFACT_POLICY.md`
and `scripts/check_artifact_policy.py`.

## GB-8 accept

- No `*_test.py`, `test_*.py`, `test_result.md`, or `backend_test.py.bak_*`
  at repository root.
- Archive lanes exist. Historical harnesses already live under
  `tests/legacy_root/` (hygiene pass, PR #236).
- `python scripts/check_root_sprawl.py` exits 0 on a clean root, 2 on sprawl.
- `skeleton.artifact_plane` imports without Godot, torch, or network.
- Cards carry `stored_prose=0`.

## GB-8b accept

- No `SEVEN_BY_*.md` at repository root.
- Lane `docs/archive/seven_by/` exists with `SEVEN_BY_INDEX.md`.
- Root README links the archive.
- Index body is moved, not rewritten.
- `python scripts/check_seven_by_archive.py` exits 0 on a clean root, 2 on sprawl.

## GB-9 accept

- `backend/godot` is not a tracked Git blob.
- Pointers exist: `godot.pointer` and `backend/godot.artifact.json`.
- Binary may live locally at `backend/godot` (gitignored) or via
  `SKELETON_GODOT_BIN` / `GODOT_BINARY` / `PATH`.
- `GodotLocator.locate()` / `godot_engine.binary.locate()` never raise.
- `found=0` is a card. Hint is `pointer:<url>` or `missing-godot-binary`.
- `python scripts/check_godot_pointer.py` exits 0 when pointers exist.

## GB-9 locate card

```
{kind:godot-binary, found:0|1, hint, stored_prose:0}
```

## Commands

```bash
python scripts/check_root_sprawl.py
python scripts/check_godot_pointer.py
python -m unittest tests.test_gb8_track_e tests.test_gb8b_seven_by tests.test_gb9_godot_pointer
```

## Forbidden

- Delete archived harnesses.
- Rewrite SEVEN_BY volume bodies.
- Commit a Godot engine binary.
- Copy artifact trees into git.
- Replace operator methods on `skeleton/cortex/deck.py`.
- Fork occupied PR branches (including closed #1008 branch).
