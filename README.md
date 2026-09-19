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
| `skeleton.shells` | Policy-bound, argv-only host process execution |
| `skeleton.shells.ai` | Jeeves/model planning, deterministic review, sealed execution, evals, MCP tooling |
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

## AI-ready shell

The shell execution plane now has a dedicated AI control layer for Jeeves and external structured-tool agents. Models propose logical commands; deterministic effect/risk policy, optional human approval, stale-plan pins, signed execution seals, workspace preconditions, and the existing ShellService decide what can actually execute. The model-facing catalog never exposes host executable paths or resolved environment secrets.

Key references:

- `docs/SHELL_AI_2026_ARCHITECTURE.md`
- `docs/SHELL_AI_THREAT_MODEL.md`
- `docs/SHELL_AI_OPERATIONS.md`
- `docs/SHELL_AI_EVALS.md`
- `docs/SHELL_AI_MCP_2026.md`
- `docs/SHELL_AI_HIGH_ASSURANCE_RUNBOOK.md`
- `docs/SHELL_AI_RUNTIME_TRUST_EPOCHS.md`
- `docs/SHELL_AI_DISTRIBUTED_AUTHORITY_OPERATIONS.md`
- `docs/SHELL_AI_DURABLE_EVIDENCE.md`
- `docs/SHELL_AI_DURABLE_EVIDENCE_LIFECYCLE.md`

The canonical quality gate runs every `skeleton/testing/test_shell_*.py` regression, so AI-shell security and execution tests are mandatory rather than optional.

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

## ARM64 / Ubuntu

Skeleton is validated on native Ubuntu ARM64 (`aarch64`) in CI. The Python job installs the repository package from its declared metadata so the ARM run exercises the same runtime dependency contract as supported hosts. The Docker runtime paths use pinned multi-platform base images, and the ARM64 CI job compiles the full Skeleton package, runs focused regression tests, and builds all three application images natively.

For ARM64 hosts, use Docker/Compose normally; Docker selects the ARM64 variant of the pinned multi-platform base images. To explicitly build the ARM64 targets:

```bash
docker buildx build --platform linux/arm64 -t skeleton:arm64 .
docker buildx build --platform linux/arm64 -f backend/Dockerfile --target production -t skeleton-backend:arm64 .
docker buildx build --platform linux/arm64 -f frontend/Dockerfile --target production -t skeleton-frontend:arm64 frontend
```

The ARM64 workflow is intentionally separate from the main x86 CI so ARM-native compatibility failures are visible without making every general-purpose test job depend on emulation.

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
