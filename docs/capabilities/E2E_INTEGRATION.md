# End-to-end integration: emulators + game building + design + story

## Flow the local model can drive
1. Query fleet (v2/v3 capability) → choose era and cores
2. Call `game_building_capability.full_pipeline(title, genre, era)`
3. Receive brief + level outline + story arc + asset plan + sample dialogue
4. Iterate with `generate_dialogue_tree`, `generate_level_outline`, etc.
5. Operator reviews
6. Downstream: GameForge / gamefile-ops emits data catalogs, world.tscn stubs, provenance meta
7. Qualified cores in the isolated host provide playtest evidence
8. Evidence feeds back for the next design iteration

## Tool composition
- `console_emulator_capability` (v2) for fleet queries
- `game_building_capability` for design/story/pipeline
- Both injectable into the same offline session prompt
- Both expose dispatch() for tool-calling loops

## Example session
User: “Design a 16-bit metroidvania called Shadow of the Pixel”
Model: calls full_pipeline → returns structured brief targeting snes9x/bsnes/genesis cores, 3-act story, hub structure, asset plan.
User: “Add a dialogue tree for the elder about the prophecy”
Model: calls generate_dialogue_tree.

All native testing and final pack emission stay outside this layer.
