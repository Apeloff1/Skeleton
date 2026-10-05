"""
Skeleton — Root README and project documentation

This is the v16 Tutolage Skeleton platform — an AI game engine
and agent orchestration framework.

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

The Skeleton platform is organized into 7 boot phases:

1. **kernel** — EventBus, EntropyPool, VectorClock, InvariantLattice
2. **memory** — RAG, CAG, MAG, Trinity, DreamEngine, DriftDetector
3. **intelligence** — Orchestrator, AdaptiveLearner
4. **swarm** — SwarmMesh, PheromoneField, HiveMind, Platoons
5. **resilience** — ResilienceFortress, CanaryRegistry
6. **interface** — AnomalyDetector, ProvenanceLedger, Reranker, QuadRetriever
7. **cortex** — JeevesCortex (observes the whole bus)

## Subsystems

- `skeleton.kernel` — Core primitives and error types
- `skeleton.memory` — Multi-plane retrieval and storage
- `skeleton.intelligence` — Reasoning and learning
- `skeleton.swarm` — Multi-agent coordination
- `skeleton.forge` — Blueprint-based system composition
- `skeleton.resilience` — Security and fault tolerance
- `skeleton.observability` — Metrics and anomaly detection
- `skeleton.api` — REST API surface
- `skeleton.cortex` — Observability hub
- `skeleton.developer` — Developer CLI and tooling
- `skeleton.deploy` — Deployment harness
- `skeleton.testing` — Test framework
- `skeleton.organism` — Runtime state and feature flags
- `skeleton.pipelines` — High-level task pipelines
- `skeleton.vault` — Access control and encryption
- `skeleton.retrieval` — Search and fusion
- `skeleton.agents` — Agent coordination
- `skeleton.context` — Questionnaire and intake
- `skeleton.config` — Layered configuration

## Developer CLI

```bash
# Scaffold a new project
skeleton dev scaffold <name> --template <template>

# Interactive wizard
skeleton dev wizard

# Health check
skeleton dev health --json

# Visualize blueprints
skeleton dev visualize --blueprint <name>

# Generate extensions
skeleton dev extension <name> --type subsystem

# Documentation
skeleton dev docs <topic>
```

## API

FastAPI routes at `/api/v1`:

- `/health`, `/health/live`, `/health/ready`
- `/genesis`, `/genesis/handles`
- `/retrieval/query`, `/retrieval/ingest`, `/retrieval/feedback`
- `/jeeves/session`, `/jeeves/interact`, `/jeeves/review`
- `/swarm/stats`, `/swarm/agent`, `/swarm/route`
- `/forge/blueprint`, `/forge/materialise`, `/forge/kinds`, `/forge/eras`, `/forge/archetype`
- `/pipeline/npc`, `/pipeline/game-logic`, `/pipeline/animation`
- `/gameforge/run`, `/gameforge/intake`

Protected routes (HMAC seal):
- POST `/forge/blueprint`, `/forge/materialise`, `/forge/archetype`
- POST `/gameforge/run`, `/gameforge/intake`

## Configuration

Layered config (lowest to highest priority):
1. Built-in defaults
2. `config/settings.yaml` (project)
3. `~/.skeleton/config.yaml` (user)
4. `SKELETON_*` environment variables
5. Runtime overrides

```python
from skeleton.config import cfg
value = cfg.get("memory.rag.top_k", default=5)
```

## License

MIT
"""

# This file serves as both module docstring and README content
# The actual README.md should be generated from this content
