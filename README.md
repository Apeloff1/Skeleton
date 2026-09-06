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
