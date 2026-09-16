# B001 — frontier freshness and relationship fidelity

## Intent

Advance B001 (Repository intelligence spine) by making the frontier index self-validating at read time and lossless for relationship metadata variants.

## Changed behavior / paths

- `scripts/repo_intel_frontier.py`
  - adds a content-aware tracked-workspace fingerprint built from the Git index tree, tracked status, and content hashes for unstaged changed files;
  - refuses to publish a mixed snapshot if tracked state changes during indexing;
  - automatically rebuilds schema-5 snapshots when the fingerprint changes or required companion outputs are missing;
  - preserves distinct edge metadata variants rather than collapsing all relations sharing only `(from,to,type)`;
  - preserves relation metadata on reverse edges;
  - reports relationship metadata variants and fingerprint verification in index metrics/notes/doctor output.
- `repo-intel/deep-index-contract.json`
  - codifies cache-freshness and relationship-fidelity invariants.
- `tests/test_repo_intel_frontier.py`
  - adds regressions for self-refresh, missing companion outputs, metadata-variant preservation, and contract semantics.

## Validation evidence

Focused tests are wired into the existing Repository Intelligence workflow (`tests/test_repo_intel_frontier.py`). GitHub Actions validation for the latest shared branch head is authoritative; superseded runs may be cancelled by PR concurrency as additional commits land.

## Security impact

Positive/neutral. The fingerprint records hashes/status only and does not emit environment values or secrets. It hashes only tracked changed files; untracked files remain outside the repository index until explicitly added to Git. Mixed-state snapshots fail closed instead of silently publishing inconsistent security/build relationships.

## Quality / performance impact

Read-time freshness adds one fast Git index-tree/status check and content hashing only for unstaged tracked files. Clean-tree queries avoid reparsing and continue to reuse the content-addressed semantic cache. Relationship fidelity increases graph accuracy by preserving distinct dependency scopes/specifications and build metadata.

## Dependency / Dependabot impact

No new runtime or development dependency. Implementation remains Python 3.11 standard-library only. Dependabot configuration is unchanged.

## Architecture / supply-chain / runtime-surface effect

Supply-chain graph evidence can no longer lose separate relation variants solely because they share endpoints and relation type. Runtime/build/search companion outputs are required for cache reuse, so route/env/hotspot/batch queries cannot silently operate on a partial snapshot.

## Remaining noticeable gaps / next augmentation

- Persist and validate richer test-evidence links (test selection confidence, historical execution evidence) rather than relying mainly on structural candidate tests.
- Add artifact lineage nodes from source/generated inputs through release outputs.
- Add base-snapshot storage for true semantic graph diffs of deleted historical edges.
- Consider compiler/SCIP ingestion for JS/TS precision while retaining the current dependency-free fallback.
