# Tutolage Skeleton — v16.2

<div align="center">

![Skeleton](https://img.shields.io/badge/Skeleton-v16.2-0F172A?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-optional-FF6F61?style=for-the-badge)
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
│   ├── registry.py         #   capability registry with versioning + health
│   └── …                   #   clocks, breaker, budget, election, gossip, saga,
│                           #   supervisor, telemetry, trace, workqueue, and more
├── agents/                 # multi-agent substrate
│   ├── ledger.py           #   append-only agent activity ledger w/ audit queries
│   ├── mesh.py             #   agent mesh: discovery, routing, liveness, consensus
│   └── scheduler.py        #   swarm scheduler: priorities, backpressure, retries
├── memory/                 # the RAG/CAG/MAG trinity with cross-tier fusion
│   ├── rag.py              #   TF-IDF in-memory store + ChromaDB store w/ fallback
│   ├── cag.py              #   persona/context-augmented memory
│   ├── mag.py              #   episodic memory + preference embeddings
│   └── trinity.py          #   fusion, dedup, re-rank, token budget, provenance
├── intelligence/           # quad-system cognitive substrate
│   ├── temporal.py         #   temporal reasoning over event streams
│   ├── causal.py           #   causal graphs + ATE estimation
│   ├── metalearning.py     #   task embeddings + meta-learner
│   ├── neurosymbolic.py    #   symbolic rules + neural inference
│   ├── economic.py         #   cost/quality model routing under budget
│   ├── dream.py            #   offline consolidation engine
│   └── orchestrator.py     #   unified multi-modal reason() interface
├── resilience/             # adversarial fortress
│   ├── sanitiser.py        #   input sanitisation with threat reports
│   ├── guardrails.py       #   output guardrails
│   ├── exfiltration.py     #   data-exfiltration detection
│   ├── shadow.py           #   shadow-mode experiments
│   └── fortress.py         #   unified ResilienceFortress interface
├── pipelines/              # Text-to-X generation pipelines (application services)
│   ├── npc.py              #   Text-to-NPC: persona, dialogue trees, behaviour graphs
│   ├── game_logic.py       #   combat / economy / progression system synthesis
│   └── animation.py        #   rigs, keyframes, state machines, blend trees
├── jeeves/                 # the Jeeves AI tutor brain
│   ├── core.py             #   system laws, session orchestration, co-coding mode
│   ├── matrices.py         #   SAM / CLOM / KREM self-learning matrices (full impl)
│   └── rag.py              #   retrieval-augmented memory w/ local fallback
├── forge/                  # the Universal Forge: systems synthesis engine
│   └── universal.py        #   composable blueprints, validation, materialisation
├── swarm/                  # extended swarm mechanics (auction, quorum, stigmergy)
├── vault/                  # secrets: Shamir sharing, rotation, sealing
├── retrieval/              # quad-lattice retrieval
├── observability/          # metrics, tracing, health, entanglement
├── api/                    # interface layer — FastAPI adapters, no domain logic
│   ├── server.py           #   app factory, middleware, lifespan, OpenAPI surface
│   └── routes.py           #   REST endpoints for every subsystem
└── __init__.py             # package surface + version constants
tests/                      # pytest suite: smoke + hermetic API integration
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
pytest -q            # full suite (hermetic — no DB, no network)
ruff check .         # lint
```

ChromaDB is optional: `pip install -e ".[chroma]"` enables the vector backend;
without it every memory store runs on fully implemented in-memory fallbacks.

---

## Subsystem Map

| Subsystem | Responsibility | Key modules |
|---|---|---|
| **Kernel** | Events, errors, identity, capability registry, flow control | `kernel/*` |
| **Agents** | Swarm discovery, routing, consensus, scheduling, audit | `agents/*` |
| **Memory** | RAG/CAG/MAG trinity with fusion + provenance | `memory/*` |
| **Intelligence** | Temporal, causal, meta-learning, neuro-symbolic, economic | `intelligence/*` |
| **Resilience** | Sanitisation, guardrails, exfiltration, shadow mode | `resilience/*` |
| **Pipelines** | NPC, game-logic, animation generation | `pipelines/*` |
| **Jeeves** | Tutor persona, system laws, self-learning matrices | `jeeves/*` |
| **Forge** | Universal system blueprint synthesis | `forge/universal.py` |
| **API** | HTTP surface, validation, lifespan | `api/*` |

---

## License

MIT — see `LICENSE`.
