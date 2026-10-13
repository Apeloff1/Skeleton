# Git-tree indexing supplement to the canonical Repository Atlas

Authority: `.machine/repository.toml` (zone owner), `machine/ai_file_tree.json`
(existing AI migration identity), `machine/architecture.json` (runtime plane).
This is an **unprivileged, read-only index**, not a new runtime service.
See also [the existing repository atlas](REPOSITORY_ATLAS.md).

## Build, verify, search

```bash
python -m scripts.build_repository_atlas build --output /tmp/skeleton-atlas --near-limit 600
python -m scripts.build_repository_atlas verify --output /tmp/skeleton-atlas
python -m scripts.build_repository_atlas query --output /tmp/skeleton-atlas --text "jeeves quest editor" --budget 2500
python -m unittest tests.test_repo_tree_atlas -v
```

The pinned Git tree is the file source of truth, rather than a capped
filesystem walk. All tracked blobs, symlinks, and opaque gitlinks are
indexed. No files are imported, executed, followed, moved or deleted.

| Artifact | Contract |
| --- | --- |
| `manifest.json` | Pinned commit and tree, complete inventory digest, zone and feature counts |
| `files.jsonl` | Every tracked file, blob ID, mode, size, owner, feature and lifecycle |
| `features.jsonl` | Group totals and representative paths for every known or provisional feature ID |
| `directories.jsonl` | Entire hierarchical file tree with recursive file/byte totals |
| `exact_duplicates.jsonl` | Same-Git-blob content groups; no deletion inference |
| `near_duplicates.json` | Bounded same-stem token-shingle comparisons; **not exhaustive** |

A query reads the index, checks the current Git HEAD and full inventory digest,
returns only paths, Git blob IDs, owners and feature labels within a byte budget.
Fetch selected code ranges through the existing governed readers afterward.

### Duplication and organization safety

The 2026-10-13 main-tree census observed 58,930 blobs, 1,793 tree
directories, 5,959 content-duplicate groups, and 13,329 excess identical
file copies. These are snapshot measurements, not automatically deletion-safe
redundancy. Files in `satellites/branch-snapshots` are immutable historical
material. Mirrors under `skeleton/ai` remain controlled by explicit migration
parity and compatibility rules.

Near-duplicate results are *unreviewed candidates* and initially compare
only same-stem, same-extension canonical code, within a bounded blob budget.
Different-name semantic duplicates, AST equivalence, or runtime substitutability
are not proven by this pass. Every physical move must be validated against
imports, runtime registration, tests, CI, rollback, and migration contracts.

### Automatic regeneration

`.github/workflows/repository-atlas.yml` rebuilds on PRs, pushes to main,
and manual dispatch, runs regression tests, verifies the inventory independently,
and publishes an ephemeral artifact. Artifacts are derived state, not source
authority or growing committed indexes.

### Subsequent milestones

1. Expand the feature atlas with symbols, routes, UI bindings, tests and
   cross-language dependency/reverse-dependency associations using
   `skeleton/repo_machine` and `skeleton/repo_intelligence`.
2. Extend near duplicates with normalized AST, cross-filename candidate
   discovery, benchmarked precision, and human disposition workflows.
3. Generate proposed moves and staged compatibility cutovers only after
   graph-boundary verification and rollback manifests are in place.

Jeeves receives **navigation rights only** from these derived indexes.
Execution remains governed by Supervisor → Secretary → Worker authority.
