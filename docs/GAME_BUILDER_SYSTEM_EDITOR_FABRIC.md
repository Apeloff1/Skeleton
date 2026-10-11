# Original Game Studio — System Editor Fabric

## What this PR actually builds

This release extends the local supervised editor in
`skeleton.ai.game_builder.game_workspace_ui` with **43 domain-specific original
game system editors** spanning 215 typed design controls. It is a real
configuration editor, not 43 new retail-ready engines. Existing proven maze
and living RPG/NPC work remains owned by the legacy runtimes; this extension
adds a broader authoring surface without pretending those runtimes have been
replaced.

The local design UI opens with **Platformer Physics**, and a grouped selector
allows designers to switch to any family. Each selected editor provides its
own bounded settings (no arbitrary source execution), validation, deterministic
configuration identity and one-click staging into the **existing exact-file
proposal/diff/human-commit pipeline**. Prior and demo trees remain immutable.

## 43 authoring families

| Category | Editors |
| --- | --- |
| World | maze, rpg, metroidvania, procedural_world, voxel, puzzle, roguelike, sandbox, quest_director, npc_society |
| Action | platformer, shooter, fighting, stealth, physics, parkour |
| Strategy | tactics, rts, tower_defense, city_builder, colony, factory, farming |
| Vehicle | racing, flight, sailing |
| Simulation | survival, ecosystem, economy, sports |
| Creative | rhythm, deck_battler, narrative, dialogue, cinematics, audio, animation |
| Product | ui_hud, accessibility, localization, networking, save_system, platform_profile |

A designer can create a genuine project and stage **systems/platformer.json**,
**systems/racing.json**, **systems/tactics.json**, etc., then inspect the exact
change and approve it. Every file has schema `skeleton.game_builder.system_editor.v1`
and a canonical settings digest. The source workspace validates those semantics
again at proposal and commit, rejecting unknown keys, invalid numbers, wrong
field types, unsupported enum choices, settings outside budgets, stale hashes,
document tampering, cross-system filename confusion and unauthorized commits.

## Executable mechanics previews (eight, not 43)

`preview_editor(...)` runs deterministic, finite Python reference slices,
with every action included in the evidence digest:

- Platformer — lateral movement, gravity integration, jumping, floor landing,
  edge clamping and an optional double jump.
- Circuit racing — bounded acceleration, braking/coasting, fixed-step distance,
  lap counting and finish state.
- Tactics — board movement, action points, attack-range checks, damage, turns.
- Tower defense — tower purchasing, enemy waves, range-limited tower damage,
  kills, leaks and credits.
- Shooter — ammo, reload, attacks, dodges, enemy defeat and player health.
- Survival — gathering, drinking, consumables, campfire crafting, hunger,
  thirst, rest and mortality.
- Rhythm — bounded timing offsets, perfect/standard windows, misses, combos,
  accuracy-based scoring and beat-period telemetry.
- Deck battler — attack, block, energy, enemy health, turns and victory.

The local UI also draws telemetry from the resulting immutable simulation state on a
Canvas: jump paths, racing speed profiles, tactics position and numeric resource
states. This display never modifies or impersonates backend proof results.

Previews are *mechanics proofs only*. They do not render finished playable
games, certify physical correctness or demonstrate execution on target hardware.

All other families return `authoring_only`, explicitly with
`simulation_executed: false`. The prior independent maze and RPG engines are
not mislabeled as new implementations merely because their settings are
available in the selector.

## Operating procedure

```bash
python -m skeleton.ai.game_builder.game_workspace_cli init \
  --root /tmp/original-studio --trusted-local-operator
python -m skeleton.ai.game_builder.game_workspace_cli create \
  --root /tmp/original-studio --project new_hybrid --genre hybrid \
  --trusted-local-operator
python -m skeleton.ai.game_builder.game_workspace_cli serve \
  --root /tmp/original-studio --port 8765 --open-browser
```

Within the loopback UI:

1. Select an active current project and a system-editor family.
2. Adjust system-specific controls.
3. Select **Validate and simulate preview** for a read-only local evaluation.
4. Select **Stage system into source review** to stage a canonical JSON document.
5. Inspect the source and diff, propose the exact change, then explicitly approve
   the human commit. Only this last stage changes the project.
6. Archive the project or freeze a demo if needed.

The same restricted loopback/CSRF-token protocol exposes `GET /api/editors`
and `POST /api/editor-preview`. No action accepts arbitrary scripts or invokes
a network provider; the server does not itself write a project during preview.

## Advanced — mandatory minimum progression level (11 October 2026)

Every listed editor now publishes a concrete **advanced design floor** with
five or more discipline-specific capability requirements. Basic/novice
progression is no longer a product milestone, and an authoring form alone
does not count as a completed advanced engine. Editor maturity is one of:

- `authoring_only`: validated advanced-design controls, **no playable runtime**.
- `advanced_reference_runtime`: a real replayable, command-driven game engine
  prototype with explicit evidence, not native hardware certification.

Eight engine families currently meet the second level:

1. **Platformer**: swept tile traversal, integer jump physics, optional
   double jump, finite dash cooldown, spike damage, checkpoint respawn,
   collectibles and exit gating.
2. **Tactics**: two independently controlled squad members, AP economy,
   position/collision checks, deterministic integer-grid line of sight,
   covered/enemy actions, guard, overwatch, medical consumables and terminal
   squad/mission outcomes.
3. **Tower defense**: three placeable/upgradable towers, finite costs,
   targeting priorities, armor, slowing effects, deterministic waves,
   enemy progress, kills, leaks and base damage.
4. **Racing**: acceleration/braking, integer track distance and laps, variable
   road grip/weather, tire wear, vehicle integrity, obstacle encounters,
   limited nitro, service pit windows, finite pit crews, finishing and scoring.
5. **Survival**: multi-biome travel, explicit depleting resource nodes, energy,
   hunger and thirst, weather exposure, resource-dependent craft/shelter/fire,
   tools and finite trading; open-ended play continues after building a camp.
6. **Shooter**: spatial projectile targeting, line-of-sight blockers, enemies
   with authored spawn positions and waves, finite ammo, movement and extraction.
7. **Deck battler**: finite hands, card costs and unique effects, poisoning,
   shields, deterministic shuffling, boss intents and item consumables.
8. **Puzzle**: five distinct logic families, interactive puzzles, finite
   rewinds and bounded independent search proofs.

Run `Start advanced scenario` in the studio after selecting one of these
three systems. Visible gameplay action buttons replay a **fully submitted
bounded command transcript** through the local, token-authenticated backend,
returning the same original seed, settings, per-turn state/event digests and
chained receipt hashes. The interactive canvas renders the authoritative
returned positions and resource state. Use `Independently verify replay` to
regenerate every state from the original actions and reject altered credits,
health, actions, evidence or event order.

Programmatic access is also available offline:

```bash
python -m skeleton.ai.game_builder.system_editor_cli play \
  --editor tactics --seed 7 --actions local-commands.json > local-evidence.json
python -m skeleton.ai.game_builder.system_editor_cli verify-play \
  --session local-evidence.json
```

The assembly graph includes reference-playable proof digests for these three
engines. It never equates successful reference simulation with a certified
Godot export or native executable. Integration of the actual other 40
game engines and producer-grade scene/node editors remains outstanding.

## Advanced multi-genre expansion — 8 real reference engines

The minimum **Advanced** design contract now has eight fully command-executing
reference families. In addition to platformer, tactical squad combat, tower
defense, racing and survival, this batch implements the following distinct
playable mechanics:

- **Arena shooter:** authored 2D arena cover/line of sight, positional enemy
  behavior, bounded reinforcement waves, ammo/reloading, dodging, healing,
  scored defeats and extraction-based victory. Shooter maps author enemy
  spawns, medical supply locations and a reachability-checked exit.
- **Deck battler:** finite authored card decks (strike, guard, pierce, drain,
  rally, scry, ward and spark), seeded deterministic shuffle, card energy,
  hand draw/discard and reshuffle, armor, damage, defense, poison,
  enemy intent rotation, potions and boss defeat. Card decks must contain a
  payable damaging option, and their opponents have reviewed intent cycles.
- **Puzzle:** independent gameplay for switch-and-door layouts, Sokoban-like
  crate pushing, circuit-node activation, timed phase gates and non-Euclidean
  paired portals, plus bounded rewind/history and customizable conditions for
  playable-but-not-necessarily-solvable worlds.

All eight accept exact-checksummed scene documents, replay signed action chains
through stateless local authority, and support resumable save files. These are
reference simulators, not yet retail-ready Godot/native engines; 35 other
editors continue to have distinct, explicit maturity labels rather than a
fabricated completed-game status.

### Real graphical authoring and proof search

The local studio now has a **cell-based graphical scene painting surface**
for shooter, tactics and puzzle boards, alongside their full structured source.
Selecting a paint tool and a map tile changes the local draft only. The user
must run canonical server validation, inspect the exact-source diff, and
explicitly approve a project-file commit. Incomplete paint actions or a stale
digest cannot bypass the scene or game-source validators. Other systems
retain their typed structured editors without falsely presenting a full
graphical terrain editor.

The new `advanced_puzzle_solver` runs bounded graph search over real puzzle
rules. It returns one of three non-interchangeable statuses:
`solved` (an action path independently replayed through the gameplay engine),
`unsatisfiable_exhaustive` (the reachable bounded state graph was fully
explored without a solution), or `unproven_search_budget` (search limits
prevented a conclusion). This is more rigorous than treating static map
connectivity as evidence of puzzle completion. It does not certify aesthetic
quality, contest difficulty or native hardware play.

Example offline proof command:

```bash
python -m skeleton.ai.game_builder.system_editor_cli scene-template \
  --editor puzzle --settings puzzle-settings.json > original-puzzle.json
python -m skeleton.ai.game_builder.system_editor_cli solve-puzzle \
  --scene original-puzzle.json --settings puzzle-settings.json \
  --max-states 12000 --max-depth 96
```

The scene editor also exposes **Prove puzzle solution / detect impossible
state**. User-selectable open-ended/non-solvable puzzles remain legal and
expressible through the `solution_required=false` control; proof status is
never silently altered to claim completion. Every solver result includes a
source/setting digest and explicitly leaves publication certification false.

## Authored advanced levels, survival regions and real savegames

Seed-only demos are no longer the sole option for the five advanced gameplay
families. The `advanced_level_scenes` module creates, validates and binds
original source scene documents to **the exact approved system configuration**:

- **Platformer:** editable spawn/exit, damaging hazard tiles, collectibles and
  checkpoints; source checks enforce bounds, uniqueness and safe separation
  between checkpoints and hazards
- **Tactics:** two squad starts, two enemy starts, occupied cover cells and
  mission objective; duplicate occupation, impossible geometry and
  disconnected objectives/enemy locations fail closed
- **Tower defense:** designer-authorized construction slots and configurable
  actual enemy-wave counts, enforced in the replay runtime
- **Racing:** circuit corners, obstacle location, selected weather and starting
  lane; vehicle physics and win conditions still execute the real runtime
- **Survival:** two to eight authored biomes/regions with explicit finite
  resources, merchant stocks and starting region/weather

The studio's **Create / validate authored scene** button produces typed JSON
that can be edited and revalidated. **Stage authored scene for review** sends
it to the existing exact-file diff/propose/approve workflow. The author must
first approve the parent `systems/<engine>.json`; changing that system after
a scene proposal invalidates the scene's digest at commit time. The gameplay
backend also checks the exact scene ID, source checksum, settings digest and
seed before it starts or replays a game.

`system_editor_assembly` now enumerates approved authored scenes and computes
a replay proof for each. These are evidence of deterministic execution, **not**
a claim that a level has been independently playtested, is enjoyable, or is
certified for release.

Portable `advanced_gameplay_save` files enable genuinely resumable sessions:
download a game save from the studio, import it in another local session, and
continue from the verified action transcript. Saves record typed settings,
authored scene, seed and action history rather than trusting mutable health,
resource or position state. Import re-executes all commands, compares
cryptographic identities and rejects modifications, stale settings,
counterfeit credits or resumed actions after a terminal game state.

Offline CLI examples:

```bash
python -m skeleton.ai.game_builder.system_editor_cli scene-template \
  --editor survival --seed 7 > survival-scene.json
python -m skeleton.ai.game_builder.system_editor_cli play \
  --editor survival --seed 7 --scene survival-scene.json \
  --actions actions.json > survivor-session.json
python -m skeleton.ai.game_builder.system_editor_cli save \
  --session survivor-session.json > survivor-save.json
python -m skeleton.ai.game_builder.system_editor_cli load-save \
  --savegame survivor-save.json
python -m skeleton.ai.game_builder.system_editor_cli continue-save \
  --savegame survivor-save.json --actions next-actions.json > continued-save.json
```

All paths are local, command data are bounded and typed, and game state
is restored through independent replay. No external models, arbitrary scripts
or native publisher credentials are executed. The `tests.test_game_builder_advanced_scenes`
suite exercises all five authored scenes, savegame tampering, continuation,
source review and local HTTP integration under the Ubuntu/Windows gate.

## Composing an original hybrid game

The newly implemented `system_editor_assembly` builds a content-addressed,
deterministic composition graph across all **approved, current** system files.
It orders systems, checks cross-editor constraints, preserves independent
mechanics preview proofs, surfaces coupling edges and explicitly lists
missing production adapters and remaining independent release reviews.

The **Review assembled current systems** UI button runs this check without
altering source. It detects incompatible gravity scales, platform-era NPC
budgets, missing NPC dialogue population, unsupported multiplayer authority,
unbounded sandbox saves, and undersized audio channel budgets.

The offline command line also exposes precise automation-friendly operations:

```bash
python -m skeleton.ai.game_builder.system_editor_cli list
python -m skeleton.ai.game_builder.system_editor_cli template --editor tower_defense
python -m skeleton.ai.game_builder.system_editor_cli preview --editor racing
python -m skeleton.ai.game_builder.system_editor_cli assembly \
  --root /tmp/original-studio --project new_hybrid --trusted-local-operator
```

These commands validate or inspect local authored configurations; they do not
auto-approve edits, install engines, run untrusted external tools or publish a
game. Cross-editor coupling edges are shown as **not yet integrated** until
their production runtime adapters actually exist.

## Unfinished implementation work — factual release blockers

- Connect each of the 35 authoring-only editors to real genre mechanics,
  renderers, game-state save/load, playtesting and export adapters.
- Integrate editor JSON configurations into the existing
  `GameBuildIntent` and authored living-story/compiler contracts, rather
  than making broad genre support a pretend replacement for the proven maze
  and RPG paths.
- Add playable genre-specific UI canvases, in-game simulation and visual
  node/timeline editors for complex systems; present controls are structured
  settings editors and eight headless mechanics previews.
- Verify full visual performance/accessibility; execute on physical hardware
  and validate the selected platform SDK/homebrew/legal release requirements.
- Reconcile separate open PR #3641 world/NPC material through a reviewed merge
  rather than copying its unmerged source or losing either history.

The existing exact-head **AI Game Builder 500 Levels** gate now includes
`tests.test_game_builder_system_editors`. The proposed code is not considered
shippable simply because its configuration hashes or previews validate.
