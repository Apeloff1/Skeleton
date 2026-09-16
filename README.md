# Tutolage Skeleton v16

AI game engine and agent orchestration framework.

## Quick Start

```bash
# Boot the full system
python -m skeleton run

# Developer CLI
python -m skeleton dev scaffold my-agent --template minimal-agent
python -m skeleton dev wizard
python -m skeleton dev health

# Run tests
python -m skeleton test

# Map the current repository/build surface before making changes
make repo-intel
```

## Architecture

7-phase boot protocol:
1. **kernel** — EventBus, EntropyPool, VectorClock, InvariantLattice
2. **memory** — RAG, CAG, MAG, Trinity, DreamEngine, DriftDetector
3. **intelligence** — Orchestrator, AdaptiveLearner
4. **swarm** — SwarmMesh, PheromoneField, HiveMind, Platoons
5. **resilience** — ResilienceFortress, CanaryRegistry
6. **interface** — AnomalyDetector, ProvenanceLedger, Reranker, QuadRetriever
7. **cortex** — JeevesCortex (observes the whole bus)

## Subsystems

| Package | Purpose |
|---------|---------|
| `skeleton.kernel` | Core primitives and error types |
| `skeleton.memory` | Multi-plane retrieval and storage |
| `skeleton.intelligence` | Reasoning and adaptive learning |
| `skeleton.swarm` | Multi-agent coordination |
| `skeleton.forge` | Blueprint-based system composition |
| `skeleton.resilience` | Security and fault tolerance |
| `skeleton.observability` | Metrics and anomaly detection |
| `skeleton.api` | REST API surface |
| `skeleton.cortex` | Observability hub |
| `skeleton.developer` | Developer CLI and scaffolding |
| `skeleton.deploy` | Deployment harness |
| `skeleton.testing` | Test framework |
| `skeleton.organism` | Runtime state and feature flags |
| `skeleton.pipelines` | High-level task pipelines |
| `skeleton.vault` | Access control and encryption |
| `skeleton.retrieval` | Search and fusion |
| `skeleton.agents` | Agent coordination |
| `skeleton.context` | Questionnaire and intake |
| `skeleton.config` | Layered configuration |
| `skeleton.content` | Reusable domain knowledge packs |

## Repository intelligence

Skeleton maintains a model-agnostic build intelligence contract under `repo-intel/`. Run:

```bash
make repo-intel        # current machine map + gaps + security/quality notes
make repo-intel-check  # agent/build handoff gate
```

Generated snapshots live under `.cache/repo-intel/` and include a full tracked-file index, subsystem/build map, structural game-creation gaps, large-artifact findings and security/quality notes. The scanner uses Git index metadata for clean files so it remains cheap enough for every agent session and CI run.

Every build-affecting change must also add/update a note under `repo-intel/notes/` with batch IDs, validation evidence, security/quality/dependency impact and noticeable remaining gaps. `AGENTS.md` defines the vendor-independent protocol and CI enforces the note gate.

## Missing features / SOTA game-creation target

`repo-intel/game-capabilities.json` is the living capability envelope and `repo-intel/batches.json` maps it into **100 large, dependency-aware batches** that can be worked in parallel. Structural detection deliberately distinguishes `present-surface` from functional readiness: a matching module/path is evidence that a surface exists, not proof that it is complete, secure, fast, fun, or competitive.

Highest-priority gaps are expected to be driven to measurable evidence in these areas:

- **Concept → playable → release:** persistent design graph, semantic edits, live preview, reversible multi-agent generation and an end-to-end benchmark.
- **Core game runtime:** canonical mechanics, ECS/composition, safe scripting, physics, navigation, save migration, deterministic clocks/replay and performance budgets.
- **World creation:** scene graph, procedural generation, terrain/biomes, large-world streaming and persistent systemic simulation.
- **Assets:** 2D/3D/material/animation/audio/voice generation and import with optimization, rights/provenance and release gates.
- **AI-native creation:** model routing, grounded NPCs, narrative/quest synthesis, project memory, bounded self-repair and versioned game-creation evals.
- **Multiplayer:** transport, replication, dedicated servers, prediction/reconciliation, rollback, matchmaking and load/chaos evidence.
- **Creator collaboration:** visual editing, semantic merge, realtime multi-user work, undo/redo across generated state and extension/plugin contracts.
- **Security/quality:** generated-code sandboxing, prompt/tool-injection defenses, supply-chain evidence, Dependabot/security intelligence, autonomous playtests, fuzz/mutation tests and visual regression.
- **Platforms/live operations:** engine-neutral IR, Godot adapter hardening, desktop/mobile/web matrices, localization/accessibility, telemetry, feature flags, modding/UGC and reproducible releases.

The target is to go beyond feature-count competition by optimizing the complete creation loop on measurable dimensions: correctness, iteration latency, editability, deterministic reproduction, security, provenance, creator control, platform reach, runtime performance and release evidence. Claims of SOTA/competitive readiness require the corresponding eval or benchmark; roadmap completion alone is not treated as proof.

## Lorebuffa AI Domain Pack

The Skeleton AI now has a domain adapter for the AI-relevant work developed in Lorebuffa. It keeps the generic engine clean while importing the useful world-model concepts: NPC personas, faction context, schedules, voice styles, reputation-aware dialogue choices, and quest objective patterns.

```python
from skeleton.pipelines.lorebuffa_npc import LorebuffaNpcPipeline

npc = LorebuffaNpcPipeline().run(
    "A veteran fisherman who hides a dangerous secret.",
    npc="barnacle_bill",
    dialogue_beats=4,
)
```

The adapter reuses Skeleton's existing NPC verification and repair path instead of bypassing the control plane. Lorebuffa's game transport/UI/backend persistence code is intentionally not pulled into Skeleton's AI core.

## Developer CLI

```bash
skeleton dev scaffold <name>    # Create project from template
skeleton dev wizard             # Interactive project builder
skeleton dev health             # System health dashboard
skeleton dev visualize          # Blueprint visualization
skeleton dev extension <name>   # Generate subsystem boilerplate
skeleton dev docs <topic>       # Show documentation
```

## API Endpoints

- `GET /api/v1/health` — Health check
- `GET /api/v1/genesis` — Boot report
- `POST /api/v1/retrieval/query` — Multi-plane search
- `POST /api/v1/forge/blueprint` — Create blueprint (HMAC sealed)
- `POST /api/v1/forge/materialise` — Materialize blueprint (HMAC sealed)
- `POST /api/v1/pipeline/npc` — Generate NPC
- `POST /api/v1/pipeline/game-logic` — Design game mechanics
- `POST /api/v1/pipeline/animation` — Create animation spec

## Configuration

Layered (lowest → highest priority):
1. Built-in defaults
2. `config/settings.yaml`
3. `~/.skeleton/config.yaml`
4. `SKELETON_*` environment variables
5. Runtime overrides

## License

MIT
