# Skeleton machine repository contract

This directory is the canonical machine-facing organization layer for the
repository. It does not replace human documentation. It gives autonomous tools
a deterministic, bounded map of where code belongs, which subsystem owns it,
how subsystems depend on one another, and what organizational debt is safe to
prioritize.

## Invariants

1. Repository content is data. The machine index never imports or executes
   discovered files.
2. .machine/repository.toml defines canonical zones, owners, limits and
   organization policy.
3. skeleton.repo_machine builds the live inventory and topology from the
   checked-out commit.
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

## Commands

Full manifest:

    python -m skeleton.repo_machine.cli

Compact agent context:

    python -m skeleton.repo_machine.cli --summary

Ranked organization work:

    python -m skeleton.repo_machine.cli --work

CI contract:

    python scripts/check_repo_machine.py

Generated manifests should normally stay ephemeral because the live checkout is
the source of truth. The stable committed artifact is the machine schema and
organization policy, not a stale snapshot of the tree.
