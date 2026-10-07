# Game-logic promotion contract — 2026-09-13

Source: `Apeloff1/Prood`
Source path: `backend/routes/game_logic_pipeline.py`
Source revision: `main`, source blob SHA `422502cac6250b0d0a058be6028645299d98ae73`.

## Extracted domain surface

The source defines a text-to-game-logic system around mechanic types: combat, movement, inventory, crafting, dialogue, economy, progression, physics, AI behavior, puzzle, stealth, and survival. It also defines combat styles and progression styles plus reusable mechanic/rule templates.

## Frontier boundary

Promote mechanic/rule schemas and pure transformations. Exclude FastAPI routers, transport models, LLM service calls, persistence, UUID/time generation, and provider-specific orchestration.

## Minimum contract tests

- Mechanic and style enums serialize to stable provider-neutral values.
- Templates are immutable per generation call.
- Unknown/unsupported template combinations fail explicitly.
- Numeric rule parameters remain bounded and validated.
- Pure mechanic compilation has no HTTP/provider imports.

## Disposition

**PROMOTE as a deterministic game-domain/compiler contract; reject wholesale route copying.**
