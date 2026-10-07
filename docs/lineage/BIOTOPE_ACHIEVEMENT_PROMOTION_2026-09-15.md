# Biotope achievement evidence promotion — 2026-09-15

## Source lineage

Biotope achievement semantics were mined once from the byte-identical source implementation:

- `Apeloff1/Lorebuffa/backend/biotope_achievements_routes.py`
- `Apeloff1/Openworld/backend/biotope_achievements_routes.py`
- shared blob: `5a06312eebf8bb21fef28b1010dfc3ccff6b6500`

The source catalog is useful, but its endpoint implementation does not maintain all of the evidence required by that same catalog. The promotion therefore keeps the existing canonical frontier achievement engine and adds only a biotope-specific normalization/evidence adapter.

## Frontier targets

- `skeleton/frontier/biotope_achievement_adapters.py`
- `skeleton/testing/test_frontier_biotope_achievement_adapters.py`

No second achievement state machine, claim path, event bus, wallet layer, or persistence system is introduced.

## Source defects closed by the adapter

### Declared requirements without emitted stats

The source recorder increments biotope, stage, rarity and a first-token fish counter, while the catalog also declares requirements for:

- distinct species in specific stages;
- number of biotopes fished;
- per-biotope minimum catch counts;
- complete fish discovery;
- trophy coverage across biotopes;
- legendary coverage across biotopes;
- maximum fish size.

The adapter derives these values from monotonic catch evidence instead of expecting unrelated persistence code to manufacture missing counters.

### Requirement/stat naming mismatches

The shared source catalog expects `lake_catches`, but the recorder emits `freshwater_lake_catches`. It expects `arctic_catches`, while the relevant stage counter is `arctic_ocean_catches`. These source-specific mismatches are bound through explicit allowlisted aliases rather than fuzzy matching.

### Species-family tracking

The source uses the first underscore-delimited fish-id token for family counters. That means identifiers such as `largemouth_bass` do not contribute to `bass_catches`. The frontier evidence recorder accepts explicit family tokens and, by default, indexes normalized identifier tokens so source achievements such as bass/trout/salmon/sturgeon/tarpon counters can be satisfied without first-token loss.

### `each` qualifier enforcement

The source `world_angler` requirement declares `count: 4, each: 100`, but the source checker only compares one scalar stat to `count` and ignores `each`. The frontier adapter interprets this as four biotopes meeting the per-biotope threshold before delegating the resulting scalar evidence to the canonical achievement kernel.

### Size-aware requirements

Source records may declare `size` instead of `count`. The adapter normalizes both forms into canonical `AchievementRequirement` thresholds while preserving threshold kind and source qualifiers as metadata.

## Canonical boundaries retained

The existing `skeleton.frontier.achievements` module remains authoritative for:

- achievement state;
- monotonic qualification;
- unlock idempotency;
- reward planning;
- claim semantics.

The existing achievement event/memory adapters remain authoritative for durable transition projection. Source fish catalogs, FastAPI routes, Motor/MongoDB persistence and wallet mutation remain source-owned.

## Evidence

The focused frontier test suite covers nested reward normalization, size thresholds, lake/arctic count aliases, family tracking, distinct-stage species, per-biotope mastery, trophy/legendary coverage, delta legendary evidence and delegation of claim semantics to the canonical achievement kernel.
