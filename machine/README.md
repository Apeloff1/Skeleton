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

## Branch integration

The branch sweep has already normalized stale branch tips that contained no commits absent from `main`. Diverged branches remain available as source material.

Current integration work includes PR #1701 from `fix/bot-manager-runtime-deps`; GitHub currently reports that integration PR as not mergeable, so it remains queued for conflict resolution rather than being forced.

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
│   └── testing/          # validation infrastructure
├── docs/                 # architecture and human documentation
└── .github/              # CI/repository automation
```

The map is intentionally updated as integration proceeds so automated workers can rediscover the current structure without relying on conversational context.
