# Machine Integration Map

Stable machine-facing index for Skeleton.

## Assembly model

Target: **one coherent application** for human maintenance and automated machine/agent operation. Active assembly branch: `integration/app-consolidation`.

## Discovery order

1. Read `machine/manifest.json`.
2. Inspect runtime dependencies.
3. Treat `skeleton/kernel` as foundational.
4. Inspect config/retrieval/vault/observability as domain services.
5. Treat agents/automation as orchestration/runtime.
6. Treat `skeleton/pr_automation` as repository automation and merge control.
7. Treat testing as validation.
8. Inspect `.github` contracts.
9. Group functionality by domain, never by branch name.

## Machine rules

- Make deterministic, domain-scoped changes.
- Prefer existing interfaces and dependency-light imports.
- Run targeted tests after each integration unit.
- Update this map as assembly changes.
- Preserve unique-commit branches until reviewed.
- Non-mergeable PRs are reconciliation source material, not blind merge targets.

## Integration ledger

- **#1701 merged:** bot-manager runtime dependency repair.
- **#1702–#1778 staged:** automation, supervisor, security, Jeeves, physics, PR automation and merge-readiness waves.
- **#1779–#1790 newly staged:** repair-intake, repo-attention, repo-bots permissions, contract drain, archive/dynamic-import safety, and secret-scan contracts.
- **#1764:** 132-file merge-unblocker reconciliation wave.
- **Large held waves:** live-service boundaries (98/99), Jeeves decision rules (137), Jeeves frontier core (57), main-gates shell-live (67), physics aggregate validation (77).
- **40** stale branch tips validated and normalized.

## Target layout

```text
Skeleton/
├── machine/              # machine-readable map and automation contract
├── skeleton/
│   ├── kernel/           # foundational primitives
│   ├── config/           # configuration
│   ├── agents/           # orchestration and agent runtime
│   ├── automation/       # builder/supervisor/reasoning automation
│   ├── retrieval/        # retrieval/ranking/fusion
│   ├── vault/            # access/security primitives
│   ├── observability/    # telemetry
│   ├── pr_automation/    # repository automation and merge control
│   └── testing/          # validation infrastructure
├── docs/
├── scripts/
└── .github/
```

The map is updated during assembly so automated workers can rediscover the current structure without conversational context.
