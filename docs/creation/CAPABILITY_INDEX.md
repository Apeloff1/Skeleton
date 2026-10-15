# Capability & Data Index (Pareto map)

Single map of what exists and where.

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
- data/game_building/ — Pareto patterns + math/physics
- data/game_data_v2/ — assets, mechanics, UX, music direction, logic, self-improvement
- data/conversational/ — model conversational corpora

## Scripts
- scripts/quick_brief.py — zero-dependency brief

## Rules
Data-only in these layers. Operator gates installs, BIOS, content, and native tests. Prefer vertical slice. Run checklists before phase advance.
