# Native generated-room quest integration — 2026-11-13

## Purpose and source preservation

PR #5304 restored the original #807 B028 quest objective runtime, B030
mechanic-pack composition and B037 constraint-guided quest generator.
Those modules were callable but did not yet affect the native Godot project.

This stacked recovery adds the opt-in \`quest_content=True\` / \`quest_length=1..8\`
contract to the existing \`GameForgeRun.execute\` and \`POST /api/skeleton/run\`.
No standalone project generator is substituted for the modern ten-stage
pipeline. All default builds remain unchanged.

## Real generated gameplay

1. The canonical Godot emitter creates \`data/rooms.json\` from the
   hardware/era/build plan, including the actual navigable room graph.
2. \`godot_quest_bridge\` derives an undirected, bounded \`WorldModel\` from
   this **same emitted room graph**. No guessed fictitious NPCs or locations.
3. The recovered B030 source-bound pack registry binds movement to quest
   objectives, and B037 synthesizes a seeded reachable 1–8-step quest
   with reward budget and dependency constraints.
4. B028 constructs and replays the objective sequence, validating completion
   and earned rewards. The resulting source is stored in
   \`data/quest_slice.json\`, alongside source-world SHA-256 and replay proof.
5. A Godot 4 native autoload \`scripts/autoloads/quest_runtime.gd\` subscribes
   to the emitted \`EventBus.room_entered\` signal. Visiting the required
   generated room progresses the live quest, updates a visible in-game quest
   HUD and accumulates reward totals.
6. The native autoload provides \`snapshot()\`, \`restore_snapshot()\` and
   \`quest_status()\` with source-digest binding, exact step-count replay and
   rejection of fabricated reward state. It does not silently award unrelated
   GameState resources or pretend to have a cloud save.
7. The canonical emit stage performs its usual source-manifest path checks,
   GDScript static checks, optional Godot boot check, and production custody
   *after* the native quest files have been attached. Exact quest hash and
   replay-verification summary enter the output response and emit receipt.

### Strict limitations

This implements **room-entry quests** for the current extraction-world
Godot generator, not arbitrary combat, NPC dialogue or narrative events.
Every one of the 67 legacy genre-specific mechanics still requires a
domain-specific native adapter and acceptance tests. The quest HUD is
visible by default for opted-in projects. Quest save snapshots may be
integrated into the app's durable save service later; the source-bound
snapshot API itself is implemented now.

This is a concrete new live game capability, but test source and static
checks do not count as a physical device or Godot-in-editor playtest.

## Review and qualification

Focused:
\`python -m pytest -q skeleton/testing/test_native_godot_quest.py skeleton/testing/test_original_quest_slice.py skeleton/testing/test_constraint_quest_synthesis.py skeleton/testing/test_genre_template_composition.py\`

Then run exact-head Merge Readiness, Backend Quality, App Foundation E2E,
Godot native runtime boot, Windows native installer, offline model, malware,
source mirror, dependency, workflow and security qualification. This branch
is stacked on PR #5304 and must not be merged before that prerequisite.

## Post-integration custody hardening

Before accepting a native quest build, the verifier now regenerates its exact
original-game quest using the source room-graph seed, current mechanic registry,
same length and fixed quest title. A different quest cannot be substituted by
simply recomputing the unkeyed source checksums and updating the GDScript
checksum constant. The verifier also checks the actual GameState / WorldMap
room-entered wiring and refuses an already-registered QuestRuntime autoload.

The local Godot save snapshot records an ordered, source-bound list of
successful visited quest rooms. Restore verifies this trace against the source
steps, current progress and recomputed earned rewards before accepting it.
This is **consistency verification**, not a cryptographic anti-cheat
guarantee: a local user able to rewrite game files can also forge an
untrusted offline save. Durable authenticated player progress remains a
separate future integration.
