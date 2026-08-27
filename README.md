# Tutolage Skeleton — v16.0

<div align="center">

![Skeleton](https://img.shields.io/badge/Skeleton-v16.0-0F172A?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-FF6F61?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**The fully rebuilt, maximum-density rewrite of the Tutolage AI Learning & Game-Development Platform**

*Every module complete. Every pipeline functional. No stubs. No placeholders. No shortcuts.*

</div>

---

## What Skeleton Is

**Skeleton** is the ground-up rewrite of the `Prood` monolith (v15) into a rigorously layered,
hexagonal codebase. Where Prood grew organically into 300+ co-mingled route modules, Skeleton
distils the same surface area — Jeeves AI tutoring, the Text-to-X game pipelines, the agent
swarms, the learning sciences engine, the world/asset forges — into a strict architecture with
total separation between **domain**, **application**, **infrastructure**, and **interface**
concerns.

Every file in this repository is complete, importable, and test-covered. There are no TODOs,
no `pass` bodies standing in for logic, and no truncated modules.

---

## Layered Architecture

```
skeleton/
├── config/                 # pydantic-settings configuration tree (env-driven, validated)
│   └── settings.py
├── kernel/                 # pure domain kernel — zero I/O, zero framework imports
│   ├── errors.py           #   typed exception lattice with codes, context, severity
│   ├── events.py           #   domain event bus: pub/sub, replay, correlation ids
│   ├── ids.py              #   strongly-typed identifier value objects
│   └── registry.py         #   plugin/capability registry with versioning + health
├── agents/                 # multi-agent substrate
│   ├── ledger.py           #   append-only agent activity ledger w/ audit queries
│   ├── mesh.py             #   agent mesh: discovery, routing, quorum, consensus
│   └── scheduler.py        #   swarm scheduler: priorities, backpressure, retries
├── pipelines/              # Text-to-X generation pipelines (application services)
│   ├── npc.py              #   Text-to-NPC: persona, dialogue trees, behaviour graphs
│   ├── game_logic.py       #   combat / economy / progression system synthesis
│   └── animation.py        #   rigs, keyframes, state machines, blend trees
├── jeeves/                 # the Jeeves AI tutor brain
│   ├── core.py             #   system laws, session orchestration, co-coding mode
│   ├── matrices.py         #   SAM / CLOM / KREM self-learning matrices (full impl)
│   └── rag.py              #   ChromaDB retrieval-augmented memory w/ fallback store
├── forge/                  # the Universal Forge: systems synthesis engine
│   └── universal.py        #   composable system blueprints, validation, materialisation
├── api/                    # interface layer — FastAPI adapters, no domain logic
│   ├── server.py           #   app factory, middleware, lifespan, OpenAPI surface
│   └── routes.py           #   REST endpoints for every subsystem
└── __init__.py             # package surface + version constants
tests/                      # pytest suite mirroring the package tree
docs/ARCHITECTURE.md        # the full architectural treatise
```

---

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn skeleton.api.server:create_app --factory --reload --port 8001
# → http://localhost:8001/docs
```

```bash
pytest -q            # full suite
ruff check .         # lint
python tests/run_unit.py
```

## GameForge CLI

```bash
python -m skeleton eras
python -m skeleton run "soulslike extraction with bonfire rest" --out ./proj --overwrite --json
python -m skeleton run --blend arcade_golden_age soulslike --t 0.5 --out ./blend --overwrite
python -m skeleton check ./proj
python -m skeleton think "soulslike extraction ttk elite dread"
python -m skeleton train --epochs 1
```

HTTP: `GET /api/skeleton/eras` · `POST /api/skeleton/run` · `GET /api/skeleton/beats` · `POST /api/skeleton/think` · `POST /api/skeleton/train` · `GET /api/skeleton/cortex`

Cortex (the model we are building, not implementing): PFC small/boilerplate · midbrain medium/coordinator · left analytic · right gestalt · Jeeves neo hivemind+trainer+LM. Slots are `ModelPort`s; `bind` hot-swaps a backend; `acquire` copies a tract into own-system; `surpass` answers from the neo transformer (own-lm decode). Stacked Pre-LN (n_layers=2, n_heads=2, FFN) on CPU; `to("cuda")` pins the same weights on GPU when torch can see one, else degrades. The speaking LM authors the BuildPlan briefing.

---

## Subsystem Map

| Subsystem | Responsibility | Key modules |
|---|---|---|
| **Kernel** | Events, errors, identity, capability registry | `kernel/*` |
| **Agents** | Swarm discovery, routing, consensus, audit | `agents/mesh.py`, `agents/scheduler.py` |
| **Pipelines** | NPC, game-logic, animation generation | `pipelines/*` |
| **Jeeves** | Tutor persona, system laws, RAG memory, neocortex | `jeeves/*`, `cortex/*` |
| **Cortex** | Interchangeable model: PFC/midbrain/hemispheres/own-system + stacked neo LM (CPU/CUDA harness) | `cortex/{port,pfc,midbrain,hemispheres,own,curriculum,neocortex,transformer,device,torch_lm}.py` |
| **Forge** | Universal system blueprint synthesis | `forge/universal.py` |
| **API** | HTTP surface, validation, lifespan | `api/*` |

---

## License

MIT — see `LICENSE`.
