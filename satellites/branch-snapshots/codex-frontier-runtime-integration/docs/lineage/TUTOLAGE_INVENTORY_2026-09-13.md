# Tutolage inventory — consolidation pass 01

## Source

- Repository: `Apeloff1/Tutolage`
- Revision inspected: `main` (`README.md`, SHA `c6adff045ead34459736ce4c09dcff298abc8221`)
- Source license: MIT (per README)
- Frontier disposition: **SELECTIVE PROMOTION**

## Confirmed capability map

| Source surface | Frontier destination | Disposition | Action |
|---|---|---|---|
| Jeeves system laws | `skeleton/ai/`, `skeleton/learning/` | CHARACTERIZE | Compare against current Jeeves control plane; retain stronger deterministic pedagogy. |
| SAM / CLOM / KREM | `skeleton/learning/` | CHARACTERIZE | Extract policy semantics; avoid duplicating existing learning controls. |
| Jeeves Hyperion knowledge base | `skeleton/learning/knowledge/` | CHARACTERIZE | Inventory unique concepts/content; promote as versioned knowledge packs. |
| Jeeves voice/personality | `skeleton/ai/` | CHARACTERIZE | Keep presentation/persona separate from kernel contracts. |
| ChromaDB RAG | `skeleton/memory/` | ADAPT | Provider-neutral retrieval adapter only. |
| Text-to-NPC | `skeleton/game/` | PROMOTE | Extract schemas, validation, and pure transformations. |
| Text-to-game-logic | `skeleton/game/` | PROMOTE | Extract domain/compiler semantics and tests. |
| Text-to-animation | `skeleton/game/` | CHARACTERIZE | Extract state-machine/rig schemas; defer UI/provider coupling. |
| immersive tutor / ZPD | `skeleton/learning/` | PROMOTE | Reconcile with existing school reasoning and learning policy. |
| gamification / achievements / quests | `skeleton/learning/` | CHARACTERIZE | Merge only missing behavioral capabilities. |
| multi-layer learning | `skeleton/learning/` | CHARACTERIZE | Preserve unique learning-path structure as policy. |
| IDE / code completion | `apps/`, `services/` | CHARACTERIZE | Application capability; no kernel coupling. |
| collaboration | `services/` | CHARACTERIZE | Extract protocol/contracts only after runtime event model is stable. |
| MongoDB / Motor | `services/` | ADAPT | Infrastructure adapter only. |
| Expo / Zustand frontend | `apps/`, `cockpit/` | DEFER | Migrate after backend contracts stabilize. |
| FastAPI routes | `services/` | REJECT WHOLESALE COPY | Promote pure logic/contracts, not routing framework. |

## Immediate extraction queue

1. Jeeves core + matrices + memory semantics; compare against the landed school reasoning control plane.
2. NPC pipeline schemas/validation and deterministic output shaping.
3. Game-logic pipeline domain schemas and pure mechanics generation.
4. Animation pipeline state-machine and rig schemas.
5. Immersive tutor/ZPD policy and scaffolding rules.
6. Learning engine's unique progression semantics.
7. Backend tests for the above surfaces as behavioral acceptance criteria.

## Exclusion rules

- No provider-specific AI call in kernel contracts.
- No MongoDB/ChromaDB requirement in minimal runtime.
- No FastAPI router imports into core.
- No secrets, `.env` values, local DBs, caches, build artifacts, or generated output.
- Preserve provenance for each promoted module.
- Resolve overlap with current Skeleton school/control-plane code before adding duplicates.
