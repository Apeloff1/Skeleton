# Prood / Tutolage promotion record

## Source

- Repository: `Apeloff1/Prood`
- Role: high-value learning/game-development source
- Status: selective promotion, not wholesale copy

The source README describes a FastAPI backend plus Expo/TypeScript frontend, Jeeves tutoring, ChromaDB RAG, gamification, and text-to-NPC / game-logic / animation pipelines.

## Promotion map

| Source capability | Frontier destination | Rule |
|---|---|---|
| Jeeves tutor orchestration | `skeleton/ai/` + `skeleton/learning/` | extract contracts and reusable algorithms |
| RAG / long-term memory | `skeleton/memory/` | adapt behind `MemoryContract`; no vendor lock-in |
| Text-to-NPC | `skeleton/game/` + `skeleton/frontier/npc.py` | preserve schema and behavior, replace web coupling |
| Text-to-game-logic | `skeleton/game/` | promote as domain service |
| Text-to-animation | `skeleton/game/` | promote schema/compiler pieces only |
| ZPD / learning stages | `skeleton/learning/` | preserve pedagogy, test independently |
| Expo UI | `apps/` / `cockpit/` | migrate after backend contracts stabilize |
| MongoDB service | `services/` | adapter only; no database requirement in kernel |

## Guardrails

1. Do not copy FastAPI routers into the kernel.
2. Do not import `services.*` from core contracts.
3. Keep model/provider calls behind explicit interfaces.
4. Preserve source provenance for every promoted module.
5. Prefer deterministic pure functions for game and learning logic.
6. Generated caches, credentials, local databases, and build output are excluded.
