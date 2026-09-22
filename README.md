# Tutolage Skeleton v16

AI game engine and agent orchestration framework.

## Quick Start

```bash
# First-time host/runtime setup
python -m skeleton app preload
python -m skeleton app setup
python -m skeleton app install
# or, before installing the Python package: python scripts/install_app.py

# Inspect canonical topology, then optionally probe live runtime health
python -m skeleton app status
python -m skeleton app status --live

# Validate the repository-wide application assembly
python -m skeleton app check

# Build and start frontend + backend + Skeleton API + Mongo
python -m skeleton app up

# Verify the assembled public surfaces
python -m skeleton app smoke

# Optional operating modes
python -m skeleton app up --hot
python -m skeleton app up --production

# Boot only the in-process Skeleton engine runtime
python -m skeleton run

# Developer CLI
python -m skeleton dev scaffold my-agent --template minimal-agent
python -m skeleton dev wizard
python -m skeleton dev health

# Run tests
python -m skeleton test
```

The application assembly contract and operator commands are documented in [`docs/APP_ASSEMBLY.md`](docs/APP_ASSEMBLY.md).
Canonical ownership, topology, change lanes, and migration boundaries are mapped in [`docs/ARCHITECTURE_MAP.md`](docs/ARCHITECTURE_MAP.md).
The complete AI build sequence, provider rules, capability planes, acceptance gates, and open construction gaps are the mandatory manual in [`docs/AI_APP_CONSTRUCTION_MANUAL.md`](docs/AI_APP_CONSTRUCTION_MANUAL.md).

### Windows installer

Windows users can install the assembled application through a normal per-user
Setup wizard. The CI artifact is named `Skeleton-Setup-<version>-windows-x64.exe`.
It installs `Skeleton.exe`, Start Menu shortcuts, optional desktop shortcut,
repair controls, and an uninstaller.

To build the installer on Windows:

```powershell
pwsh ./scripts/windows/build_installer.ps1
```

The installed launcher contains its own Python runtime. Docker Desktop with the
Docker Compose plugin remains required to build and run the application services.

## Architecture

7-phase boot protocol:
1. **kernel** — EventBus, EntropyPool, VectorClock, InvariantLattice
2. **memory** — RAG, CAG, MAG, Trinity, DreamEngine, DriftDetector
3. **intelligence** — Orchestrator, AdaptiveLearner
4. **swarm** — SwarmMesh, PheromoneField, HiveMind, Platoons
5. **resilience** — ResilienceFortress, CanaryRegistry
6. **interface** — AnomalyDetector, ProvenanceLedger, Reranker, QuadRetriever
7. **cortex** — JeevesCortex (observes the whole bus)

## Artifact plane

- Track E root-test archive: `tests/legacy_root/`
- SEVEN_BY series archive: [`docs/archive/seven_by/`](docs/archive/seven_by/)
- Policy: [`docs/ARTIFACT_PLANE.md`](docs/ARTIFACT_PLANE.md)

## Builder plane

Autonomous feature work uses a deterministic Builder Plane between Secretary
admission and the bounded feature worker. Maintainer-approved issue authority
is compiled into a digest-sealed build manifest with exact snapshot/execution
custody, an ordered build DAG, proposal budgets, acceptance criteria, and
publication evidence. The plane is data-only: it does not add token
permissions, executable model output, or merge authority.

See [`docs/BUILDER_PLANE.md`](docs/BUILDER_PLANE.md) for the complete
authority, lifecycle, failure, and CI contract.

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

## Optional Java accelerators

Skeleton remains Python-first, with opt-in Java 21 kernels for large observability/statistical batches, dense VectorStore top-K scoring, and finite-AABB physics broad phase. Small workloads and all accelerator failures stay on the existing Python paths.

See `docs/java-accelerators.md` for enablement, bounds, failure semantics, deterministic parity rules, and the crossover benchmark.

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
