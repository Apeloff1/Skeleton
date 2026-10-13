# Whole-repository navigation index and consolidation queue

**Purpose:** Let Jeeves, maintenance agents and human contributors navigate the **entire** Git-tracked application without loading every file into model context. The authoritative ownership contracts remain `machine/architecture.json`, `machine/ai_file_tree.json`, and `.machine/repository.toml`. This is a **read-only, versioned projection**, not a second owner or a permission bypass.

## Source and reproducibility

The index walks `git ls-tree -r -l -z HEAD` at an exact SHA rather than an OS directory walk. It therefore includes canonical implementation, metadata, binary assets, compatibility facades, historic satellites and snapshots, tracked generated artifacts and tests. Entries remain accessible even when they are excluded from the existing code-search scorer. No code execution or source modification occurs during indexing. SHA identities are Git blob identities (not SHA-256); output file digests are SHA-256.

Build locally at the target commit:

```sh
python scripts/build_repository_navigation_index.py --root . \
  --output .machine/repository-navigation --near-limit 2500
python scripts/build_repository_navigation_index.py --root . \
  --output .machine/repository-navigation --query 'jeeves workbench' \
  --context-bytes 8000
python -m unittest discover -s tests -p 'test_repository_navigation_index.py' -v
```

The `repository-navigation-index.yml` workflow refreshes on every `main` push, nightly, or manual dispatch, validates its HEAD binding and 100% Git-tree path coverage, and publishes versioned artifacts. It has **read-only GitHub permissions**. It does not commit volatile generated index changes to `main` or silently delete code. The stable code and workflow live in the repository; complete generated data lives in build artifacts, in `.machine/repository-navigation` on local builds. The existing `repo-machine-index.yml` remains the canonical richer static and symbol index; generated files under `.machine` are never counted as tracked source unless explicitly committed.

## Layers — small context first

| Layer | Artifact | AI retrieval purpose |
| --- | --- | --- |
| L0 | `summary.json` | Source revision, counts, index list, integrity digests, root-level map |
| L1 | `zones.json` | Canonical machine zone, owner and lifecycle aggregates |
| L1 | `features.json` | Functional file-tree clusters, role and zone populations |
| L1 | `directories.json` | Every tracked directory with subtree and direct file counts |
| L2 | `files.jsonl` | Every exact tracked file path, blob identity, bytes, group, role, lifecycle |
| L2 | `exact-duplicates.json` | All shared Git blob identities and the complete set of paths per identity |
| L2 | `near-duplicates.json` | Content-verified similarity candidate pairs, method and deferred-candidate count |
| L3 | Existing `repository-machine.json`, `code-search-index.json` | Scoped imports, symbols, line locations, relationships and testing evidence |
| L4 | Actual source files | Fetch only SHA-bound file(s) relevant to the proposed edit |

The query CLI emits only bounded metadata hits, never source bodies. For a file edit, fetch the actual file from the **same commit**; the retrieval index is not sufficient evidence to modify code.

The navigation projection groups paths into existing machine zones, owners and lifecycles, plus discoverable feature paths. Path grouping is a *navigation heuristic*, not architecture authority. A discovered feature is not necessarily a working runtime feature. `unclassified` is reported explicitly, never silently assigned.

## Duplication methodology and safety

1. **Exact** means same Git blob SHA; compatible with cross-directory duplicates and binary files. It does not prove identical role, legal retention obligations or safe deletion. Empty files count too.
2. **Near** begins with a bounded same-filename, nearby-size candidate search over text source. Candidate bodies are fetched by blob ID and compared with token four-gram Jaccard similarity. Similarity never means contract equivalence. Only content-verified matches appear in the match list. The candidate search is deliberately bounded and non-exhaustive; its deferred count must be visible. Different-name near duplicates, advanced semantic equivalences and minified/format-transformed code require a separate AST/symbol/embedding review, not an invented assurance claim.
3. Mirror/facade candidates in `skeleton/ai/*`, `skeleton/repo_machine/*`, and historic `satellites/*` must be resolved against `machine/ai_file_tree.json`, explicit parity and import constraints, not basename alone.
4. No automatic move, deletion or imports rewrite occurs. Any consolidation uses **plan -> owner approval -> dependency/import inventory -> two-way compatibility tests -> staged move -> rollback -> independently verified signoff**.

## Proposed reorganization sequence

1. **Inventory and partition**: ensure no tracked path is omitted, group by `zone`, `feature`, `role`, `lifecycle`, and Git identity; keep historical `satellites` separate from live implementations.
2. **Authority resolution**: consult architecture and AI migration mappings; name canonical owners, compatibility adapters, quarantined acquisition and intentional test fixtures.
3. **Duplicates**: triage exact copies first, then verified near candidates, then structural/semantic overlaps. Rank by byte/cognitive cost and dependency risk rather than file count alone. Retain evidence and tombstones before any removal.
4. **Feature-level migration**: choose one feature boundary per PR; build reversible redirects/facades, update imports, docs, tests, workflows, and runtime construction manifests. No unverified mass deletion.
5. **Invariants**: require App Assembly, architecture/AI-tree checks, security gates, relevant language tests and exact-head CI before signoff. A failed gate is a blocker, not a completed move.

**Known baseline (2026-10-12 `main` commit `e4dce36df30ad934d2d8a9fa92ec84c9c943d2ca`):** 58,930 tracked blobs across 1,793 Git tree directories; 5,959 exact shared-blob groups with 13,329 extra copies; 11,732 files under `satellites/`. These baseline figures come from the Git recursive tree, not from the new workflow (which must still execute at its own head). Do not claim near-duplicate totals until content has been compared in the runner.

## Caveats

This is full **tracked-tree** coverage, not a census of ignored/untracked local cache or external service data. A feature's actual use and self-improvement authority are governed by runtime contracts, not by mere index inclusion. The pre-existing `.machine/repository.toml` `max_files = 50000` scanner limit is insufficient to guarantee coverage of the current 58,930-file tracked tree; the new lightweight all-path index exists to close that visibility gap independently, and the richer scanner must be separately profiled before its limit can be raised safely.
