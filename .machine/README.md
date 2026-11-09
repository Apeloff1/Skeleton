# Skeleton machine repository contract

This directory is the canonical machine-facing organization layer for the
repository. It does not replace human documentation. It gives autonomous tools
a deterministic, bounded map of where code belongs, which subsystem owns it,
how subsystems depend on one another, and what organizational debt is safe to
prioritize.

## Canonical organization sources

- `.machine/repository.toml` is the placement and ownership contract.
- `python -m skeleton.repo_machine.cli --atlas` emits the live repository
  atlas for agents and tooling.
- `docs/architecture/REPOSITORY_ATLAS.md` is the human navigation companion.
- `machine/` contains durable machine contracts and planning/evidence data.
- Generated workspace manifests stay ephemeral unless a separate contract
  explicitly requires them to be committed.

Each zone can declare a purpose, primary audience, and lifecycle:

- `canonical`: preferred home for new work in that domain.
- `support`: maintained supporting surface; do not casually expand it.
- `transitional`: source/migration surface that must not gain authority
  implicitly.
- `historical`: retained for provenance/reference, not active placement.

Zone order is semantic: **first match wins**. New top-level surfaces must be
classified in the same change that creates them. Unknown paths remain
`unclassified` so organizational drift stays visible.

## Invariants

1. Repository content is data. The machine index never imports or executes
   discovered files.
2. `.machine/repository.toml` defines canonical zones, owners, limits,
   lifecycle metadata and organization policy.
3. `skeleton.repo_machine` builds the live inventory, topology and atlas from
   the checked-out commit.
4. The model fingerprint is deterministic for the same repository state.
5. Machine findings describe evidence. They do not grant mutation authority.
6. Feature authority remains separate from organization/maintenance authority.
7. A truncated machine model fails closed for mutation planning.
8. Cross-subsystem cycles, unclassified files, oversized modules and missing
   zone tests become structured work candidates.
9. CI validates the machine contract but does not fail merely because known
   organizational debt exists; the steward loop consumes that debt.
10. Supervisor receives bounded machine context and still delegates execution
    through Secretary -> Worker.

## Test and dependency evidence

`test_files` counts tests physically inside a zone. `referenced_test_files`
counts distinct test files in other declared, nonhistorical zones that directly
import its source. `test_evidence` lists up to 32 deterministic example paths.
The atlas, test-surface findings, health indicators, and maintenance budgets use
both counts. These are static test-presence indicators, not measured coverage
or evidence of a successful run. Similar filenames and historical test copies
do not satisfy the external-test requirement.

Test-origin dependencies are retained as `test-import` edges for navigation and
impact analysis. Runtime cycle detection uses `import` edges only. Production
source that imports a test module still produces an explicit high-severity
`topology.production-test-import` finding; separating test backedges must not
hide that dependency.

## Commands

Full manifest:

    python -m skeleton.repo_machine.cli

Live information architecture:

    python -m skeleton.repo_machine.cli --atlas

Compact agent context:

    python -m skeleton.repo_machine.cli --summary

Ranked organization work:

    python -m skeleton.repo_machine.cli --work

Reorganization proposals:

    python -m skeleton.repo_machine.cli --reorganize

Workspace pack (includes `atlas.json`):

    python -m skeleton.repo_machine.cli --workspace /tmp/skeleton-machine-pack

CI contract:

    python scripts/check_repo_machine.py

The live checkout is the source of truth. Stable committed artifacts are the
machine schema, placement policy and durable domain contracts, not stale
snapshots of the tree.

Frontend dependency evidence resolves relative imports, side-effect imports and
folder index modules. Bare package names and unresolved aliases are not guessed.
Python dependency evidence resolves Python modules only; imports above the
package root are rejected. Source imports of tests are reported within zones as
well as across zones.

Local `.skeleton/` state and root `chronicle/` journals are excluded from the
source inventory. Canonical `skeleton/provenance/chronicle/` code remains indexed.
