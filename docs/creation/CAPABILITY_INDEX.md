# Capability & Data Index (Pareto map)

Map of runtime, planning helpers and optional reference material.

## Stateful application

Use the [first-install guide](../../README.md#first-install), then Product → Studio →
Game learning for the actual editors, play sessions, bounded training and build/export
jobs. Jeeves chat and crawler capture use their existing authenticated API owners.

The table below describes **data-only planning helpers**. They generate briefs,
checklists and candidate descriptions. Fleet/planning records do not establish that
a core is installed, firmware is approved or a game has executed. Consult Studio
readiness for actual target availability and the existing emulator/build owners for
execution. Canonical helpers live under `skeleton/jeeves/`; governed AI mirror paths
remain available for existing imports.

## Code (skeleton/ai/agents/jeeves/)
| Module | Purpose |
|--------|---------|
| unified_game_capability.py | Facade: fleet + adventure + creation |
| local_model_console_capability_v2.py | Emulator fleet query/filter/plan |
| adventure_game_capability.py | Rooms, puzzles, dialogue, asset tiers |
| full_game_creation_capability.py | Plans, bibles, backlogs, QA/release |
| adventure_systems_extended.py | Multi-room, sequence, state machines |
| production_planning_extended.py | Risk, resources, milestones |
| design_bible_assets_extended.py | Bible templates, asset checklists |
| actionable_checklists.py | Design / adventure / production / UX gates |

## Docs (docs/creation/)
- OPERATOR_QUICKSTART.md — start here
- UNIFIED_FACADE.md
- ACTIONABLE_CHECKLISTS.md
- FULL_GAME_CREATION_OVERVIEW.md
- DESIGN_BIBLE_STANDARDS.md
- ADVENTURE_DESIGN_FRAMEWORKS.md
- ASSET_QUALITY_TIERS.md

## Data
- [data/game_building/](../../data/game_building/README.md) — compressed Pareto patterns + math/physics with source/checksum manifest
- [data/game_data_v2/](../../data/game_data_v2/README.md) — compressed design text with source/checksum manifest
- data/conversational/ — model conversational corpora

## Scripts
- scripts/quick_brief.py — zero-dependency brief

## Rules
Data-only in these layers. Operator gates installs, BIOS, content, and native tests. Prefer vertical slice. Run checklists before phase advance.
