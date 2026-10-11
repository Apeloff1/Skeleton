# Dual-runtime original game production — playable game, not just a design plan

Canonical implementation owner: skeleton/ai/game_builder. This source
release extends the existing typed GameBuildIntent -> PlayableWorld ->
demonstrate_solvable -> CompiledPlayableProject pipeline. It does **not**
introduce a second procedural generator, AI inference service, rights owner,
state store, or unsupported publication interface.

## Produce a native-editable project and browser game together

Save intent.json with an original project intent:

~~~json
{
  "project_id": "my-first-original-game",
  "title": "Crystal Cartographer",
  "subtitle": "Explore a new world one step at a time.",
  "seed": 2061,
  "width": 19,
  "height": 15,
  "levels": 3,
  "collectibles_per_level": 3,
  "hazards_per_level": 4,
  "theme": "forest",
  "starting_health": 3
}
~~~

The existing builder already validates this input and proves a safe route.
Run from the repo root, after operator identity/authority has been handled by
the host:

~~~bash
python -m skeleton.ai.game_builder.dual_runtime_cli \
  --intent ./intent.json --output ./my-game \
  --trusted-local-operator
~~~

This creates a new directory and **refuses to overwrite** any existing
project. The trusted-local-operator flag only acknowledges authorization
established by the caller: it is not a login check.

| Output | Purpose |
| --- | --- |
| index.html | Fully standalone CSP-restricted game; works offline |
| godot/project.godot | Open with Godot 4.2+ to edit/run a native 2D project |
| godot/scenes/main.tscn | Concrete launchable game scene |
| godot/scripts/main.gd | Original Godot runtime implementing turn rules and renderer |
| godot/world.json | Runtime data from the exact same typed world |
| godot/proof.json | Engine-readable copy of Python winning action proof |
| proof/verified_solution.json | Full winning Python action replay |
| release.json | World/proof digests, SHA-256 file checksums, truthful target readiness |
| README.md | Runtime controls and validation boundaries |

No packaged ROMs, BIOSes, commercial game assets, scraped text, model weights,
SDK keys or external scripts are required or shipped.

## Optional designer-authored maps: an actual editing path

Besides procedural mazes, creators can draw an original tile level as a list
of equal-length strings. Only # wall, . floor, S spawn, G exit, C collectible,
and H hazard are accepted. No scripting language or third-party assets are
imported. For example, place the following exact JSON into authored.json:

~~~json
{
  "schema": "skeleton.game_builder.authored_tiles.v1",
  "intent": {
    "project_id": "my-cave",
    "title": "Original Cave",
    "subtitle": "A hand-edited original map.",
    "seed": 42,
    "width": 9,
    "height": 9,
    "levels": 1,
    "collectibles_per_level": 2,
    "hazards_per_level": 1,
    "theme": "arcade",
    "starting_health": 3
  },
  "levels": [[
    "#########",
    "#S..C...#",
    "#.#####.#",
    "#.......#",
    "#...H...#",
    "#.......#",
    "#..C..G.#",
    "#.......#",
    "#########"
  ]]
}
~~~

Supply the identical intent object as a separate intent.json, then run:

~~~bash
python -m skeleton.ai.game_builder.dual_runtime_cli \
  --intent intent.json --authored-world authored.json \
  --human-reviewed --trusted-local-operator \
  --output ./my-authored-game
~~~

The importer requires exact schema, intent identity and explicit review;
rejects malformed geometry, extra fields, duplicate JSON keys, oversized
files, symlinks, missing goals, wrong item counts and unsolvable exits;
recomputes a hazard-free winning trace with the canonical BFS solver; then
compiles browser/Godot gameplay with the **same** simulator and release
receipt as generated levels. The manifest records the authored algorithm,
not the procedurally generated one. The reviewed flag only acknowledges
geometry review: it does not grant an intellectual-property license.

## Two runtimes, one gameplay contract

Both outputs implement the **same reference behavior**:

- Four-direction movement through walls and corridors, one input per turn.
- One-time collectible scoring (+10), exit locked until all pickups are found.
- Hazards cost one health on tile entry; zero health means defeat.
- Completion awards +100 and enters the next level, or ends in a victory.
- Terminal state cannot accept more moves.
- Undo for up to 256 actions, restart, and a 20,000-step bound.
- Godot saves only local action history with a world digest binding and
  **replays** it upon load instead of trusting a serialized score/position.
- Python reference proof solves all generated levels while avoiding hazards.

In Godot, use WASD, arrow keys, gamepad D-pad or touch swipes to move; Z or
gamepad B to undo; R or gamepad Start to restart; F5 to save and F9 to load.
Hardware input latency and mobile viewport usability need device testing. The HTML build also has accessible touch controls, an
accessible text map and optional downloadable browser action logs.

## Verification and operating boundaries

Run:

~~~bash
python -m unittest tests.test_game_builder_dual_runtime tests.test_game_builder_authored_tiles -v
python -m unittest tests.test_game_builder_playable_world \
  tests.test_game_builder_playable_export -v
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
~~~

If Godot 4 is on PATH, the dedicated test also attempts a headless native
replay of the Python winning trace. The scene runs all verified actions and
checks native final score, health, position, level, collectibles and steps
against the independently executed Python state, exiting nonzero on
divergence. A direct operator command from the output folder's parent is:

~~~bash
godot --headless --path ./my-game/godot -- --verify-proof
~~~

The only success receipt is a NATIVE_REPLAY_OK line containing the world
digest. A missing engine causes an explicit skip; source generation alone is
**not** a claim of a working compiled Godot executable. Hardware, controller,
conformance, store approval, packaging, usability and console-specific
emulator certification need independent follow-up evidence.

Every packaged file except the manifest is SHA-256 checked. The manifest
contains a content digest over its body. Export renders/verifies before
writing and stages a temporary folder in the destination's parent before
renaming it into place. Outputs are new snapshots, not updates
to any existing user's edited Godot project.

Research citations stay outside executable Godot code. Optional researched
game designs must first be approved through the existing RightsLedger and
game builder source-clearance flow. Original game inspiration does not
authorize copying a protected character, distinctive art, music, text,
map layouts or proprietary game engine code.

## What is still missing for fully featured game production

This milestone delivers *one original playable 2D puzzle/adventure vertical
slice*, not a universal game editor or all-console native renderer.
The next meaningful production layers are editor-authored quests/dialogue,
genre-specific controls and combat, touch/controller mappings in native
projects, save migrations, original art/audio composition, authored content,
automated emulator/runtime replay comparisons, UX playtesting, performance
budgets, full Godot desktop builds and platform/legal release gates.

World/NPC atlas branches can later feed their own approved geometry and
encounter data through a versioned adapter, after their contracts land;
they are deliberately not imported from an open PR into the release path.
