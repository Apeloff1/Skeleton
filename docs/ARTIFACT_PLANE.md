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

## GB-9 locate card

```
{kind:godot-binary, found:0|1, hint, stored_prose:0}
```

`GodotLocator.locate()` / `godot_engine.binary.locate()` equivalent:
`skeleton.artifact_plane.godot_locate`. `found=0` is a card, not an
exception. Hint may be `missing-godot-binary`, `pointer:<url>`,
`env:SKELETON_GODOT_BIN`, or a relative path.

## Commands

```bash
python scripts/check_root_sprawl.py
python scripts/check_root_sprawl.py --json
python -m unittest tests.test_gb8_track_e
```

## Forbidden on GB-8

- Delete archived harnesses.
- Move `SEVEN_BY_*.md` (GB-8b).
- Commit a Godot engine binary (GB-9).
- Copy artifact trees into git.
- Replace operator methods on `skeleton/cortex/deck.py`.
- Fork occupied PR branches.
