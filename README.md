# Tutolage Skeleton v16

A local-first game studio with Jeeves AI chat, Dragon web capture and reviewed
knowledge, original-world editing, human/AI play, and bounded policy training.
The application runs as a frontend, application API, canonical AI engine and MongoDB.

## First install

Install **Git**, **Python 3.11+**, and **Docker Desktop or Docker Engine with Compose v2**.
Start Docker before running the installer. Host Node/Yarn are optional; the
container build supplies frontend dependencies. Initial dependency/image builds
need internet access. Models, compiler SDKs, cores and firmware have separate setup.

### Linux and macOS

```bash
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton
python3 -m venv .venv
source .venv/bin/activate
python scripts/install_app.py --production --start
python -m skeleton app doctor --live --studio --json
```

### Windows PowerShell

```powershell
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton
py -3 -m venv .venv
.\.venv\Scripts\python.exe scripts/install_app.py --production --start
.\.venv\Scripts\python.exe -m skeleton app doctor --live --studio --json
```

Open **http://localhost:3000/setup** first, then **http://localhost:3000/product**.
The production flag serves the built web app through Nginx. Later commands must
use the same Python environment. On PowerShell, invoking its Python executable
directly works without changing execution policy.

The installer installs Python dependencies, creates a private `.env`, and starts
the four application services. Preserve `.env` and Docker data volumes across
restarts. A healthy install starts **without AI weights**; configure a model before
expecting chat or autonomous studio decisions. Web capture also needs a signed-in
operator, explicit source rights and a bounded run grant.

### Set up the owner account

Public registration creates a viewer. To manage captures, build projects and
administer the studio, explicitly bootstrap your own account using a private
password file outside the repository:

```bash
python -m skeleton app setup --admin-email owner@example.com \
  --admin-password-file /absolute/private/owner-password.txt
python -m skeleton app up --production --no-build
```

Choose your own password: at least 16 characters, at most 72 UTF-8 bytes. On Unix,
restrict the file to `0600`. Do not commit the file or put the password in a command
argument. You can pass the same two account flags to the initial installer instead.
There is no shared administrator password or automatic first-user elevation.

### Enable AI

For the optional pinned **Linux x86-64 glibc** CPU model/runtime, explicitly provision
artifacts, select the deployment in private `.env`, and recreate the engine:

```bash
python scripts/provision_local_ai.py --target linux-x86_64-glibc \
  --download --context-size 12288 --output ./data/local-ai
```

```dotenv
AI_PROVIDER=local
AI_LOCAL_MODEL_PATH=
AI_LOCAL_DEPLOYMENT_PATH=/app/local-ai/deployment.json
SKELETON_LOCAL_MODEL_DIR=./data/local-ai
```

```bash
python -m skeleton app up --production --no-build
python -m skeleton app doctor --live --studio --json
```

This explicitly acquires about 657 MB of pinned artifacts. The script's default
context remains 8,192 tokens; the larger studio example requests 12,288. Context
and inference remain subject to actual model/host capacity. Existing installations
are verified and never silently reconfigured. Other CPU/OS targets need a compatible
runtime; preparing Linux files on another host does not prove native execution.
Hosted providers and already installed GGUF models are alternatives. Follow the
[complete AI and crawler setup](docs/ai/FIRST_INSTALL_AI_AND_CRAWLER.md) for activation,
platform details, offline inputs and private configuration.

## Use the studio

| Task | Open | What it does |
| --- | --- | --- |
| First-run readiness | `/setup` | Distinguishes service health, configured AI and optional native dependencies. |
| Application hub | `/product` | Opens Studio, Jeeves, crawler and operations surfaces. |
| AI conversation | `/jeeves-chat` | Durable chat through the configured canonical engine. |
| Game creation and learning | `/game-learning` | Edit original worlds, observe human/AI play, run bounded learning and prepare exports. |
| Dragon web capture | `/crawler` | Capture authorized pages, inspect source text, review references and withdraw/erase sources. |

From **Product → Studio → Game learning studio**, create or select a project.
Original-world completion tracks saved edits, positive simulation, measured review,
a compiled desktop package, and source/package export preparation. The console
editor reports approved cores, content and toolchain readiness separately.

See [crawler, builder and training operations](docs/ai/STUDIO_CRAWLER_BUILDER_TRAINING.md)
and [native prerequisites](docs/ai/STUDIO_INSTALLATION_AND_NATIVE_READINESS.md).
The [creation capability index](docs/creation/CAPABILITY_INDEX.md) covers design
helpers and optional reference corpora; planning templates do not execute a game.

## Restart, diagnose and recover

```bash
python -m skeleton app status --live
python -m skeleton app logs
python -m skeleton app up --production --no-build
python -m skeleton app doctor --live --studio --json
```

`--no-build` is for restarting existing images. After updating application source,
run `python -m skeleton app up --production` to rebuild changed services. Use
`--hot` for frontend/source development instead of the production profile.

Change occupied ports in private `.env` before rebuilding:

```dotenv
FRONTEND_PORT=3000
BACKEND_PORT=8001
SKELETON_PORT=8010
```

Both production browser build arguments and development environment defaults
follow these published ports. Explicit `EXPO_PUBLIC_*` URLs override them; use
browser-reachable HTTPS endpoints for a remote deployment. Keep engine/provider
credentials out of public frontend variables.

Back up the private `.env` and durable state using the documented recovery owner.
Do not delete Docker volumes, replace live SQLite files, or rotate secrets as a
routine repair. The [assembly guide](docs/APP_ASSEMBLY.md) describes operating modes,
service readiness and recovery boundaries.

## Current capability boundaries

- The studio has a working bounded creation/build/export workflow. Desktop packages
  are browser-rendered launchers; cross-compilation does not prove execution on every OS.
- Native emulation and builds require approved cores, suitable content/firmware,
  compiler SDKs and the sandbox. The default Alpine backend does not make every
  host native tool executable. The recorded inventory still has 70 unmapped targets.
- Learning updates game policies and records compatible lessons. It does not
  automatically change Jeeves's transformer weights or guarantee creative quality.
- Compressed design corpora are optional reference text, not measured gameplay
  evidence or automatically admitted training data. Their manifests preserve hashes.
- Docker service health, AI availability, native target readiness and production
  acceptance are separate states. This repository does not certify every console,
  arbitrary-ROM semantic understanding, or superiority over commercial games.

Exact historical observations are in the
[creation qualification](docs/ai/STUDIO_CREATION_QUALIFICATION_2026-10-15.md).
Canonical ownership and architecture are mapped in the
[Repository Atlas](docs/architecture/REPOSITORY_ATLAS.md),
[integration guide](docs/architecture/REPOSITORY_INTEGRATION.md), and
[AI construction manual](docs/AI_APP_CONSTRUCTION_MANUAL.md).

### Standalone local AI

Use a locally installed trained GGUF model and llama.cpp CLI without Docker or
hosted-provider credentials. Prepare the pinned configuration once:

```bash
python -m skeleton app prepare-local-model \
  --executable /path/to/llama-cli --model /path/to/model.gguf \
  --output ./local-model.json

# Durable terminal chat:
python -m skeleton app chat --gguf-deployment ./local-model.json --interactive

# Browser workspace on this computer:
python -m skeleton app serve-local-ai --gguf-deployment ./local-model.json \
  --token-file ./local-ai.secret --open-browser
```

Paste the token from the new private file into the browser workspace. Conversations,
references, cancellation and retry controls use the local model and SQLite store.
The desktop **Local AI** window also has **Set up GGUF…**. Native checkpoints remain
supported. Model preparation pins files; useful responses still require trained
weights and a compatible installed runtime.

See [offline AI operations](docs/ai/OFFLINE_NATIVE_CHAT.md) for limits, backups,
API routes, terminal commands and recovery behavior.

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

12-phase boot protocol (`skeleton/bootstrap/genesis.py`, `BOOT_PHASES`):
1. **foundation** — MerkleDAG, EventJournal (journaled bus), ReplayEngine, CapabilityKernel, Membrane, TemporalLattice
2. **kernel** — InvariantLattice, EntropyPool, VectorClock
3. **memory** — RAG, CAG, MAG, Trinity, RepetitionScheduler, DreamEngine, DriftDetector, DifferentialPrivacy
4. **intelligence** — Orchestrator, AdaptiveLearner
5. **swarm** — SwarmMesh, PheromoneField, StigmergicRouter, HiveMind, Negotiator, Platoons, Coordinator, MeshBridge
6. **resilience** — ResilienceFortress, CanaryRegistry, ChaosHarness
7. **interface** — AnomalyDetector, ProvenanceLedger, Reranker, Ranker, QuadRetriever
8. **forge** — universal Forge
9. **galaxy** — GalaxyNode, transport, consensus, election, fleet, Byzantine engine, KAG sync
10. **contexts** — ContextFabric, ResponseCycle, CausalEngine
11. **support** — SupportFabric + Overseer engines V1/V2/V3/V3.5 (ticked inline)
12. **cortex** — JeevesCortex + Jeeves alias (observes the whole bus)

Each phase is timed; one summary line is logged per boot against the budget in
[`docs/engineering/PERFORMANCE_BUDGETS.md`](docs/engineering/PERFORMANCE_BUDGETS.md)
(warn above 2.0 s, error above 5.0 s; override with `SKL_BOOT_BUDGET_MS` /
`SKL_BOOT_CRITICAL_MS`).

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
| `skeleton.automation.swarm` | Multi-agent coordination |
| `skeleton.forge` | Blueprint-based system composition |
| `skeleton.resilience` | Security and fault tolerance |
| `skeleton.observability` | Metrics and anomaly detection |
| `skeleton.api` | REST API surface |
| `skeleton.cortex` | Observability hub |
| `skeleton.developer` | Developer CLI and scaffolding |
| `skeleton.deploy` | Deployment harness |
| `skeleton.testing` | Test framework |
| `skeleton.organism` | Runtime state and feature flags |
| `skeleton.forge.pipelines` | High-level task pipelines |
| `skeleton.vault` | Access control and encryption |
| `skeleton.retrieval` | Search and fusion |
| `skeleton.automation.agents` | Agent coordination |
| `skeleton.context` | Questionnaire and intake |
| `skeleton.config` | Layered configuration |
| `skeleton.simulation.content` | Reusable domain knowledge packs |
| `skeleton.learning.school` | Curriculum, assessment, and learner state |
| `skeleton.distributed` | Galaxy, mesh, and network coordination |
| `skeleton.knowledge.graphs` | Graph and reasoning primitives |
| `skeleton.provenance.chronicle` | Evidence and tamper-evident history |
| `skeleton.tools.integrations` | Connectors and authenticated webhooks |
| `skeleton.research.social` | Research evidence intake |

## Lorebuffa AI Domain Pack

The Skeleton AI now has a domain adapter for the AI-relevant work developed in Lorebuffa. It keeps the generic engine clean while importing the useful world-model concepts: NPC personas, faction context, schedules, voice styles, reputation-aware dialogue choices, and quest objective patterns.

```python
from skeleton.forge.pipelines.lorebuffa_npc import LorebuffaNpcPipeline

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
