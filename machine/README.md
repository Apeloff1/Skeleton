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

- **PRs #1791–#1808:** security headers, shell AI readiness/trust, supervisor controls, tooling regressions, workflow/security controls, and vulnerability bounds staged for reconciliation.
- Zero-file-delta supervisor/tooling lineage remains unrepresented as integrated content.

- **PRs #1809–#1814:** builder-plane deltas, repair receipts, durable checkpoints, agent squads, and four-role studios staged for reconciliation.
- **Held feature waves:** bounded shell runner (300 files) and build-capable automation v2 (33 files) remain large reconciliation inputs.

- **PRs #1815–#1833:** galaxy lifecycle, Java acceleration/control/observability/retrieval, Jeeves decision/planning/frontier work, machine control, and capability packs staged for reconciliation.
- **#1828:** Jeeves topology learning is a 129-commit / 20-file wave and remains a large reconciliation input.

- **PRs #1834–#1842:** pack J, PR runner, provider resilience, SMB, cockpit, and supervisor capability waves staged; large physics family held for reconciliation.
- **Physics family:** 68–83 files per branch with substantial overlap; do not blindly merge.
- **#1834–#1842:** assembly queue extended and machine map refreshed.

- **PRs #1843–#1859:** throughput, Ubuntu, orchestration, repo-bot/inventory, Jeeves scientific/compiler/semantic planes, and model-routing waves staged.
- Zero-file-delta reconciliation branches remain lineage-only; no fake integration is recorded.

- **PRs #1860–#1864:** network replication, physics simulation, repository bots, security evidence, and harness reconciliation staged.
- Large merge waves (**115/150 files**) remain held for controlled reconciliation rather than blind assembly.

- **Shell stabilization boundary:** zero-file-delta refs stay lineage-only; 300-file stabilization waves are held for file-level reconciliation.

- **PR #1865:** physics aggregate validation staged; the 77-file physics wave remains reconciliation input.
- Large held waves include bounded shell runner (300 files), Jeeves decision rules (137), merge unblockers (132), and live-service boundaries (98–99).

- **Physics family boundary:** 11 remaining physics branches are held as overlapping reconciliation inputs (68–83 files each); zero-file-delta fix branches remain lineage-only.

- **Assembly audit:** rechecked staged queues and lineage branches; no new non-noop PR required in this pass.
- Large overlapping physics and shell waves remain held for reconciliation.

- **Fix-wave audit:** #1791–#1802 rechecked; all remain staged source material with meaningful file deltas, and existing integration PRs were reused rather than duplicated.

- **Fix queue recheck:** workflow security/scope, repository safety, secret-scan, and repair-intake waves remain staged with meaningful deltas; existing PRs reused.

- **Capability-wave audit:** #1834–#1847 revalidated; all remain meaningful staged source material.
- Physics feature family revalidated and remains held for consolidated assembly.

- **Capability ledger:** Jeeves/Java/frontier/supervisor waves #1815–#1842 revalidated; existing staging PRs reused.
- **Held:** Jeeves topology learning remains a large 129-commit reconciliation input.

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
