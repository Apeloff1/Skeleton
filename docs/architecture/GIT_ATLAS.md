# Git Atlas — exhaustive, low-context repository inventory

This is a read-only derived view of the canonical repository machine (machine/ and .machine/repository.toml). It is not another runtime or ownership authority. It complements the bounded working-tree scanner, which may report truncation.

## Run

    python -m skeleton.repo_machine.git_atlas --root . --output .machine/git-atlas

The outputs derive from checked-out HEAD, not dirty/untracked content:

- summary.json — exact commit/tree IDs, counts by canonical zone and provisional feature key, exact-duplicate counts, manifest SHA-256 checksums.
- files.jsonl — one record per tracked path including mode, Git blob SHA, byte size, owning zone and provisional feature.
- exact-duplicates.json — groups of identical Git blobs; equal bytes do not imply that a path can be deleted.

The GitHub Actions workflow repository-git-atlas.yml runs on every PR, push to main, nightly, and manual dispatch, publishing commit-scoped artifacts.

## AI context selection

1. Read the summary and resolve the canonical ownership zone.
2. Filter the JSONL inventory to the requested feature.
3. Use the existing repository-machine code search, symbol/reference, dependency, and impact indexes for source-level navigation.
4. Retrieve only necessary code spans at the same Git commit.
5. Before editing or moving, assess imports, runtime entry points, tests, installers, CI, platform support, and ownership contracts.

Feature keys are provisional path-derived navigation keys, NOT stable logical capability IDs. Never assume they survive file moves; later milestones must introduce a verified stable feature registry.

## Duplicate governance

Classify duplicate paths by canonical, support, transitional, or historical lifecycle. Compare runtime reachability and platform-specific behavior before proposing consolidation. Preserve historical snapshots, evidence, and generated builds unless a separate approved retention policy authorizes changes.

Near-duplicate detection is not yet delivered by this artifact. It requires normalization/AST analysis, bounded source reads and false-positive review. Future near-duplicate findings must remain suggestions, never automatic deletions.

## Fail-closed guarantees

- Reject malformed Git records, unsupported modes, duplicates paths, excessive response bounds, and wrong repository roots.
- Gitlinks remain opaque. Symlinks are indexed as blobs and their targets are never traversed.
- Index outputs are disposable and non-authoritative; rebuild them when commit IDs or checksums disagree.
- Scanner does not invoke model providers, execute repository code, mutate Git, or move files.

## Milestones

- [x] Complete HEAD-pinned Git metadata inventory and exact-blob duplicate reporting, implementation committed
- [x] Canonical zone and provisional feature classification, implementation committed
- [x] Deterministic summary, JSONL output and checksums, implementation committed
- [x] Focused regression tests and automatic workflow, implementation committed
- [ ] First CI run verified and all regressions resolved
- [ ] AST/normalized near-duplicate analysis with reviewed confidence
- [ ] Stable feature IDs and runtime/UI/API/test mappings
- [ ] Incremental reindexing, approved move plans and rollback
