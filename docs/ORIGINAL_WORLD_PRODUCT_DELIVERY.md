# Original Worlds — Actual Game Product Delivery

**Architecture:** `original-world-product.v1` (2026-10-11).
**Repository:** `Apeloff1/Skeleton`, draft PR #3641.
**Product claim:** A real, offline, playable Python desktop/reference game, with
persistent physical terrain, active inhabitants, executable game mechanics,
original causal world laws, vector/raster visual outputs and a reproducible
portable build. This is **not** a complete AAA/console game engine or a claim
that 122.88 million separate games have been written, polished or released.

## What was actually implemented

### 1. Sparse, physically consequential landscape

`original_world_product_terrain.py` has deterministic, on-demand **32×32**
terrain chunks with signed global coordinates. Coordinates map to specific
reproducible forest, stone, meadow, marsh, cliff, spring, sand and orchard
biomes; they are not preallocated in memory. The player's immediate local
world exists within an already selected 122.88-million-index
source-law/genre/architecture/living-system/continuation configuration.

The player can physically travel one adjacent tile per action, jump bounded
elevation steps, extract nonrenewing stone/wood/food/water from individual
locations, construct material-backed bridges and ramps, excavate accessible
slopes, build hearths/mills/beacons, eat real provisions and recover energy
through rest. Elevation, marsh flooding and cliffs prevent invalid shortcuts.
The editor builds each visited location from authored seed rules and records
only changed tiles (maximum 2,048 sparse writes per session).

**This is tile collision and a resource economy, not continuous 3D rigid-body
physics, a GPU voxel game or infinite active terrain.** Geographic coordinates
are bounded to +/-2^20 tiles, and each active level is small.

### 2. Twelve actual autonomous residents

`original_world_product_agents.py` implements separate stable actors with
profession, physical coordinate, energy, hunger, health, skill, experience,
carried resource and relationships:

forager, forester, mason, farmer, builder, courier, scout, guardian, healer,
naturalist, engineer and caretaker.

NPC decisions use bounded real tile-path BFS and finite physical resources.
They can actually travel, harvest one unit from a specific editable cell,
carry that unit home to a depot, consume inventory food, starve if food is
unavailable, scout traversable regions, help residents and train job skills.
Household goods do not magically appear via population counters.

This is deterministic, resource-bound **goal-directed game AI**, not a
provider language model, a full dialog model, a human-equivalent artificial
general intelligence or complex real-time crowd planning.

### 3. Integrated multiplayer-ready *state*, single-player product

`original_world_product_session.py` is a single immutable transaction
boundary for one original-law source world, its 24-room architectural map,
its selected genre and progression mode, one local streamed terrain viewport
and its society. All actual world turns advance the NPC clock and terrain
turn together; inconsistent or forged clocks are rejected.

Physical inventory can be transferred to the wider world with
`studio deposit_wood`, `studio deposit_stone` and `studio share_food`.
Transfers remove the exact goods from the local inventory before crediting
the source game's physical material or civic supplies. Residents can receive
finite player food through proximity-gated gifts, and professions may be
reassigned through real trust/consent costs. World, terrain and agents all
have an immutable event ledger and nested checksum-protected save.

No multiplayer server/network replication is delivered by this file.
Calling the state machine network-ready refers only to deterministic,
serializable state, not proven networking or concurrency.

### 4. Real graphics and real desktop controls

`original_world_product_render.py` emits **standalone SVG**, native raster
**P6 PPM** images and optional ASCII map views of the *actual game state*.
Structures, physical geography, persistent edits, NPC positions, player
marker and player inventory are reflected directly in render output.

`original_world_product_desktop.py` implements a genuine Python Tk native
desktop canvas, keyboard/clickable movement, local action controls,
living-system buttons, complete game command palette, original mission
progress, residents, geography and explicit file saving. The native
desktop view requires an installed Tcl/Tk desktop display. The headless
world engine and all image/export commands run without a display.

The renderer is 2D; no 3D mesh pipeline, photorealistic output,
real-time procedural audio or native GPU game graphics is certified.

### 5. Inspectable original-premise quests

`original_world_product_missions.py` ties each of the sixteen original
causal disciplines and ten consequence regime families to **evidence from
player actions and durable state**. The director preserves the source's
handwritten premise, player agency, failure mechanism and ending policy.
It evaluates physically mined resources, cooperative relationships,
installed passages, actual time and echoes, research, construction,
simulated economies and global causal changes.

The missions do not grant free rewards and explicitly avoid pretending that
a domain proof is a complete bespoke implementation of any original fictional
world law. The 1,424 written causal-root premises still need individual
level design and mechanics beyond these sixteen domain patterns.

### 6. Distribution pipeline

`original_world_product_bundle.py` builds a **deterministic portable
Python `.pyz` executable application**. It resolves only required internal
original-game source modules, deliberately excludes unrelated Skeleton
package initializer side effects and writes a per-file SHA256 provenance
manifest. The bundle needs the destination machine to provide Python 3.11+
and, for the optional desktop view, a working tkinter installation.

`scripts/original_world_native_launcher.py` and the
`Original World Native Builds` GitHub workflow implement native
PyInstaller packaging on **Windows x64** and **Linux x64**. The build freezes
the self-contained Python archive, launches the compiled executable
without graphics, restores an actual saved game, advances the world,
and produces a verified SVG and raster PPM. Native outputs are uploaded
as CI artifacts.

The Linux native build has run successfully. Windows runner checkout
previously failed on unrelated ultra-long repository filenames; a sparse
checkout of only the original-game source and launcher was introduced.
**Windows binary success must be verified from its own run** and never
inferred from Linux. All native binaries remain **unsigned**, without an
installer, code-signing authority, app-store approval, legal right to third
party assets, or platform console build validation.

No copyrighted commercial game assets, proprietary ROMs or developer SDKs
are imported into the authored archive.

## Actually play the product

From repository root:

```bash
# Open a real 2-D native window with game controls.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice --system trophic \
  --arc sandbox --desktop --save my-original-world.json

# Play the same world entirely in a terminal.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice --system trophic \
  --arc sandbox --interactive

# Real resource transactions, physical inhabitants and a world turn.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice --system trophic \
  --arc sandbox \
  --actions-json '[{"layer":"terrain","verb":"forage","amount":2},{"layer":"studio","verb":"share_food","amount":2},{"layer":"causal","verb":"end_turn"}]' \
  --svg world-view.svg --ppm world-view.ppm \
  --save world-save.json --missions

# Resume saved game.
python -m skeleton.game.generation.original_world_product_cli \
  --load world-save.json --interactive --save world-save.json

# Reproducible portable launcher for other Python-equipped computers.
mkdir -p dist
python -m skeleton.game.generation.original_world_product_bundle \
  --output dist/original-world-studio.pyz
python dist/original-world-studio.pyz --inventory
python dist/original-world-studio.pyz --desktop
```

In the native command palette, gameplay follows these layers:

`terrain walk north`, `terrain jump east`, `terrain chop`,
`terrain forage`, `terrain build_hearth`,
`studio share_food`, `studio gift 0`,
`studio assign 0 engineer`, `living reseed`, `mode toggle 0`,
`spatial travel 1`, `arc reflect`, and `causal end_turn`.

## Tests and executable scope

The dedicated original-world workflow runs the existing atlas,
world-root/compiler, four handcrafted-playable scenarios, 10 genre loops,
12 narrative continuations, 10 topologies, 10 autonomous living systems,
plus new actual local terrain, physical NPCs, product session, renderers,
authored-root evidence goals and cross-process portable `.pyz` tests.

The native workflow additionally verifies its binary outputs on platform
runners. Production multi-platform shipping is blocked until native
CI, performance, assets, UI, and legal review are complete.

## Substantial unfinished work — concrete, not hidden

1. **Bespoke originals:** The 1,424 individually authored root premises
   are not 1,424 full authored campaigns. Much of the vast combinatorial
   game index uses shared reference game mechanics. Requires per-law
   rules, original geography, authored puzzles, narratives, endings,
   progression, dialogue, inhabitants, original art and tuning.
2. **Real-time physics and rendering:** Need robust fixed-step collision,
   character controllers, ropes/vehicles, rigid-body and fluid tiers,
   tiled GPU sprite batches, optional streamed volumetric 3D,
   particles, shaders, lighting, animations, responsive cameras,
   accessibility and tested frame rates.
3. **Wider worlds:** Local chunks are generated on demand and saved
   sparsely, but this release is bounded by 2,048 modified tiles and
   resident planning radius. Cross-region NPC schedules, streaming
   worlds, LOD, wide-path planning and world-origin shifting remain.
4. **Deep AI and ecosystem:** 12 actual simple professions exist, not
   a mature ecology, diverse authored people, language models, social
   memory, emergent narrative planning or crowd/traffic simulation.
5. **Products and hardware:** Actual Windows and Linux executable builds
   need full verification and signing; a polished Windows installer,
   macOS package/notarization, console homebrew adapters for legal
   permitted targets, native ROM QA, mobile support, gamepad/VR UI,
   asset packs and release update system remain.
6. **Quality/security/legal:** Performance budgets on user equipment,
   scene/quest authoring GUI, scripted lore, original soundtrack,
   licensing/legal checks, exploit protections, fault recovery,
   external playtesting and commercial quality are not certified.

Do not fill the completion dashboard by counting game recipe
permutations as completed separate games. **Progress should be
measured by verified independent playable game releases and meaningful
original authored gameplay, not address-space size.**
