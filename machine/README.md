# Machine Integration Map

This directory is the stable machine-facing index for Skeleton.

## Assembly model

The target is **one coherent application**, organized for both human maintenance and automated machine/agent operation.

The active assembly branch is `integration/app-consolidation`. It is the workspace where distinct capabilities are combined before promotion to `main`.

## Discovery order

1. Read `machine/manifest.json`.
2. Inspect runtime dependencies in `requirements.txt` and `requirements-dev.txt`.
3. Treat `skeleton/kernel` as foundational primitives.
4. Treat `skeleton/config`, `retrieval`, `vault`, and `observability` as domain services.
5. Treat `skeleton/agents` as the orchestration/runtime layer.
6. Treat `skeleton/testing` as the validation layer.
7. Inspect `.github` for CI and automation contracts.
8. Group new functionality by domain package, never by branch name.

## Machine rules

- Make small, deterministic, domain-scoped changes.
- Prefer existing interfaces over parallel implementations.
- Keep imports dependency-light and avoid unnecessary root-level coupling.
- Run targeted tests after each integration unit.
- Update the manifest when architecture or entrypoints change.
- Update this README when the assembly workflow or machine contract changes.
- Preserve branches containing unique commits until their useful changes have been integrated or explicitly retired.

## Integration ledger

- **PR #1701 — merged:** `fix/bot-manager-runtime-deps`; runtime dependency repair integrated into the assembly branch.
- **PR #1702 — queued:** `feat/automerge-control-plane-20260919`; 19 files / 9,605 additions staged into the assembly branch at file level because the source branch diverged from the assembly tip.
- Integrated domain: automerge control plane, including workflow automation, policy/evidence/ledger/model/stack modules, CLI/GitHub adapter, contract checks, and tests.
- Stale branch normalization remains at **40** validated tips; unique-commit branches remain preserved for review.

## Target layout

```text
Skeleton/
├── machine/              # machine-readable map and automation contract
├── skeleton/
│   ├── kernel/           # foundational primitives
│   ├── config/           # configuration
│   ├── agents/           # orchestration and agent runtime
│   ├── retrieval/        # retrieval/ranking/fusion
│   ├── vault/            # access/security primitives
│   ├── observability/    # telemetry
│   ├── pr_automation/    # repository automation and merge control
│   └── testing/          # validation infrastructure
├── docs/                 # architecture and human documentation
├── scripts/              # machine checks and maintenance scripts
└── .github/              # CI/repository automation
```

The map is intentionally updated as integration proceeds so automated workers can rediscover the current structure without relying on conversational context.
