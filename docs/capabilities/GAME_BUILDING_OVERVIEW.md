# Game Building, Design, and Story Capability — Full Overview

Integrated with the expanded 169+ (actual 215) emulator fleet.

## Capabilities
- Design briefs targeted at specific hardware eras and cores
- Level / world outlines with pacing and structure
- Story arcs, themes, quest hooks
- Dialogue trees
- Asset plans (sprites, audio, data catalogs) with provenance rules
- Full end-to-end pipelines
- Game-design curricula
- Tool schema + dispatch for local-model loops
- Prompt injection cards

## Grounding
Every design is aware of the emulator fleet. Recommendations pull real cores from `fleet_database_v3.json`. Hardware-era constraints (palette, resolution, sprite limits) are surfaced so designs stay authentic to the target.

## Safety
- Data-only output
- No native execution
- No asset or BIOS downloads
- Operator reviews all briefs before any GameForge / pack emission
- Aligns with existing catalog, host, and content-inspection contracts

## Key files
- `game_building_capability.py`
- `game_building_cli.py`
- `fleet_database_v3.json` (215 entries)
- `SAMPLE_PIPELINE.json`
- Supporting design/story guides (this expansion)

The local model can now go from “I want a 16-bit metroidvania” to a complete brief + level outline + story arc + asset plan + target cores in one tool call.
