# NPC promotion contract — 2026-09-13

Source: `Apeloff1/Prood`
Source path: `backend/routes/npc_pipeline.py`
Source revision: `main` at the revision recorded by the Prood inventory.

## Extracted domain surface

The source exposes a text-to-NPC domain with:

- archetypes including merchant, warrior, mage, healer, rogue, scholar, artisan, noble, peasant, guardian, trickster, mentor, villain, companion;
- alignment values across lawful/neutral/chaotic × good/neutral/evil;
- emotional states including neutral, happy, sad, angry, fearful, surprised, disgusted, curious, suspicious, friendly;
- generation inputs for description, optional archetype/alignment, dialogue/quest toggles, and complexity;
- deterministic description parsing for archetype, traits, and alignment;
- archetype-based stat/personality templates;
- behavior-pattern and dialogue hooks.

## Frontier extraction boundary

Promote only the pure domain contract. Keep these outside the kernel/domain model:

- FastAPI `APIRouter` and HTTP exceptions;
- Pydantic request transport models where they are only API plumbing;
- LLM service imports;
- UUID/time/random generation unless explicitly modeled as injectable policy;
- persistence and external service calls.

## Required canonical shape

`NPCSpec` should represent validated intent and generated domain state. Parsing should be a pure function. Personality/stat generation should be separately testable. Dialogue and quest generation should consume the validated NPC contract rather than transport-layer objects.

## Minimum contract tests

1. Known archetype keywords resolve to the expected archetype.
2. Combined alignment keywords resolve to the expected alignment.
3. Trait modifiers remain bounded to `[0, 100]`.
4. Unknown descriptions remain valid with explicit `None`/empty detections.
5. Archetype templates do not mutate shared source data between calls.
6. Transport/provider imports are absent from the pure NPC module.

## Disposition

**PROMOTE as a provider-neutral domain contract; do not copy the FastAPI route wholesale.**
