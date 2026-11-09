# Tracked repository atlas — Batch 1

The repository's canonical ownership taxonomy remains `.machine/repository.toml`,
and the existing `skeleton.repo_machine` and code-search indexes retain their
authority. This atlas is a **derived, pinned Git-tree projection** of *every*
tracked entry, including ignored/transitional archives, symlinks and gitlinks.
It is not an execution engine or an authority for changing files.

## Commands

```bash
python -m skeleton.repo_machine.tracked_inventory --root . --output .machine/tracked-inventory
python -m skeleton.repo_machine.tracked_inventory --root . --output .machine/tracked-inventory --check
python -m unittest discover -s tests -p 'test_tracked_inventory.py' -v
```

The first command builds deterministic artifacts. The second fails if *any*
artifact differs from the current HEAD-derived content, or if a file is missing.
The workflow `.github/workflows/repo-machine-index.yml` builds this atlas on
main pushes, scheduled refreshes, manual dispatches and relevant pull requests,
checks it, validates source commit identity, and uploads artifacts alongside
the existing machine/code-search indexes.

## Artifacts (build output; do not commit as source of truth)

- `manifest.json` — schema, pinned source commit/tree, format, completeness
  declaration, counts, content hashes and sizes of the other artifacts.
- `files.jsonl` — sorted, exhaustive tracked entries with path, mode, Git OID,
  Git blob size, zone, owner, lifecycle and directory-derived feature family.
- `groups.json` — compact per-zone/per-directory-family counts to seed
  bounded-context navigation; semantic capability labels are *not* implied.
- `exact-duplicates.json` — identical Git blob object IDs grouped by content,
  with modes and all paths. Review is mandatory before any deduplication.

The index is reproducible for the same commit and taxonomy. It neither reads
uncommitted worktree changes nor silently skips paths based on ignore settings.
Gitlinks are enumerated but never treated as blob duplicates. Git symlink blob
hashes identify **link text**, not the content of their targets. Modes are
included so executable/regular/symlink distinctions remain visible.

All indexes are fail-closed: malformed Git records, unsupported modes,
noncanonical paths, duplicate paths, exceeding configured bounds, stale
artifacts and changes to HEAD during the scan fail the command.

## Initial baseline

A non-truncated GitHub recursive-tree read of `main` on 2026-10-13 returned
58,930 blob entries and 1,793 tree entries. By Git blob identity, 5,959
duplicate groups included 19,288 paths. Some are intended snapshot copies,
not redundant active code. This observation is **not** a deletion recommendation.
The atlas workflow will recompute counts against its own pinned HEAD commit.

## Phase boundary

Batch 1 = complete structural inventory, canonical-zone placement, path-family
grouping, exact duplicates, deterministic provenance, tests and CI publication.

Batch 2 = semantic features/symbol graph, cross-file dependency and runtime UI
edges, provenance-backed near-duplicate suggestions, progressive retrieval and
approved move plans. These must reuse the canonical repo-machine and
Jeeves execution boundaries; no separate runtime authority is permitted.

The atlas never renames, deletes, rewrites or consolidates code. Every such
change requires a reviewed impact plan, backward-compatibility assessment,
focused regression validation and rollback evidence.
