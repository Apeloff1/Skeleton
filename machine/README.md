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

- **Reconcile-wave audit:** #1848–#1865 revalidated; existing integration PRs reused with no duplicate staging.

- **File-level reconciliation:** network replication and X-harness waves are already byte-for-byte present on the assembly branch; their open PRs remain lineage/source references rather than duplicate content.

- **Deep reconciliation:** physics stack and Jeeves semantic/compiler waves were inspected at file level; divergent core modules remain held rather than overwritten.
- **Physics aggregate:** 77-file wave remains held due overlap with the consolidated simulation stack.

- **Physics family audit:** 11 candidate branches rechecked; core CCD/convex/collision/world modules diverge across branches, so the family remains held for semantic consolidation.

- **Large-wave audit:** PR runner hygiene #1867 staged; bounded-shell and shell-AI 300-file waves remain held for reconciliation.

- **Latest staging wave:** machine gates, safe-1669, merge-unblockers, live-service boundaries, Jeeves decision drain, and shell-live gates are staged as integration PRs; large overlapping waves remain held for reconciliation.

- **Semantic/domain wave:** Jeeves semantics, repository bots, security evidence, Java observability/retrieval, and role studios revalidated against assembly; existing integration PRs reused.

- **Frontier/Java/machine wave:** revalidated galaxy, Java accelerator/control/observability, Jeeves decision/planning/frontier chains, and machine control-plane sources; existing integration PRs reused.

- **Orchestration/ops wave:** PR runner, provider/SMB resilience, cockpit, supervisor hierarchy/resilience, x-agent, and bot-ledger sources revalidated; existing integration PRs reused.

- **Security/fix wave:** 18 security, supervisor, workflow, shell, and hardening sources revalidated; existing integration PRs reused.

- **Throughput/science wave:** throughput mechanics/forge/pipeline, Ubuntu delivery, inventory gates, and Jeeves science/cost sources revalidated; zero-file model-routing remains lineage-only.

- **Control-plane/builder wave:** builder, repair receipts, durable checkpoints, squads, supervisor, backlog reasoning, and automerge sources revalidated; #1873/#1874 created for newly staged deltas.

- **Security/reliability contracts:** repair intake, repo contracts/bots, archive/import safety, and secret-scan sources revalidated; existing integration PRs reused. Three older branch comparisons need another pass.

- **Security resolution wave:** deserialization, token parsing, content-type, scraper DNS/SSRF, CORS, vault atomicity, and scan-evidence branches revalidated; zero-file SAST traversal branch remains lineage-only.

- **Automation/CI wave:** revalidated action runners, queue pressure, reconciliation, branch control, CI hygiene, bot ledger, CodeQL, Dependabot, frontier push coalescing, and housekeeping sources; existing integration PRs reused.

- **Reconciliation wave:** revalidated repo-bot, security-evidence, physics, network/X-harness, and Jeeves semantic/science sources; game-replay, quality, character-motor, and model-routing zero-file deltas remain lineage-only.

- **Feature wave:** staged ASM vector microkernel as new PR #1875 and revalidated automation, builder, supervisor, squad, Java, and retrieval sources; existing integration PRs reused, zero-file deltas retained as lineage.

- **Jeeves/frontier wave:** revalidated decision, planning, evidence, frontier reasoning, machine control, recovery, pack, runner, provider, SMB, and cockpit sources. Large topology-learning and PR-runner-hygiene waves remain held for reconciliation.

- **Ops/throughput wave:** revalidated supervisor contracts, PR runner, provider/SMB resilience, cockpit tooling, throughput mechanics/pipeline, Ubuntu delivery, and x-agent orchestration; zero-file authority/observability branches remain lineage-only.

- **Held merge waves:** repo-machine-gates (115 files) and safe-1669 (150 files) revalidated; both remain staged for file-level reconciliation rather than blind merge.

- **Temporary branch lineage:** Java accelerator rebase temp branch is zero-file versus assembly; no duplicate integration created.

- **Archive lineage:** PR-runner and workflow-secret-output snapshots remain historical source material after revalidation; neither is treated as a merge target.

- **Backup lineage:** five recovery snapshots revalidated; all diverge materially from assembly and remain historical recovery/source material, not merge targets.

- **Stabilization wave:** audited 38 shell stabilization branches; most are zero-file lineage. New PR #1876 stages shell orchestration (84 files). Three large 300-file waves remain held for reconciliation.

- **Reconcile wave:** revalidated 27 branches. Meaningful deltas are already staged in integration PRs; zero-file deltas remain lineage only.

- **Fix wave:** revalidated 15 current-main fix branches; meaningful deltas are already represented in integration staging, with no duplicate PRs created. One zero-file branch remains lineage only.

- **Feature wave:** revalidated 46 feature branches. Existing integration PRs cover meaningful staged deltas; zero-file branches remain lineage. Large shell, PR-runner, Jeeves topology, and physics families remain held for reconciliation.

- **Merge wave:** two merge snapshots audited; both are held for controlled reconciliation (115 and 150 files) rather than blindly merged.

- **Archive wave:** both historical snapshots revalidated; unique deltas remain available as recovery/source material and neither is a merge target.

- **Temporary branches:** `tmp/java-accelerator-operations-rebase-20260920` is zero-file lineage versus assembly; no integration action required.

- **Chore wave:** PR #1877 stages a distinct 4-file small backlog drain; the 0-file housekeeping runner remains lineage only.

## Target layout

```text
Skeleton/
├── machine/              # machine-readable map and automation contract
├── skeleton/
│   ├── app/              # canonical whole-application manifest/launcher
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
