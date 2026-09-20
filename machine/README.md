# Machine Integration Map

This directory is the stable machine-facing index for Skeleton.

## Discovery order

1. Read `machine/manifest.json`.
2. Inspect `requirements.txt` and `requirements-dev.txt`.
3. Treat `skeleton/kernel` as foundational primitives.
4. Treat `skeleton/agents` as the orchestration/runtime layer.
5. Treat `skeleton/testing` as the validation layer.
6. Keep application features grouped by domain package rather than branch name.

## Integration branch

`integration/app-consolidation` is the assembly branch for consolidating functionality from the surviving feature branches before promotion to `main`.

## Automation contract

Agents should make small, domain-scoped changes, run the relevant tests, and update the manifest when adding a new top-level subsystem.
