# Repository Atlas

This is the human navigation companion to `.machine/repository.toml`. It
describes the intended shape of the repository without moving stable runtime
paths merely for cosmetic uniformity.

The machine view is generated from the live checkout:

```bash
python -m skeleton.repo_machine.cli --atlas
```

## Canonical tree

```text
Skeleton/
├── .machine/                 machine placement/ownership policy
├── machine/                  durable machine contracts, evidence and plans
├── .github/                  hosted CI, merge policy and repository automation
├── skeleton/                 canonical Python application/runtime namespace
│   ├── ai/                   AI runtime, providers, learning, research
│   ├── providers/            canonical provider-neutral contracts
│   ├── app/                  whole-application assembly/operator surface
│   ├── bootstrap/            engine startup and subsystem wiring
│   ├── kernel/               foundational primitives
│   ├── core/                 core runtime services
│   ├── foundation/           foundational cross-cutting primitives
│   │   └── architecture/     canonical architecture index + round history
│   ├── contracts/            stable internal contracts
│   ├── automation/           autonomous control-plane implementation
│   ├── agents/               agent runtime/orchestration
│   ├── jeeves/               Jeeves assurance/reasoning planes
│   ├── shells/               policy-bound execution plane
│   ├── memory/               runtime memory
│   ├── retrieval/            retrieval/ranking/fusion
│   ├── security/ + vault/    trust, policy and authorization
│   ├── state/ + persistence/ durable state/storage
│   ├── kv/                   paged/tiered KV-cache control plane
│   ├── native/                native execution + accelerator registry
│   ├── observability/        telemetry and diagnostics
│   ├── build/ + forge/       build/construction systems
│   │   ├── creator/          intent compiler + reversible design edits
│   │   └── pipelines/        content/game generation pipelines
│   ├── release/ + deploy*/   delivery lifecycle
│   ├── simulation/ + game/   simulation/game runtime
│   │   └── platform/         engine adapter boundary (Godot)
│   ├── world/                deterministic world/scene state
│   ├── frontier/             frontier gameplay/product runtime
│   │   ├── runtime/          contracts, execution, streams, memory/control plane
│   │   ├── progression/      achievements, quests, reputation, passes/meta systems
│   │   ├── ecology/          aquarium, bait, biotope, breeding + adapters
│   │   ├── economy/          commerce, cooking, crafting, energy, equipment
│   │   ├── characters/       NPC generation, adapters and archetype profiles
│   │   └── game/             gameplay orchestration, ship and world systems
│   ├── repo_machine/         live repository model and atlas
│   ├── pr_automation/        PR/merge control
│   ├── repo_intelligence/    repository analysis
│   └── testing/              reusable/integration test infrastructure
├── backend/                  backend API/product control plane
├── frontend/                 browser/mobile product shell
├── tests/                    repository-level regression/contract tests
├── eval/                     evaluation fixtures/surfaces
├── scripts/                  CI/local validation and operations tooling
├── packaging/                installers and packaging
├── docs/                     human architecture, policy, plans and runbooks
├── memory/                   project/session memory; not runtime authority
├── complete/                 transitional imported/staged source material
└── satellites/               transitional satellite/source material
```

## Placement rules

1. Put new canonical runtime code under an existing `skeleton/<domain>/`
   surface whenever a matching domain already exists.
2. Put machine-readable durable contracts in `machine/`; put repository
   taxonomy/policy in `.machine/`. Do not mix those two roles.
3. Put human explanations, architecture, runbooks and plans in `docs/`.
4. Reuse `tests/` or `skeleton/testing/`; do not create a third test root.
5. Reuse `scripts/` for repository tooling; runtime libraries belong under
   `skeleton/`, not under scripts.
6. `complete/`, `satellites/`, and `skeleton/acquired/` are transitional
   source surfaces. Copying from them does not make the copy canonical unless
   the receiving domain and tests are explicit.
7. `memory/` is project memory/evidence, not an importable runtime namespace.
   Runtime memory belongs in `skeleton/memory/`.
8. New top-level directories require a zone, owner, purpose, audience and
   lifecycle entry in `.machine/repository.toml` in the same change.
9. Preserve compatibility imports during moves. Prefer staged extraction and
   shims over tree-wide rename bursts.
10. Generated machine snapshots are normally ephemeral. Commit them only when
    another evidence/provenance contract explicitly requires a durable artifact.

## Lifecycle meanings

| Lifecycle | Meaning | Placement rule |
| --- | --- | --- |
| `canonical` | Preferred long-term home | New domain work may land here |
| `support` | Maintained supporting surface | Expand only when the support role is explicit |
| `transitional` | Migration/import/staging surface | Do not grant new runtime authority silently |
| `historical` | Provenance/reference only | No new active implementation |

## Machine discovery

Agents should read the atlas before broad code search. The live atlas contains
zone ownership, criticality, purpose, audience, lifecycle, prefixes, file/test
counts, dependency edges and any unclassified roots. For a proposed new path,
`placement_for_path()` applies the same first-match policy as the repository
model.

The important invariant is **one navigable repository, two views**: humans get
a stable conceptual tree; machines get the same taxonomy plus live topology and
counts.


## Active namespace migrations

The first consolidation wave is now structured around canonical source plus
compatibility shims:

| Legacy import surface | Canonical source | State |
| --- | --- | --- |
| `skeleton.deployment.*` | `skeleton.deploy.strategies.*` | transitional shim |
| `skeleton.contexts.*` | `skeleton.context.domains.*` | transitional shim |
| `skeleton.application.*` | `skeleton.app.runtime.*` | transitional shim |
| `skeleton.persist.*` | `skeleton.persistence.core.*` | transitional shim |
| `core.shift_supervisor.*` | `skeleton.automation.shift_supervisor.*` | transitional shim |
| `core.activation_security` | `skeleton.security.activation_security` | transitional shim |
| `skeleton.architecture_index` | `skeleton.foundation.architecture.index` | transitional shim |
| `skeleton.architecture_round*` | `skeleton.foundation.architecture.rounds.round*` | transitional shim |
| `skeleton.jvm_accelerators` | `skeleton.native.jvm_registry` | transitional shim |
| `skeleton.genesis` | `skeleton.bootstrap.genesis` | transitional shim |
| `skeleton.provider_contract` | `skeleton.providers.contract` | transitional shim |
| `skeleton.kv_cache` | `skeleton.kv` | transitional shim |
| `skeleton.platform.*` | `skeleton.simulation.platform.*` | transitional shim |
| `skeleton.pipelines.*` | `skeleton.forge.pipelines.*` | transitional shim |
| `skeleton.creator.*` | `skeleton.forge.creator.*` | transitional shim |
| `skeleton.frontier.{agent_runtime,contracts,events,...}` | `skeleton.frontier.runtime.*` | transitional module shims |
| `skeleton.frontier.{achievements,quests,reputation,...}` | `skeleton.frontier.progression.*` | transitional module shims |
| `skeleton.frontier.{aquarium,bait,biotope,breeding,...}` | `skeleton.frontier.ecology.*` | transitional module shims |

New code should use the canonical namespaces. Compatibility surfaces stay
readable until reference audits and downstream migrations prove they can be
removed safely.
