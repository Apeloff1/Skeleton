# Prood inventory — consolidation pass 01

## Source

- Repository: `Apeloff1/Prood`
- Revision inspected: `main` (`README.md`, SHA `b02adca69fba1f60df934778baa1aff1a76d4946`)
- Source license: MIT (per README)
- Frontier disposition: **SELECTIVE PROMOTION**

## Confirmed capability map

| Source surface | Frontier destination | Disposition | Action |
|---|---|---|---|
| Jeeves tutor / system laws | `skeleton/ai/`, `skeleton/learning/` | PROMOTE | Compare against existing Jeeves control-plane contracts; retain unique pedagogy only. |
| SAM / CLOM / KREM learning matrices | `skeleton/learning/` | CHARACTERIZE | Extract deterministic policy/value; do not import service plumbing. |
| ChromaDB RAG | `skeleton/memory/` | ADAPT | Preserve retrieval semantics behind `MemoryContract`; provider-neutral adapter only. |
| Text-to-NPC | `skeleton/game/`, `skeleton/frontier/npc.py` | PROMOTE | Preserve schema/validation/behavior; replace FastAPI/model coupling. |
| Text-to-game-logic | `skeleton/game/` | PROMOTE | Extract deterministic domain/compiler pieces and tests. |
| Text-to-animation | `skeleton/game/` | CHARACTERIZE | Extract schemas/compiler/state-machine logic; exclude UI/provider plumbing. |
| ZPD / immersive tutor | `skeleton/learning/` | PROMOTE | Compare with current school reasoning pipeline; preserve unique pedagogy. |
| XP / levels / achievements / quests | `skeleton/learning/` | CHARACTERIZE | Merge only capabilities not already represented by existing progression work. |
| 4-stage learning model | `skeleton/learning/` | CHARACTERIZE | Treat as pedagogical policy, not application routing. |
| MongoDB service | `services/` | ADAPT | Database adapter only; never a kernel dependency. |
| Expo / Zustand frontend | `apps/`, `cockpit/` | DEFER | Migrate after backend contracts stabilize. |
| FastAPI routes | `services/` | REJECT WHOLESALE COPY | Extract contracts and pure logic; no router import into core. |
| Docker / CI | repository operations | CHARACTERIZE | Reconcile with Skeleton gates; do not duplicate blindly. |

## Immediate extraction queue

1. `backend/routes/jeeves_core.py` — compare system laws, matrices, co-coding, and RAG orchestration against current Jeeves control plane.
2. `backend/routes/npc_pipeline.py` — extract NPC schema, validation, and deterministic transformations.
3. `backend/routes/game_logic_pipeline.py` — extract game-domain generation schemas and pure transformations.
4. `backend/routes/animation_pipeline.py` — extract rig/keyframe/state-machine schemas.
5. `backend/routes/immersive_tutor.py` — compare ZPD/scaffolding against existing learning policy.
6. `backend/services/rag_service.py` — characterize retrieval/index semantics for a provider-neutral adapter.
7. Relevant backend tests — promote behavioral guarantees alongside implementation.

## Exclusion rules

- No FastAPI router imports into kernel/core contracts.
- No OpenAI-specific calls in provider-neutral contracts.
- No MongoDB/ChromaDB requirement for minimal runtime.
- No secrets, `.env` values, local DBs, caches, build output, or generated artifacts.
- Every promoted implementation receives source repository + revision + source path provenance.
- Prefer pure/deterministic logic where behavior can be separated from infrastructure.

## Acceptance gate

A Prood component is promotion-ready only when:

- its behavior is covered by focused tests;
- its dependencies fit the Frontier layering contract;
- provider/database/web-framework coupling is behind adapters;
- provenance is recorded;
- duplication with existing Skeleton capabilities has been resolved explicitly.

## Source evidence

The Prood README identifies FastAPI backend routes for NPC, game-logic, animation, Jeeves core, Jeeves synergy, and immersive tutoring; MongoDB and ChromaDB services; an Expo/TypeScript frontend; Jeeves knowledge/matrices/RAG; text-to-X pipelines; gamification; and four learning stages.
