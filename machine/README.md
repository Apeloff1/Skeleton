# Machine Integration Map

This directory is the stable machine-facing index for Skeleton.

## Assembly model

The target is **one coherent application**, organized for human maintenance and automated machine/agent operation.

The active assembly branch is `integration/app-consolidation`. Distinct capabilities are combined here before promotion to `main`.

## Discovery order

1. Read `machine/manifest.json`.
2. Inspect `requirements.txt` and `requirements-dev.txt`.
3. Treat `skeleton/kernel` as foundational.
4. Inspect `config`, `retrieval`, `vault`, and `observability` as domain services.
5. Treat `skeleton/agents` and `skeleton/automation` as orchestration/runtime layers.
6. Treat `skeleton/pr_automation` as repository automation and merge-control infrastructure.
7. Treat `skeleton/testing` as validation.
8. Inspect `.github` for CI/automation contracts.
9. Group functionality by domain package, never by branch name.

## Machine rules

- Make deterministic, domain-scoped changes.
- Prefer existing interfaces over parallel implementations.
- Keep imports dependency-light.
- Run targeted tests after each integration unit.
- Update manifest and README when structure or workflow changes.
- Preserve unique-commit branches until their useful changes are integrated or explicitly retired.
- Treat non-mergeable PRs as source material requiring reconciliation, not as merge commands.

## Integration ledger

- **PR #1701 — merged:** bot-manager runtime dependency repair.
- **PR #1702 — queued:** automerge control plane; 19 files / 9,605 additions.
- **File-level integrated:** backlog reasoning adapter and builder plane control.
- **PRs #1703–#1778:** staged integration queue covering build-capable automation, supervisor control, workflow/queue controls, security hardening, Jeeves domains, physics, PR automation, and merge-readiness contracts. These remain source/staging material; non-mergeable items are not blindly merged.
- **PR #1763:** canonical owner queue drain variant.
- **PR #1764:** 132-file merge-unblocker reconciliation wave.
- **Large held waves:** live-service test boundaries (98/99 files), merge-unblockers (132), Jeeves decision rules (137), Jeeves frontier core (57), main-gates shell-live (67), physics aggregate validation (77).
- Stale branch normalization remains at **40** validated tips.

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
├── docs/                 # architecture and human documentation
├── scripts/              # machine checks and maintenance scripts
└── .github/              # CI/repository automation
```

The map is updated during assembly so automated workers can rediscover the current structure without relying on conversational context.
