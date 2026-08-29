# Tutolage Skeleton — v16.0

<div align="center">

![Skeleton](https://img.shields.io/badge/Skeleton-v16.0-0F172A?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-FF6F61?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**The layered rewrite of the Tutolage AI Learning & Game-Development Platform**

</div>

---

## What Skeleton Is

**Skeleton** is the layered rewrite of the Tutolage platform into a strict
hexagonal architecture: **kernel** (pure domain), **agents** (multi-agent
substrate), **memory / retrieval / intelligence** planes, the **Universal**
**Forge** blueprint engine, the **Jeeves** tutor brain with the trainable
**cortex** organism, a serving **FastAPI** surface, a **CLI**, and a **legacy
backend** in `backend/` being absorbed via guarded shims.

The 2026-08 deep-cut campaign folded every duplicate into a canonical
implementation, fixed five runtime-landmine bugs found by reading (two of
which disabled the entire CLI and the four-plane retrieval lattice), and
wired every boot phase. See `docs/DEEP_CUTS.md` and `BUILD_PLAN.md` for the
full ledger.

---

## Repository Layout

```
skeleton/                    # the v16 package (pip install -e .)
├── kernel/                  # pure domain: events, errors, ids, registry,
│   │                        # clocks, work_queue (DRR lanes + deadlines),
│   │                        # shims: workqueue / fair_queue / vclock → canonicals
├── genesis.py               # boot orchestrator: kernel → memory → intelligence
│   │                        # → swarm → resilience → interface → cortex
├── config/                  # pydantic-settings tree
├── agents/                  # mesh (operational roster), scheduler, ledger
├── swarm/                   # SwarmMesh (partitions, chaos, auctions),
│   │                        # hive, stigmergy, consensus + mesh_boundary note
├── memory/                  # RAG / CAG / MAG trinity + prefix_renderer
│   │                        # and warmer (KV-cache semantics, ported from
│   │                        # backend/services)
├── intelligence/            # dream, adaptive, metalearning, tensor base
├── retrieval/               # quad lattice (RAG+CAG+MAG+KAG + RRF), fusion,
│   │                        # ranking trio (rule boost → FeatureReranker →
│   │                        # diversity Ranker), pipeline
├── resilience/              # threat fortress, bulkheads, canaries
├── observability/           # health, metrics, tracing, anomaly, SLO
├── vault/                   # sealed secrets store, Shamir seal, KMS, audit
├── agents|swarm as above    #
├── jeeves/                  # tutor: core, matrices (SAM/CLOM/KREM), builder,
│   │                        # tactical, templates, assessment
├── cortex/                  # JeevesCortex — slots (pfc/midbrain/left/right),
│   │                        # neo LM, MoE, callosum, sleep, REINFORCE
├── context/                 # cockpit command language, tensor, quad pipeline
├── forge/                   # blueprints, eras, hardware, walk, gdscript emit
├── pipelines/               # text→NPC / game-logic / animation
├── api/                     # server factory, routes, cortex routes, auth,
│   │                        # idempotency, telemetry → kernel bus
├── testing/                 # scaffold + fixtures + smoke suites
backend/                     # legacy monolith being absorbed:
└── services/cag|mag guarded → skeleton memory, other services route-local
```

---

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn skeleton.api.server:create_app --factory --reload --port 8001
# → http://localhost:8001/docs

pytest skeleton/testing/ -q    # smoke suites (15 + 6 tests)
ruff check .                   # lint
```

## CLI

```bash
python -m skeleton eras          # era dialect list
python -m skeleton run "vision" --out ./proj --overwrite --json
python -m skeleton check ./proj
python -m skeleton think "stimulus"
python -m skeleton train --epochs 1
python -m skeleton metrics       # score the live neocortex
```

## HTTP surface (selected)

| Endpoint | Purpose |
|---|---|
| `GET /health`, `/metrics`, `/api/v1/genesis` | Boot & health introspection |
| `POST /api/v1/memory/query` | Trinity RAG/CAG/MAG fusion |
| `POST /api/v1/retrieval/query`, `/retrieval/ingest` | Quad four-plane retrieval |
| `POST /api/v1/jeeves/*` | Tutor sessions, review, advice |
| `POST /api/v1/forge/*` | Blueprint build & materialise (idempotent) |
| `POST /api/v1/gameforge/run` | Ten-stage context pipeline (live now) |
| `GET /api/v1/context/snapshot` | Cockpit command-language state |
| `GET /api/v1/cortex/status`, `POST /api/v1/cortex/think` | Neocortex inspect |
| `GET /api/v1/telemetry/routes` | Per-route timing |

## Principles

1. **Kernel is pure.** No framework or I/O imports under `skeleton/kernel/`.
2. **One implementation per concept.** Duplicates fold into the canonical
   module; old import paths survive as shims until the rename pass.
3. **Failures are typed.** Everything derives from `SkeletonError` with a
   code, severity and context.
4. **Boot is total.** Genesis phases wire kernel → memory → intelligence →
   swarm → resilience → interface → cortex; `health()` evaluates the
   invariant lattice on demand.
5. **The cortex is a model, not a wrapper.** PFC / midbrain / left / right /
   neo slots with acquire / surpass / distill heads and an own-system LM.

---

## License

MIT — see `LICENSE`.
