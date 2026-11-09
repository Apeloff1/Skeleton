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

## Tenth genuine original gameplay family: Factory & Automation

The `factory` editor is no longer just fields for machine counts and belt
speed. `advanced_factory_runtime.py` adds an independently replayable,
source-bound manufacturing game. The authored original factory has one to
four operative machine stations of bounded smelter, assembler, packer and
optional generator types, unique sequential machine IDs, finite ore/coal
deposits, a configurable shipment objective and priced market.

Players construct, upgrade, toggle, liquidate and repair real machines;
mine finite ore and purchase from finite coal reserves; spend coal on local
generation, allocate actual energy to machines, set speed vs efficiency,
scrub paid pollution, and ship batches of *actually manufactured* goods.
Ore is consumed to forge plates, plates become components, and components
become packaged product through bounded belt speed and machine levels.
Energy scarcity stalls individual machines, monthly-style operational time
increments and machine wear create maintenance obligations, and pollution
shutdown or bankrupting supply chains can terminate a run. Only two or
more authentic manufacturing contracts meeting the authored target permit
success: no fabricated shipments or unlimited-money outcomes.

The separate `advanced_factory_godot.py` is a **real native Godot game**
that independently implements the same throughput/power/wear/economy
mechanics, draws a live machine-floor status view and accepts construction,
production, mine, shipment, pollution, upgrade, repair, switch and sale
orders. Gamepad controls cover daily production and assembly actions.
Its `--verify-factory` mode begins from original source state and
independently replays the reviewed command history, comparing every full
factory state field including nested sorted machine stats and immutable
station roles. ZIP distribution and source export are not falsely reported
as native runtime/hardware certification.

Game Studio, offline operator-authorized `godot-export` CLI, deterministic
`original-godot-factory/` source ZIP, strict canonical scene authoring,
and native-proof/tamper rejection tests now cover this tenth real genre.
Dedicated `game-builder-advanced-factory-native.yml` executes eight authored
factory histories (resource mining, powered three-stage lines, contract win,
maintenance, smart power, finite coal, repairs, efficiency and pollution)
on Linux and Windows **and runs their exported desktop game binaries**.
The broader advanced regression gate keeps all ten reference engines and
source custody tested on both operating systems.

**Evidence requirements:** count `factory` as an independently verified
native game only after its exact-head Godot history and desktop binary checks
both succeed. The previous nine native engines are proven, with 10/43
(23.3%) now having real reference gameplay but 33/43 editor families still
authoring-only. These reference games are bounded examples, not comprehensive
production-quality coverage of every subgenre or console/PC hardware.
PR #3642 remains draft until readiness gates and broader app priorities
are separately assessed.

## Ninth actual original gameplay family: Godot 4 Farming & Ecology

This is a **new game**, not a ninth adapter for an existing reference
engine. `advanced_farming_runtime.py` introduces independently replayable
deterministic farming commands and game rules, while
`advanced_farming_godot.py` implements those rules again in genuinely
executable offline GDScript. Typed editor `farming` is now a real game,
not just the old parameters (`crop_types`, `growth_days`, `field_tiles`,
`seasons`, `livestock`).

Core runtime: one to four playable field sectors from the configured
bounded acreage, authored individual soil and moisture, deterministic
weather and seven-day seasons, three crop classes selected from available
crop types, growth stages dependent on moisture and fertility, periodic
pests, irrigation and compost, finite seeds and fertilizer, harvest yield
and soil depletion, finite market purchase and sales, optional livestock
with finite feed, hunger and products, contracts and reputation, and a
meaningful victory threshold (**80 coins, 8 actual harvested units, 2
completed market contracts**). Unsustainable farms can bankrupt under
strict conditions; impossible commands fail closed before state mutation.

The authored farm scene permits only canonical sequential plot IDs,
integer soil/moisture bounds, approved weather and market multipliers;
it is content addressed and settings-bound. Every original game source is
shipped with an immutable proof transcript and hashes. In Godot
`--verify-farming` mode, the independent GDScript engine reconstructs
the same authored land, separately executes player commands, and checks
**every final economy/field/weather/livestock/contract state field**, not
just an end banner. Crop plot metadata is normalized at the proof
boundary for Godot's JSON int/float interoperability.

The reviewed offline CLI and local token-gated Game Studio can now
download **nine** independently authored native game project source ZIP
families, using distinct `original-godot-farming/` custody. Exporting
source is **not** native runtime verification, authorized console SDK
use, third-party art/IP rights or a commercial release certification.

The new `game-builder-advanced-farming-native.yml` workflow includes
eight original farm scenarios, with real planted/harvested crops, weather,
saturation, profitable market win, livestock products, fertilizer use,
season toggles, pests and scarce acreage. It executes the Godot game on
both Linux and Windows and exports and independently executes both
desktop game binaries. The full advanced regression workflow includes
the ninth reference engine, native source, authorized API/CLI/Studio,
forged receipt resistance and strict authored-scene checks.

Status is evidence-gated: **nine of 43** typed editors have a real Python
reference engine, and the original prior **eight of eight** native
engine families are already independently verified. Promote Farming
from candidate to ninth native-verifiable game only after its dedicated
exact-head Godot and executable jobs actually succeed on both OSes.
The remaining 34 typed families require equally substantive original
gameplay and native development; editor parameter counts do not count
as finished games.

## Eighth original native gameplay candidate: Godot 4 open-ended Survival

`advanced_survival_godot.py` provides an independent, genuinely playable
Godot 4 offline survival/crafting simulation. Unlike games with a forced
objective victory, the original survival world **does not have a solved
end state**: permanent-camp and self-sufficient-outpost milestones signal
achievement, but play continues until resource constraints or survivor
death end the run. This is deliberate, not an unfinished ending.

Canonical authored scenes select a bounded two-to-eight-region world,
starting region, biome-specific finite food/wood/water/stone/game reserves,
merchant supplies and initial weather. Native rules independently execute
twelve meaningful survival commands: forage, gather wood, mine, drink, hunt,
cook, craft tools, light a fire, build shelter, trade, travel and rest.
Mechanics include non-replenishing local reserves and finite market supplies,
energy-limited movement/gathering, crafting costs and boosted harvest with
tools, weather shifts every six turns, hunger/dehydration every two turns,
limited temporary fires, healing, heat/cold exposure, shelter levels one
through three, progression achievements and terminal survivor death.

The native GDScript runtime neither reuses Python gameplay frames nor
fetches external data. Each user action mutates a distinct native world state,
renders live biome/resource/weather/crafting/status information and supports
keyboard and gamepad. The `--verify-survival` native Godot mode reconstructs
the authorized scene and independently replays every reviewed action before
comparing **all 21 complete gameplay state fields** (nested finite region
inventories, health, survival economy, milestones, weather, event ordering
and terminal outcomes). Numeric values in nested JSON regions are normalized
strictly at the proof boundary to prevent superficial float/int mismatches.

The local Game Studio's authenticated ZIP handoff and operator-authorized
offline `godot-export` now support **all eight advanced gameplay reference
families**, each with distinct native source/game rules. Survival uses its
own deterministic `original-godot-survival/` source root and manifest.
Exports cannot overwrite an existing project, and a generated ZIP must
not be described as hardware-certified or as proof of on-device execution.

Dedicated `game-builder-advanced-survival-native.yml` executes eight authored
native world histories on Linux and Windows: initial resource gathering,
travel and region trading, two-stage settlement/outpost progression with
continued gameplay, fire/hunting/cooking, finite market trade, changing
weather, multi-region exploration and a terminal resource-loss death. It
then exports and **executes real native desktop binaries on each OS**.
The broader advanced regression suite includes scene provenance, replay
tampering, source ZIP custody, local CLI, API and Studio controls. Native
Survival becomes **verified** only after exact-head replay and executable
checks are successful on both OSes. Even with eight of eight reference
engines verified, the other 35 editor families remain authoring-only and
overall Game Creator release readiness remains unknown.

## Seventh native candidate: standalone original Godot 4 circuit racing

`advanced_racing_godot.py` adds an independently executing, original
Godot 4 race game, beyond the previous Python-only racing simulation. Its
GDScript physics simulates real authored circuit position, lap crossing,
acceleration, braking, coasting and three-lane steering, finite nitro,
pit crew/service capacity, fuel expenditure and fuel starvation, weather
grip (dry/wet/storm), corner understeer tire and engine damage, center-lane
obstacle collisions, tire wear, mechanical limp mode, terminal engine
destruction, checkpoint-style lap accounting and championship scoring.
The player uses WASD/arrows, Space, B, P, R, or gamepad controls.

A playable, original rendered circuit includes race direction, player lane,
authored corners/obstacle, live speed/laps/fuel, car/engine integrity and
results. Gameplay uses **native integer-step GDScript**, not Python-generated
frame playback. The reviewed source `game.json`, signed scene/settings
hashes and `proof.json` bind every authored variant to the source model.
When invoked with `--verify-racing`, Godot independently reexecutes all
approved commands and compares all **22** gameplay fields including
unmodified scene weather, exact corner/obstacle identity, tire/engine/fuel,
pit/nitro costs, lap crossing event order and win/fail results.

The authorized offline `godot-export` CLI and local token-gated visual
studio now produce a seventh distinct fixed-path native source bundle
`original-godot-racing/`. ZIP generation is source delivery, **not**
evidence of Godot execution or a hardware/publication certificate.

`.github/workflows/game-builder-advanced-racing-native.yml` is a
separate exact-head native proof lane: eight genuine original circuits on
Ubuntu/Windows (all three weather classes, steering, pit, boost, damage,
multi-lap completion and terminal finish) and exported game-binary execution
on both operating systems. Native racing **is only verified after both OS
jobs and real exported binaries succeed**. The full advanced reference
regression suite includes the source-custody, command-replay, forge-rejection,
offline CLI and Game Studio race tests. Until native CI succeeds, count
racing as implemented but unverified.

## Sixth independent native adapter: original Godot 4 tower defense

The `advanced_defense_godot.py` native game now executes the **actual**
source-approved finite-wave rules of the advanced `tower_defense` reference,
rather than animating a Python state. Authored `build_slots` and a strict
1–12 `waves` count are respected in independent GDScript gameplay. Systems
include integer-tick enemy spawning/movement, finite construction credits,
three possible tower positions, level-one-to-three upgrades, sells and
refunds, first/strongest targeting, authored tower range, armor mitigation,
higher-level slow effects, kill rewards, resolved waves, enemy escapes and
base-HP damage, objective win and terminal base destruction. The player
controls the simulation with 1–3 (build), Q/W/E (upgrade), Z/X/C (sell),
F/S (target priority), Space (advance a tick), Enter (four ticks), R (reset)
and gamepad actions.

A typed, reviewed Godot source package carries the exact scene, settings,
source hashes, independent Python session action log and final proof state.
The native `--verify-defense` mode starts from its *own* original game
world, executes the same bounded commands through GDScript and compares all
**17** top-level final gameplay fields, including nested tower/enemy states,
finite resources, target policy, wave accounting, event order and outcomes.
Godot's JSON integer/float representation is normalized in proof values,
not substituted into the independent simulation.

The authorized offline `system_editor_cli.py godot-export` and the local
token-gated visual studio now export a sixth native source-family under a
distinct stable `original-godot-tower_defense/` ZIP root. Replay tampering,
stale settings, unsupported games, unauthorized writes and destination
overwrites are rejected. Creating the portable project does **not** claim
it has executed on any platform; published releases need separate rights,
game-quality and hardware reviews.

Dedicated exact-head CI `game-builder-advanced-defense-native.yml` runs
**eight original, authored defense scenarios** on Windows and Linux:
basic waves, upgrades, sell/rebuild, target-priority switching, completed
short wave, long lane, enemy escape and destroyed base. The gate also
exports and independently executes real Windows and Linux desktop
executables. Report six of eight native reference engines as complete
**only when these exact-head native checks pass**, not when source exists.

## Fourth independent native engine: authored original Godot 4 arena shooter

The `advanced_shooter_godot.py` adapter executes a playable, offline, original
Godot 4 combat game **independently** of the Python source simulator. It has
real 2D authored-grid movement, swept two-step dodge displacement and finite
dodge charges, cover-blocked movement and line-of-sight targeting, integer
Bresenham firing paths, proximity-and-identity-based target selection,
weapon damage/armor, ammunition and reloading, cover stance, finite medkits,
tactical pickups, bounded reinforcement waves, spatial enemy patrols and
line-of-sight attacks, terminal defeat, mission score, and an actual
enemy-clearance + extraction-tile victory condition. The user can play with
WASD/arrows, F/Space to fire, R reload, C cover, H heal, Shift dodge east,
Enter extract, Backspace restart or gamepad buttons.

Every map uses canonical `advanced_level_scenes.py` geometry with exactly
three spawn anchors, valid cover and collectible placements, reachable
extraction and source/setting digests. Native JSON numerical coordinates are
normalized into integer vectors at the source boundary. Replay witness mode
`--verify-shooter` starts the native arena from its **own authored scene**,
replays bounded commands using the GDScript combat rules (not Python output
snapshots), then checks the full `PROOF_FIELDS` contract: position,
dimensions, HP and supplies, evasion/cover, enemy states and positions,
replacements, ammunition, pickups, wave and kill counts, score, event order,
and win/loss state. Any mismatch is an execution failure.

The local Game Studio and reviewed `godot-export` CLI now support a **fourth
native project** (`shooter`) alongside `puzzle`, `platformer`, and
`deck_battler`. Its ZIP uses a unique fixed `original-godot-shooter/` root,
explicit operator authorization for writes, independently replay-verified
Python session source, and immutable content hashes. A ZIP handoff does not
claim the new Godot runtime was executed on the user's computer.

The dedicated `.github/workflows/game-builder-advanced-shooter-native.yml`
uses **nine authored arena scenarios on Ubuntu and Windows**: default combat,
cover, dodge, movement, enemy tactics, firing + reload, multi-target
elimination, a new reinforcement wave and completed extraction. The job
runs each generated Godot project, requires exact native/Python parity, and
then exports **and executes** real Linux and Windows desktop game binaries.
Those native completion claims depend on the exact-head workflow result;
source creation alone is not confirmation. Console certification, copyrighted
assets and publication permissions remain separate human reviews.

## Third independent native engine: original Godot 4 deck battler

The native adapter set has been extended beyond the original puzzle and
platformer implementations. The `advanced_deck_godot.py` engine independently
executes the eight original card effects and all turn/economy transitions in
Godot 4 GDScript. It does not call the Python runtime from within Godot or
simply animate precomputed outcomes.

**Native rules, advanced floor:** deterministic seed-derived deck shuffles;
hand limits, finite draw/discard and reshuffle; typed cards `strike`,
`guard`, `pierce`, `drain`, `rally`, `scry`, `ward` and `spark`;
energy-per-turn and explicit card costs; shields, piercing attacks, hit
damage and drain healing; strength and poison; rotating enemy attack/defend/
poison/charge decisions; finite potions, boss defeat and terminal-player
failure. Keyboard keys 1–5 select hand cards; Enter ends a turn; H uses a
potion; R restarts. Gamepad actions and status-rich card rendering are
included.

The exporter binds its native project to the exact approved scene, settings,
seed and all gameplay transcript actions. A type-checked
`game.json` + `proof.json` is included with Godot sources, export presets,
README, and a content-addressed manifest. Replay mode `--verify-deck`
executes the entire native game independently then compares **29** Python-
verified gameplay fields, including draw/discard order, enemy intent, state
changes, action-result events and terminal outcome. Mismatches fail the
native executable verification.

The local studio download, human-authorized offline `godot-export` CLI and
stable original-project ZIP now accept `deck_battler` alongside `puzzle`
and `platformer`; all remaining advanced reference engines still fail
closed for native export. Example:

```bash
python -m skeleton.ai.game_builder.system_editor_cli scene-template \
  --editor deck_battler --seed 9 > original-deck-scene.json
python -m skeleton.ai.game_builder.system_editor_cli play \
  --editor deck_battler --seed 9 --scene original-deck-scene.json \
  --actions original-commands.json > original-deck-session.json
python -m skeleton.ai.game_builder.system_editor_cli godot-export \
  --session original-deck-session.json --output ./original-deck-game \
  --trusted-local-operator
godot --headless --path ./original-deck-game/godot --import
godot --headless --path ./original-deck-game/godot -- --verify-deck
godot --path ./original-deck-game/godot
```

The dedicated `game-builder-advanced-deck-native.yml` GitHub workflow
builds **13 independent native scenarios**—eight card families, victory,
enemy cycles, poison, deck reshuffle and potion use—on both Windows and
Linux and exercises actual desktop executable exports. Unit and browser
tests also reject stale settings, tampered sessions, unapproved exports and
unsafe source overwrites. A generated ZIP is not certification that hardware
or a specific game build was actually tested. Native parity must be judged
from the successful exact-head CI result rather than source presence.

**Maturity accounting:** 43 typed families keep the required Advanced
design floor; eight have executable Python reference gameplay. Of these,
native parity is implemented for three distinct families, and it is
considered verified only after its dedicated CI succeeds. The other five
remain Python-only prototypes; the other 35 families remain authoring-only.
Non-homebrew licensed assets, restricted console SDKs and commercial
publication need separate authorization and rights clearance.

## First real native adapter: original Godot 4 puzzle game

The `advanced_godot_export.py` native exporter ports the **advanced puzzle**
family to an independently implemented, playable **Godot 4.4.1+** GDScript
game. This does not mean all eight advanced reference families have native
adapters; shooter, deck battler, tactics, survival, racing, tower defense and
platformer still require equivalent native-runtime implementations.

The generated offline, original, asset-free Godot project contains:
- `godot/project.godot`, `scenes/main.tscn` and the runnable
  `scripts/main.gd` with original controls and grid rendering
- `godot/game.json` with canonical typed settings and authored level geometry
- `godot/proof.json` with the exact independently verified Python gameplay
  action transcript and selected expected final-gameplay fields
- A source hash manifest, fixed Linux/Windows export presets and local README

Godot's GDScript independently executes switches, doors, pushable crates,
circuits, timed phase gates, portal movement, rewind and victory predicates.
It **does not read the Python final state as authoritative gameplay**.
The headless `--verify-advanced` mode plays all actions using the real native
simulation, then fails closed unless position, crate state, switch/circuit
progress, phase, portal visitation, undo budget, time and terminal outcomes
match the independently verified Python session. This is an integration
proof, not a human playtest or claim about all desktop hardware.

Usage (after explicitly reviewing the original authored puzzle and actions):

```bash
python -m skeleton.ai.game_builder.system_editor_cli godot-export \
  --session reviewed-puzzle-session.json --settings puzzle-settings.json \
  --output ./my-original-puzzle --trusted-local-operator
godot --headless --path ./my-original-puzzle/godot --import
godot --headless --path ./my-original-puzzle/godot -- --verify-advanced
godot --path ./my-original-puzzle/godot
```

The local Game Studio additionally offers an explicit **Download playable
Godot 4 puzzle project** action for an active, fully replay-verified puzzle
session. Its localhost-only endpoint validates the session and settings anew
before returning a deterministic, content-addressed ZIP containing precisely
the fixed exporter-owned source tree. It does not automatically commit,
execute Godot, publish, fetch assets or certify native hardware. Non-puzzle
genres deliberately receive an unsupported-native-adapter error.

The Linux parity gate now exports and executes a genuine Linux desktop
binary. The Windows lane also exports a Windows `.exe` and runs its
console-capable companion against the independently verified Python puzzle
state. Native executable success must be confirmed by an exact-head run, not
just inferred from the presence of the workflow definition.

The exact-head `game-builder-advanced-godot-native.yml` workflow builds
five separate original puzzle modes on Linux and Windows, invokes their
Godot source runtimes, compares actual native results to Python, and also
builds and executes an exported Linux desktop binary. Claims of native
verification must reference successful GitHub workflow runs; a generated
project alone is never proof it has executed.

Original content is authored without external game code or third-party
copyrighted assets. Rights clearance and distribution certification remain
independent human-governed release stages.

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


## Eleventh original game — Colony Simulator (12 October 2026)

This adds a real reference game and a separately authored Godot 4 game, not
another settings-only editor. Catalog coverage increases from **10 to 11 of 43
families with executable advanced gameplay (25.6%)**. **32 families remain
authoring-only**. Native Colony is implemented but is an *unverified candidate*
until exact-head Linux and Windows native/desktop-binary workflows succeed.
The previously verified ten natives retain their separate evidence.

### Advanced authored agency

Colony provides **15 bounded real game controls**: founding settlers, labor
capacity, needs decay, relationship bonuses, adaptive/scheduled/off threats,
starting supplies, credits, worker productivity, water yield, raid frequency,
disease pressure, frugal/balanced/abundant food demand, disabled/rare/frequent
disasters, endless or victory lifecycle, and controlled migration. These
controls affect simulation, not merely the source label.

Canonical, settings-bound scene source has 2–6 distinct ordered original
districts, typed biomes, finite food, water, timber and stone reserves, starting
district, raid strength and finite caravan stores. Every identity and budget is
validated, and scene/source digests are included in replay evidence. No
external maps, scripts or licensed game assets are imported into executable
content.

Players can assign/release six professions, construct six building types,
harvest finite resources, send food-costing expeditions, trade with finite
caravans, recruit settlers within housing constraints, manage rations,
feasts, defenses, medical care and advance simulation in one/four-day steps.
Assigned labor changes genuine district stock and original inventory; daily
consumption, raids, storms and disease drive morale, health, injuries,
resource loss and potential depopulation. Medical care costs supplies.
Fortifications require real wood/stone and raid survival requires adequate
guards/watchposts. Replay transcripts reject forged supplies, population,
dates, achievements, altered action chains and changed authored geography.

The self-sufficient milestone requires a functional farm/well and sustainable
stores; the tougher thriving-outpost milestone requires morale, clinic,
watchpost and defended raids. Default gameplay remains open-ended *after*
milestones. An optional campaign-ending policy can terminate on success.
Unsolvable resource situations are valid game outcomes and do not confer
fabricated victory.

### Independent native game, Studio and qualification

The Python gameplay source lives in advanced_colony_runtime.py. The
separately implemented Godot game in advanced_colony_godot.py executes its
own worker/economy/crisis rules, renders district vitality and supports
keyboard/gamepad orders. Its --verify-colony mode replays all reviewed
commands and compares every gameplay state field, including nested district
stocks, workers, structures, injuries, events and end conditions. It does
not replay Python-rendered frames.

The offline original Godot ZIP contains game.json, proof.json, original
project source, release SHA-256 manifest and Linux/Windows export presets.
The trusted-operator CLI and token-gated local Game Studio can export a
source-bound project. Studio canvas renders finite district stocks, worker
assignments, needs and milestones. No implicit project writes or publication
permissions are granted.

Dedicated game-builder-advanced-colony-native.yml exercises eight distinct
original colony scenarios on Ubuntu 24.04 and Windows 2022, checking real
Godot replay and the exported desktop executable. The broader advanced
gameplay regression workflow validates exact-head Python gameplay,
source/scene custody and adversarial receipts on both operating systems.
The workflow *definition* is not evidence of successful execution.
Native hardware/console certification, vendor SDK authorization, independent
production playtesting, full app completion and rights clearance remain
outside these proof claims.

Operator examples (create your own JSON actions and reviewed receipt):

    python -m skeleton.ai.game_builder.system_editor_cli scene-template --editor colony --seed 5
    python -m skeleton.ai.game_builder.system_editor_cli play --editor colony --seed 5 --actions authored-colony-commands.json
    python -m skeleton.ai.game_builder.system_editor_cli godot-export --session reviewed-colony-session.json --output /tmp/new-colony --trusted-local-operator


## Twelfth original advanced family — City & Infrastructure (12 October 2026)

The typed City & Infrastructure editor now has a real original executable
Python city simulation, not a zoning form masquerading as gameplay.
**12/43 (27.9%)** now have reference gameplay; **31/43** remain authoring-only.
This twelfth family is **reference-only** pending an independent native
implementation and hardware validation. The earlier tenth Native Factory
is historically verified; native Colony is still awaiting its new CI parity
gates. We do not equate reference coverage with native certification.

### Fifteen decision-bearing advanced controls

The five existing urban editor settings (regional citizen demand, maximum
zoned sites, utility-node count, traffic simulation, planned/mixed/market
economics) now combine with municipal opening budget, housing density,
road capacity, power output, waterworks output, industrial emissions,
disaster interval/on-off switch, development policy (transport/industrial/
ecology), and endless/campaign ending mode. These settings influence actual
game transitions and are protected by strict bounded typed source schemas.

### Real spatial city game

- A **4×4 authored municipal map** with original biome/terrain tiles,
  unique transport hub, finite aquifer, bounded forestry and quarry
  reserves, flooding risk and distinct regional demand.
- Every road/bridge is an actual connected-graph asset. A player cannot
  zone distant isolated land or construct a service plant that does not
  join the real street network. Bridges require actual water terrain and
  priced materials.
- Eleven construction types: roads, river crossings, housing, business,
  industry, parks, power, waterworks, firehouses, clinics, schools.
  Development, upgrades, demolition/salvage and exploration harvest
  actually mutate the city and cost credits/wood/stone.
- Resident growth is constrained by usable, road-connected housing,
  employment, functional power, usable finite water and regional demand.
  City utilities cannot serve an unreachable zone. Waterworks gradually
  draw down the **authored finite aquifer**; city growth will eventually
  fail if the municipality cannot secure more sustainable supplies.
- Traffic congestion depends on resident and employment demand and
  connected roadway capacity; transit policy reduces pressure. Industry
  introduces real pollution; parks, environmental policy and public
  services change resident satisfaction.
- Tax modes, urban policy, bond debt, interest/maintenance, budget,
  paid supply imports, flood losses and bankruptcy create meaningful
  alternatives and expensive consequences. No arbitrary client state
  or free-money console calls grant unearned success.
- Functional-city and prosperous-city achievements are based on
  actual power/water, road access, population, employment, service
  investment, budget and morale. Default cities remain playable
  after achievements. Only explicitly authored campaign policy
  ends after the prosperity objective.

The visual local Game Studio draws the live 4×4 zoning map, transit,
utilities, finances, population, pollution and milestone telemetry, and
adds a **parcel-addressed command composer** instead of hundreds of
unusable action buttons. The separate original terrain authoring canvas
supports painting geological types, relocating the road hub and editing
finite source supplies and flooding; source edits are unsigned and
cannot become gameplay until revalidated through the human review chain.

The new advanced_city_runtime.py and tests/test_game_builder_advanced_city.py
cover deterministic command replay, independent receipt re-creation, save
and resume, finite resource exhaustion, road connectivity, backed debt,
scene-source checksum custody, city assembly, original CLI and visual
map authoring. Existing broad Game Builder Advanced System Engines
CI runs these regressions on Linux and Windows.

**Proof truth:** this is a bounded original advanced urban gameplay
reference, not an independently executed Godot city engine or commercial
municipal simulation. Console/hardware targets, depth of city types,
ongoing hydrology and climate adaptation, sophisticated 3D traffic,
production art, third-party rights and retail release remain unfinished.


## Thirteenth original advanced family — Stealth & Detection (12 October 2026)

The Action-family Stealth & Detection editor has been raised from an
authoring-only settings form to an original playable, deterministic offline
infiltration game. This is the thirteenth of 43 editors with executable
advanced reference gameplay: **13/43 = 30.2%**. The other 30 are currently
authoring-only. Stealth is not independently native-certified.

### Original 10×8 authored infiltration facility

Walls, concealment, crawl-only vents, locked doors, physical guard patrol
routes, active security cameras, recoverable keycards, finite intelligence
caches, archive, security terminal, entry and extraction are source-addressed
and protected by strict typed geometry and full-document checksums.
Validation enforces bounds, no blocked critical objectives, mission-specific
finite targets, terrain and extraction reachability and a game-relevant
bounded original playfield.

Patrols actually navigate the facility with deterministic shortest-path
routes, directed 90-degree viewing cones, integer ray occlusion through
walls and closed doors, directional noise investigations, suspicion decay,
contact damage and escalation to actual lockdown. Walking, sprinting,
crouching, shadow/cover, darkness, smoke and verified disguises change
surveillance effectiveness. Independent cameras, physical sabotage and
an increasingly dangerous alert level constrain play.

For high-staff facilities, the bounded 80-cell reference map uses a
controlled active force (maximum 20) and an actual finite guard reserve,
deployed on alarm at authored entry coordinates. This never pretends
250 simultaneous NPCs fit on an 80-cell map; additional configured
personnel influence security escalation and bounded reserve waves.

### Player action economy and mission choice

The player may walk, sprint using recoverable stamina, crouch through
vents, hide in actual cover, deploy finite decoys/smoke/EMP, stun close
guards, acquire their uniforms, physically collect keycards, open secure
doors, hack terminals, disable live cameras, collect intel, recover
health using finite medkits and physically extract. Out-of-range,
unsupported or fabricated commands fail closed.

Three genuinely different objectives are playable: (1) archive heist
requires a legitimate terminal hack or keycard unlock; (2) sabotage
requires a genuinely disabled camera and terminal hack; (3) intelligence
requires recovery of the required number of original finite caches.
All three require reaching the mission exit, not merely clicking "win".
Capture and alarm lockdown can end the mission unsuccessfully.

**34 gameplay-affecting typed design controls** cover guard budgets,
perception, visibility/noise, medical resources, stamina, gadgets, hearing,
alarm/risk response, field equipment, reinforcement cadence, mission
design and optional lockdown. No general-purpose script or free reward
is accepted through scene or action contracts.

### Graphical authoring, replay and assurance

The local Studio has a live, color-coded ten-by-eight mission map and
detailed HUD of health, stamina, guard/camera activity, alarm, equipment,
archive, intel and score. A registered action selector and directional
keyboard controls allow turn-based player interaction without teleporting.
The supervised scene painter lets authors paint walls/cover/vents/doors,
cameras, intel/keycards, patrol circuits, terminals and exit/spawn. Draft
scene mutations remain unsigned until backend validation, exact source
hash recalculation and explicit local review/approval.

The Python engine produces deterministic independently re-created replay
receipts, tamper-resistant saves, continuation and original scene digests.
Hybrid game assembly now includes the real stealth smoke path and authored
mission evidence. The dedicated cross-platform regression suite covers
all three wins, illegal moves, forged rewards, finite inventory, physical
security, guards, source custody and Studio rendering.

**Honest boundary:** there is no independently verified Godot native
stealth engine, release binary, audiovisual campaign, console publishing
license or hardware certification for this thirteenth family yet. The
City Builder is likewise reference-only. Both need independent native
implementation, test parity and genuine export assurance.


## Fourteenth original advanced family — Interconnected Exploration (12 October 2026)

The World-family Interconnected Exploration editor (metroidvania) now
implements a real **persistent, original interconnected adventure**. This
is reference runtime coverage for **14/43 = 32.6%** of the existing family
catalog; **29/43 remain authoring-only**. Reference coverage is not
independent Godot, console or release verification.

### Persistent authored worlds, progression and side routes

The default setting authors 24 original world regions (bounded runtime
range 2..24), with independently changeable biome, finite enemy health,
environmental hazards, supply caches, optional secrets, collectible traversal
power, fast-travel shrine, original guardian chamber and undirected passage
graph. A strict authored source validator rejects unknown fields, noninteger
quantities, duplicate rooms/portals/ability rewards, closed progression
cycles, duplicated or fabricated powers, disconnected guardian routes and
unreachable regions. Gated routes cannot demand abilities that cannot be
earned earlier; a static progression fixed-point must reach every chamber.

Movement powers include original dash, grapple, phase, swim and resonance
archetypes. An ability must be acquired from an actually visited, cleared
room. World locks use those earned powers. For a user-configured world,
sequence breaks are optional and strictly limited to authored breakable
locked routes. Each unorthodox crossing consumes real stamina and changes
persistent progression evidence. Visiting and revisiting rooms preserves
clearance, enemy injuries, cache depletion, activated fast-travel shrines,
acquired powers, secret discoveries and equipment gains. Travel across
nonadjacent regions is only permitted between visited, activated shrines
with a real stamina charge.

### Combat, economy, defeat and indefinite play

The player starts with finite health, stamina, healing tonics, camp
provisions and crafting shards. Ordinary and heavy strikes actually reduce
authored enemies, with counterattacks, armor, dodge, stamina, guard and
focused strikes. Room hazards respond to authored biomes and certain
acquired powers. Defeated foes grant finite material rewards, never
repeatable on revisits. Original hidden caches/secrets can be recovered
exactly once; forging consumes materials and increases effective attacks;
camping consumes provisions and restores bounded resources in safe shrines.
There is an actual high-health guardian with attacks, defensive factors,
defeat and a persistent milestone. Campaign settings stop at victory,
whereas the default endless world permits nonterminal revisiting and
continued exploration after defeating the guardian.

The engine exposes **40 gameplay-affecting typed editor fields**, growing
from the prior five: the existing number of regions, gate budgets,
collectible abilities, fast travel and sequence-breaking options combine
with enemy health/power/variance, authored hazard effects, survivability,
stamina economy, finite healing/loot, attack and guard strength, concentrated
strikes, heavy attacks, upgrades, rare secrets, boss stats, map density,
camping, traversal cost and endgame policy.

### Studio, source review and replay guarantees

The local operator Studio renders a live 24-room network with sealed
or open routes, visited/revisited chambers, available power relics,
current enemy and boss damage, finite supplies, collectible progress and
achievement state. Instead of flooding the UI with dozens of independent
buttons, a region-targeted action composer selects travel, legal sequence
breaking, activated fast travel, combat, heal, explore, shrine, crafting and
resource actions. The separate supervised original world authoring map
allows painting each region's biome, foe HP, hazards, cache, powers,
shrine/secret flags, entry/finale and annotated passage requirements.
Source changes remain untrusted until strict backend validation and
explicit approved file review; no grid click authorizes unearned gameplay.

The engine supports independently recomputed action-transcript receipts,
portable verified save/continuation, forged-state detection, typed
content-addressed authored scenes and cross-editor hybrid assembly
evidence. Its dedicated adversarial tests cover complete original
campaign and postgame, gate progression, deliberate sequence breaks,
full-room topology, finite loot, boss combat, replay forgery, auto-save,
impossible geometry and genuine authored-source custody.

**Delivery boundary:** World runtime currently caps a configured map at
24 regions, with no production streaming/open-world scale and no
independently authored/native-executed Godot metroidvania engine. It is an
original game-reference implementation, not a publication certificate.


### AI-assisted interconnected-world progression planner

A further original AI-facing capability is now implemented in
advanced_world_planner.py. It is an explicitly bounded offline
shortest-action search across real authored bidirectional passages.
State includes current region, persistent visited-room bitset, and
collected traversal-ability bitset. Portal access is denied until the
corresponding movement relic is actually reachable; every previously
unvisited room carries the action costs of clearing its finite enemies
and claiming its earned original power. The planner finds a feasible
guardian route without relying on the optional sequence-break mechanic
to conceal impossible map design.

The resulting itinerary consists only of commands the real gameplay
engine accepts: travel to an actual connected region, damage actual
enemies, claim earned abilities and defeat the original guardian.
The itinerary is independently re-executed in an explicitly
damage-disabled *diagnostic mode*, including authored enemy and boss
HP and unchanged geometry. The source and configuration identities
are preserved as hashes. The route cannot write or auto-approve
original user files; live challenge survivability, native execution,
platform-specific behavior and publication all remain unverified.

The planner exposes bounded node and action limits, explicit
no-solution/unproven statuses, deterministic hashes and supervised
local operations through the Studio (AI: rehearse world ability
progression) and offline CLI (plan-original-world). Adversarial
regressions cover full eight- and 24-region route planning, source
digest falsification, impossible budgets, game transcript replay,
and source mutation invariants.

Original reference-only City, Stealth and Interconnected World editor
sessions deliberately disable their Godot export UI until a real
separately implemented native engine is ready. The native source
support of previously implemented families remains intact.


## Fifteenth original advanced family — Open-ended Sandbox (12 October 2026)

The World-family Open-ended Sandbox editor now implements a **genuinely
executable offline creative/survival reference game** instead of only
configuration settings. This raises the forty-three-family catalog to
**15/43 = 34.9% reference-playable** and leaves **28/43 authoring-only**.
It does NOT count as native Godot or console execution.

### Persistent streamed world, not arbitrary billion-cell allocation

A world contains between 1 and 4096 deterministic logical regions. The
original simulation materializes a bounded **8×8 tile chunk per actually
visited region**, rather than allocating all 262,144 potential tiles at
startup. Terrain materialization is derived from seed and region identity;
previously entered regions retain their *actual separately mutated
64-cell maps*, including depleted stocks, cultivated crops, construction,
wildlife, pollution, aquifer water and fire. Returning to a region restores
its exact persistent state, never a fresh map with free materials.
Every local action requires physically adjacent tiles, and open water
requires a real bridge to cross.

The signed initial authored scene has an exact 64-cell terrain map,
safe entry, prescribed local fauna and settler spawns, credit reserve,
weather and a safe original region name. Each cell individually contains
its unique canonical ID, biome, building and upgrade level, finite
wood/stone/clay/ore/forage/fish/water quantities, soils, crops, moisture,
wildlife/taming status, active fire and pollution. Validation checks
integer bounds, illegal land usage, finite stock identity, wildlife counts,
crop/soil coherence, authentic settler spawn locations and a safe player
entry. Every source-drafted alteration invalidates the prior SHA-256
content receipt until exact backend validation and human file review.

### Physical building, crafting and ecological feedback

- **Six original terrain families:** grassland, forest, ridge, sand,
  wetland and lake. Materials cannot be extracted from an unconnected
  tile or unsuitable deposit even under the unlimited supply policy.
  Finite resources physically deplete; renewable forests, water and fish
  regenerate only under the authored renewable policy and bounded
  weather/ecology settings. Unlimited supply is a separate explicit rule.
- **Eleven construction types** operate on real locations: housing
  supplies living capacity; paths reduce physical movement cost; bridges
  make water crossable; farms accelerate crop growth; wells withdraw
  *finite real adjoining aquifer* water for the community; workshops and
  kilns enable appropriate material conversions; fences block wildfire;
  beacons allow energy-funded region travel; generators consume real
  finite fuel and generate energy/emissions; storehouses increase the
  allowed physical inventory budget.
- Crafting has genuine resource bills and corresponding machines:
  milling timber into planks, firing clay to bricks, forging tools from
  ore and planks, producing fuel and processing finite food. Survival
  construction costs real wood, stone and planks plus a bounded municipal
  fee; creative-mode building and authorized terraforming are distinct
  explicit options. A creative user can design freely, but cannot forge
  arbitrary API actions, rewrite player-inhabited tiles or use game state
  to certify a native executable.
- Farming requires real prepared soil, finite seed, soil moisture or
  rain, elapsed growth ticks and a harvestable crop. Irrigation consumes
  carried water. Harvesting awards finite food and recovered seed. The
  non-creative player must manage energy, hunger, thirst, exposure, food
  and water; creative worlds default to nonlethal design work unless
  the author explicitly enables creative hazards.
- Ecological evolution includes deterministic climate cycling, seasons,
  bounded forest and aquifer replenishment, finite fish stocks,
  wildlife movement into viable adjacent habitat, renewable wildlife
  population growth under a cap, localized ignition/fire spread, actual
  wood destruction, pollution and paid extinguishing. Burning wildlife
  sites, crop fields or populated construction cannot be silently
  overwritten by terrain tools.

### Real working settlements and nonterminal player worlds

Settlers have persistent ID, **home region**, map location, job, health,
morale, accumulated skill and work count. The author can define the
initial population, recruit only into **actual local housing**, physically
co-locate for assignments, and release individual residents. Roles
include idle, farm labor, lumber production, mining, ranching,
workshop construction and guard work. Actual daily tasks consume
nearby finite trees, ore, seeds and crop yield and mutate persistent
regional inventory. Workers left in a previous chunk cannot magically
harvest the newly visited region. Communities consume real communal
food/water, and unmet needs reduce health and morale; built adjoining
wells can replenish water by depleting a real map source.

Original game modes differ: an open-ended creative world defaults to
**perpetual play, no mandatory boss or scripted win**, whereas the
explicit author-disabled-perpetual policy may end after a physically
qualified housing/population settlement milestone. Survival and
creative modes are separate editorial choices, including independent
resource finite/renewable/unlimited policies.

The original editor expands from five to **76 typed gameplay-affecting
controls** covering world size, game duration, resource policy,
creative/survival, physical movement and labor energy, available NPCs,
regional job radius, ecological regeneration, finite resources,
animal behavior, weather, wildfire, farming, hunger/exposure,
transportation, generator output/fuel, crafting bills, trading prices,
storage capacity, town milestones and optional terraforming.

### Game Studio, replay and validation

The local Studio renders the actual visited region's eight-by-eight
terrain, structures, crops, animals, fire, player location and health,
energy, food/water, mined and crafted supplies, seasons, community,
power, credits and achievements. An accessible tile picker replaces
thousands of unmanageable resource/building buttons with **selected-cell
actions** plus independent global operations. Clicking the canvas
chooses the cell, but never teleports the player or bypasses proximity.
A separate **30-operation local authored-scene painter** edits
original biomes, water/ore/wood/fish/forage, animals and taming,
crop/soil, buildings, settlements, player spawn, starting credits,
fire/pollution and climate, all under typed scene review.

New source: advanced_sandbox_runtime.py. Dedicated regression:
tests/test_game_builder_advanced_sandbox.py. Verification checks
cross-platform deterministic sessions, legitimate ecological
simulation, typed scene-source identity, finite material budgets,
world region revisit permanence, worker locality, legal movement,
market/credit anti-forgery, actual agriculture/wells/workshops,
optional nonterminal/campaign outcomes, portable save and replay
tampering, offline CLI, supervised graphical authoring and genuine
source-bound hybrid game assembly.

**Delivery boundaries:** this is a real but bounded original Python
simulation and Studio frontend, not a complete 3D voxel universe,
MMO, every wildlife species, a commercial crafting sandbox, a native
Godot implementation, a verified physical console binary or
store-ready publisher asset. Each future engine, content, platform,
frame-time and asset claim requires separate independent evidence.
Source projects are built only from original material with the
existing human-reviewed, fail-closed offline custody workflow.


### Witness-driven events, quests and non-inflationary local stories

In the same standalone sandbox, a separate original system
(advanced_sandbox_story.py) now produces a **causal narrative evidence
chain** from real witnessed actions, rather than an LLM inventing
completed quests, NPC experiences or grants. This is wired directly
to successful original gameplay transitions and the physical region.

Each live settler has a geographic region, actual position and health,
so a witness report is possible only for a current-region worker that
physically saw a nearby act within the typed sight radius, or heard
an acoustically recognizable event within the independently authored
hearing range. Storms reduce direct visual reach. Logged evidence
records the source action, world region, cell, day/turn, witness IDs,
perception mode, distances, source category, exact immutable digest,
and the preceding observation's digest. A bounded live ledger may
compact old messages while retaining the cryptographic chain head and
quest-specific originating evidence digest.

Witness observations open five distinct finite original quests:

- **Forest restoration:** a worker observes real local logging; the
  damaged/depleted habitat must be actually replanted using legitimate
  seed and water. New saplings survive seasons, can burn in real fires
  and mature into finite real source wood. No duplicated historical
  restoration reward is allowed for the same site.
- **Wildlife stewardship:** a witness observes actual wildlife hunting;
  live animals must genuinely be domesticated in the same region.
- **Fire safety:** nearby settlers observe/ hear a real ignition,
  and completion requires an actual corresponding fire-extinguishing
  operation using paid carried water.
- **Civic reconstruction:** a settler witnesses real demolition and
  asks the player to rebuild on that exact location. The rebuilt
  structure must exist in the authoritative map before payment.
- **Community relief:** real local settler hunger/dehydration produces
  a direct self-reported observation and a need-based request. The
  player must transfer *actual carried supplies* to community stores,
  restoring their configured real food/water thresholds.

Quests are content-identified by region, site and objective type;
completed historical requests do not regenerate merely because a
player repeats damage and repair. Active quest count, visible
observation count, sight/hearing radius, seeded grant reserve, finite
quest reward, seed and sapling growth days, mature forest yield,
community relief minimums and donated supply amounts are governed
by **eleven additional typed editorial axes**, for 76 total.

Money is not minted by completing or repeating story commands:
the civic grant fund is bounded by the unallocated original build
budget at world creation. Each successful quest deducts its payment
from this physical remaining reserve, and only then transfers that
amount into credits. In particular, creative-mode supply overrides
do not make donated supplies materialize: donations always deduct
the real carried items.

The Studio world HUD now shows the live NPC witness ledger count and
open quests; the authoring palette includes original sapling age
states and the replay receipts expose the entire bounded NPC event
and quest state. Dedicated adversarial tests cover unseen and
heard incidents, forest recovery over time, limited grants and
duplicate-event suppression, local civic demolition/reconstruction,
relief deliveries, historical source custody, observable witness IDs
and chain-integrity tamper resistance.

**Scope caveat:** this implements five concrete original, spatially
caused story templates. It does not yet claim unrestricted human-level
NPC personality, thousands of moral/social behaviors, sophisticated
acoustical ray tracing, learned agent policy, authored voice acting,
full quest dialogue production or cross-game canonical memory.
Those are independent extensions and verification obligations.


## Sixteenth original advanced family — Roguelike Runs (12 October 2026)

The World-family Roguelike Runs editor is now a genuinely executable
deterministic offline reference game, not a form with parameters.
**16/43 = 37.2%** of the catalog have originally authored playable
reference runtimes; **27/43 remain authoring-only**. No native Godot
roguelike or commercial binary certification is implied.

### Procedural dungeons, real combat and bounded encounter density

This original implementation independently generates successive compact
6×6 tactical floors from the authored seed, depth, configured topology,
enemy budget, trap density, finite treasure and changing environmental
ambience. The author may change the *first floor's* exact wall, obstacle,
entry/exit, security, merchant, shrine, treasure, trap and enemy-source
placement under the normal content-addressed scene review protocol.
Subsequent floors are procedurally and deterministically constructed
and keep the same procedural seed lineage.

Physical walking and stamina-expensive two-cell dashes must traverse
real adjacent clear tiles; walls, active enemies and map edges block
unauthorized movement. Actual floor enemies have original IDs, HP,
armor, attacks, ranged tactics, bounded shortest-path pursuit, poison,
stun, hit-point depletion and one-time loot awards. A player can make
directional melee strikes, spend finite arrows for real line-of-sight
shots, use ranged mana-powered magic with finite poison/stun effects,
block an actual attack, rest, consume food/potions and earn experience
from genuinely defeated enemies. Enemies respond autonomously within
configurable local threat ranges, and no arbitrary state-editing attack
or fabricated completion command is registered.

Original game choices include finding traps and spending energy
to disarm them, opening spatially adjacent one-use finite treasure
chests, seeking shrine blessings, purchasing consumables or permanent
gear upgrades from a physically reached merchant, and investing earned
relics for one of two different original run-progression benefits.
Procedural chest loot responds to the bounded original item-pool axis.
A player may kill an original elite for its one-time physical key or
consume a finite lockpick at the correct physical exit. The last floor
requires an actual defeated guardian as well, even when the door has
already been unlocked. Campaign success demands reaching the final
exit in the live persistent state, not simply issuing a win command.

A high encounter budget of up to 60 does not create 60 overlapping
entities in the thirty-six-cell room. A bounded live roster and
**finite physical reserve spawns** represent overstrength dungeons.
Reserve creatures materialize only at actual unoccupied authorized
tactical locations, preserving finite enemy accounting, rather than
being a free or invented crowd simulation.

### Permadeath, progression and meaningful rewards

The typed editor can enforce permadeath: a defeated player produces
a terminal and independently re-created lost-run receipt. A separately
authored no-permadeath mode may resurrect using actual previously
earned relics, returning to the floor entry and surrendering some
finite funds. This remains a paid finite choice, not a cheat.
Earned XP levels health and attack; enemies/chests/shrines provide
nonrepeatable rewards; meta progression can be disabled, configured
as practical unlock rewards, or invested into real incremental upgrades
during a run. The run transcript records all resource changes, enemy
deaths, stair transitions and the actual final guardian milestone.

The editor now offers **77 strongly typed gameplay-affecting controls**
(including the original five), including level count, encounter density,
item pool, permadeath, meta policy, hero health/mana/stamina, melee/ranged
abilities, enemy patrol and aggression, enemy HP, armor, damage scaling,
guardian stats, room wall/trap/chest budgets, finite money/loot,
potions, EXP pacing, shrine enchantments, merchant prices, player
equipment, lockpicks, poison, stun, food and optional revival cost.

### Studio and integrity

The original Studio displays the actual current floor's signed tiles,
traps, shops, enemies, finite chests, guardian, player and staircase.
The live HUD shows health, mana, stamina, armor, gold, relics,
keys, lockpicks, treasure and finite encounter reserves. The accessible
action composer and arrow/Shift+arrow shortcuts use registered actions,
not a free teleport. The separate signed source painter supports
19 named room-authoring operations for geometry, traps, treasure,
spawn, stair/merchant/shrine positions, original enemy placement
and stats, guardian assignment, visual theme and finite reserves.
Changing source does not grant approval or create a new signed digest.

A dedicated replay/scene/adversarial suite validates complete original
multi-floor victory, actual directional strikes, physical key or
lockpick exits, one-use chests, earned original loot, merchant proximity,
paid revival versus permadeath, distinct relic economics,
finite reserve waves, authentic first-floor scene geometry,
save/continuation, forged result detection, offline CLI and reviewed
cross-family hybrid assembly. It is included in the Linux and Windows
advanced-reference CI gate alongside previous editor families.

**Important limitations:** The ordinary interactive reference
session is still bounded to 128 player actions. A separate checkpointed
long-run interface now exists and needs independent validation; this
is not a reason to raise or disable the shared limit. No native Godot
roguelike is implemented or hardware-published here, and this
compact original floor generator does not claim fully featured
commercial-level content generation or a modern multiplayer dungeon.


### Original long-running campaigns and independent checkpoints

The separate advanced_roguelike_longrun.py supports up to
**8,192 actual dungeon commands** with configurable 8–128 command
checkpoint intervals. Each checkpoint includes the original genesis
or prior digest, action-window digest, deterministic event/state
digest, floor, terminal state and content-addressed chain head. A
complete long-run receipt includes the original signed scene, editor
settings identity, actions, authentic final state and complete ordered
checkpoint sequence. An unfinished original run can be continued.

Every continuation first **rebuilds the prior state by replaying
the complete original action history** from seed, authored geometry
and settings. Client-supplied stored HP, cleared guardian, free
currency or edited checkpoints are never accepted as authoritative.
This is a fully recomputed history, not a fast trust-the-snapshot
shortcut. The shared 128-action interactive reference limit remains
unchanged for every other original editor family.

The offline entry points are roguelike-marathon,
roguelike-marathon-verify and roguelike-marathon-continue.
The token/CSRF-protected local Studio endpoint
/api/roguelike-marathon provides independently reexecuted long-run
play behind the existing local source-approval boundary. An original
dungeon Studio panel accepts JSON action batches, validates
continuation against the previous full source record, and shows
current floor, turns, checkpoint count, head digest, victory and
honest native certification status.

Cross-platform tests include **20-floor and 200-floor end-to-end
victory with actual combat and actual final guardian**, edited
source and checkpoint rejection, swapped configuration rejection,
illegal commands, action budget overflow, continuation after
terminal outcome, and offline CLI proof. This capability is
finite: a total 8,192 commands, never a claim of continuous
background work, an indefinitely persistent server process or
hardware-level native execution. Faster checkpoint promotion
requires a separate independent trust and performance review.


## Seventeenth advanced reference family — Real-Time Strategy (12 October 2026)

The Strategy-family Real-Time Strategy editor now implements an original
**spatial RTS reference game**, rather than merely holding an economy,
fog and command-latency form. It raises playable reference coverage to
**17/43 = 39.5%** of the original catalog, with **26/43 still
authoring-only**. This is deterministic Python gameplay and a playable
Studio client, not an independently native-certified hardware RTS.

### Original authored operational battlefield

A canonical 8×8 bounded demonstration battlefield includes signed
obstacle cells, original friendly/enemy command bases with real HP,
friendly and hostile spawns, a capturable relay, initial finite
wood/ore/energy treasuries, typed stock-limited physical deposits and
an original environmental setting. The authenticated scene validator
checks every tile is in range, rejects mismatched dimensions,
duplicated/overlapping structures/units/sources, resource spoofing,
illegal free budgets and disconnected original objectives. Dynamic
pathfinding uses deterministic shortest routes with real blocked cells,
unoccupied destination tests and incremental per-tick movement.
Orders are not a teleport, and fog-concealed enemies cannot be attacked.

The reference field keeps a maximum of sixteen simultaneously
selectable original friendly units, not a deceptive 300/5,000-unit
claim on 64 map tiles. The broader editor preserves its preexisting
max-units profile values for future native/large-map expansion, but
live local reference play explicitly caps active units at sixteen.
A high configured resource-node budget similarly cannot mint more
sources than physically fit; source count is bounded by signed
geography and a 64-cell world.

### Actionable tactical economics, battle and victory

Five differentiated units (worker, soldier, ranger, medic, siege)
have bounded HP, spatial location, different attack behavior,
equipment, experience and actual finite supply usage. Authentic
worker gather/return cycles **deplete physical wood/ore/energy
deposits, hold limited material cargo and deposit it only at a real
friendly command/outpost**. Unfunded training or absent barracks
cannot mint a new army. Five genuinely priced structures include
an outpost for logistics/supply, real barracks, attacking defense
turrets, periodic power generators and barriers. Tech upgrades
consume wood, ore and energy to change actual attacking capability,
armor protection, economy and vision.

Three authored supply policies are distinct: no army supply
restriction, population capacity, or logistics with explicit
per-tick energy expense and supply-line attrition on shortage.
The engine models independently configured hostile faction pursuit,
melee contact, damage, bounded reinforcement waves and finite base HP.
Fog of war has a true visibility/discovery mask, actual army/
building vision, finite energy-funded temporary scanning and
rejected concealed enemy targeting.

**Two distinct playable victories** exist: a player must physically
deploy and hold the relay for the required capture/hold time, with
enemy contest preventing a free victory, or physically wear down
the original hostile command building to zero HP. The player's
force may also fail from actual attrition/loss. Typed action
contracts support selection, spatial move orders, finite worker
harvest orders, attacks, scanning, structures, research,
production, repair, cargo deposit, squad posture and real
simulated time advancement.

The editor expands from five to **62 typed rule fields** in
this implementation, including finite budget and army population,
individual unit roles/HP/damage/range, hostile AI/aggro, physical
transport capacity, deposit stock, tick-time productivity,
world topology, technology cost and effectiveness, fog/vision,
supply modes, energy upkeep, opposing waves, fortress construction,
relay-victory timings and potential defensive buildouts.

### Graphical Studio, independent source/replay and assurance

The playable Studio renders original 64-cell terrain, discovered
versus current fog, original sources, allied and hostile units,
bases, relay, town economy, researched/owned force and battle
objectives. A cell-targeted tactical action composer uses the
registered commands; changing the selected friendly unit is itself
a physical authorized command. Clicking the map chooses a target,
not a magical unit or resource. A separate original map painter
supports terrain block toggles, physical deposit identity/stock,
base/relay moves, troop spawns, environment and initial treasuries,
and keeps each draft **unsigned until strict revalidation and
exact-file approval**.

Replay receipts cryptographically bind input actions and original
authored source to every state transition. The dedicated Windows
and Ubuntu regression suite checks actual spatial relay victory,
enemy command combat victory, no teleporting, finite labor/material
delivery, supply policies, hostile pursuit, visibility,
construction/research charges, signed-map anti-spoofing, portable
save/continuation, original scene painting and hybrid game assembly.

**Scope boundary:** this is an advanced original reference on
a deliberately bounded tactical grid, not a production 60-Hz
multi-thousand-unit engine, GPU fog-of-war implementation,
networked RTS, autonomous learning-based opponents or store-ready
native release. Cross-platform reference CI must pass before
reference maturity is certified; native engine and hardware
porting remain separate unfinished work.


## Eighteenth original advanced family — Rhythm & Timing (12 October 2026)

The Creative-family Rhythm & Timing editor has been promoted from
settings-only to an **original deterministic timing game**, with
an authoritative game clock, timed score judgements, an authored
chart and independent on-demand original synthesized soundtrack.
This raises original reference gameplay coverage to **18/43
(41.9%)**; **25/43 remain authoring-only**. Reference Python
gameplay is not a native console-ready audiovisual engine.

### Source-bound timing and game semantics

Each chart is an original authored sequence of up to 256 timed
events, with a 3–6 lane original note highway, note identities,
timestamp, meter, accent, chord partner and held duration.
Exact scene/source validation rejects duplicate or missing IDs,
unrecognized kinds, invalid tempi, out-of-range lanes,
unsupported timing shifts, mismatched hold duration,
unknown source fields and imported sample IDs.

Real player input includes physical lane taps and flicks,
two-key chords in either authored lane order, actual pressed
and released holds, explicitly elapsed server-controlled
clock time, calibration, timing inspection and chart
completion. The player cannot forge timestamps, scores
or hit judgements by submitting them as actions.
An unpressed hold cannot be released for reward.
Scores depend on lateness, perfect/great/good timing
windows, combo, multiplier, finite health, mines
and missed notes. A qualified final rank is not granted
until the chart genuinely finishes.

The editor now provides **42 original decision-bearing fields**,
including metrical swing, BPM, beat count, original oscillator
selection, note volume, judgement/release accuracy,
held/chord/mine/slide policies, latency calibration,
accessibility assist, practice hazards, anti-mashing,
score/health economies and conditional failure mode.
Timing window ordering is checked. Swing actually moves
the note timestamps; compensation affects real
player judgement but never accepts a client clock.
Dynamic difficulty tightens timing eligibility and
practice mode relaxes terminal health failure without
making missed input score as successful.

### Offline math-generated soundtrack

A separate synthesizer renders only mathematically
derived sine, triangle and pulse oscillators or
explicit silence. It never imports old game recordings,
proprietary soundfonts or other commercial music
and does not need an external executable or internet.
The PCM output is deterministic 12-kHz mono signed
16-bit WAV in bounded 20-second sections, with
physical note onsets, envelopes, mathematically
determined amplitudes, optional two-key chords
and an exact SHA-256 waveform receipt.

The offline rhythm-audio command requires explicit
trusted local operator approval and a previously
nonexistent local output path. Signed scene/seed
mismatches and edited receipts are refused.
The authenticated loopback Studio audio endpoint
limits previews to five seconds; Studio plays
2.5-second synthesized original WAV excerpts.
Neither a preview nor its receipt automatically
approves game assets or certifies native output.

### Replay-verified full-length compositions

The shared interactive reference API retains the
128-action cap. An independent full-chart runner
supports **4,096 real registered rhythm commands**
through 16–128 command checkpoints. Each checkpoint
records original source identity, chronological
input action digest, elapsed clock, actual note
judgements, deterministic state digest and
previous-checkpoint chain identity.
Every continuation independently reexecutes
all history from the original author-reviewed
chart and configuration before accepting input.
Untrusted client score snapshots and replay
substitutions are never authoritative.

The local CLI provides rhythm-longrun,
rhythm-longrun-verify and rhythm-longrun-continue.
Studio adds full-performance command batches,
independent source reexecution, current clock,
judgement/score/accuracy telemetry, checkpoint
head and explicit no-native-certification status.

Studio shows the original lane highway and
upcoming event positions, remaining beat
progress, actual finite HP, combo, misses,
hazards, rank, key-press controls, 1–6
keyboard shortcuts, clock stepping,
standalone generated sound playback, and
an author-controlled source chart painter.
The editor can update a real beat lane,
kind, chord partner, accent, limited timing
shift or original safe title, requiring
a new valid authored source digest.

Cross-platform regression coverage includes
actual clock and hit classification,
original chords and pressed/released holds,
mines, harsh/friendly difficulty options,
signed source forgery, independently
replayed portable saves, waveform
determinism, 256-beat long-run performance,
checkpoint tampering and CLI/local
Studio supervision.

**Unfinished**: native console timing,
independent device input jitter measurement,
thousands of original polished compositions,
native sound mixer integration and released
copyright-checked audiovisual packages.
The presence of generated sample WAVs
does not make these completed.

## RTS fidelity completion — seventy-two real design controls

The seventeenth reference family has advanced
from 63 to **72 typed gameplay settings**.
Each newly included axis implements a physical
game consequence. Medics actually heal
wounded allies in local range by spending
finite energy, while requiring real funded
barracks for training. Defensive/aggressive/
hold stances actually change autonomous
fighting decisions. Defeating enemies now
awards earned bounded veterancy and
configurable damage bonuses. Siege units
gain original structure-specific damage,
not simply a new class name.
All authored resource nodes are capped
by their corresponding source resource
budgets, eliminating invalid free material
creation from a forged map.

Adversarial tests cover real energy-funded
medical repair, proximity constraints,
stance-based fire, earned veterancy,
siege damage differentiation and deposit
stock-source conservation. A full-scale
native thousands-of-units game, network
model and hardware performance validation
remain separate deliverables.


## Nineteenth original advanced family — Arena Fighting (12 October 2026)

The Action-family Fighting Game editor now includes a genuinely executable
offline original multi-round arena game, raising the distinct reference
family count from eighteen to **19/43 = 44.2%** and leaving **24/43
authoring-only families**. This is advanced deterministic Python reference
gameplay and local authoring, *not* a native or device-certified fighting
game build.

### Original three-lane combat and authentic physical objectives

The arena is a typed three-lane horizontal original stage with an 8–16 cell
width, distinct authored player and opponent spawn coordinates, environmental
hazards, bounded breakable line-of-sight cover and exact world weather/theme.
The authored scene is validated as one content-addressed source, with
bounds, unique IDs and occupied-cell checks. Neither fighter can be
placed outside the stage or in another fighter, hazard or surviving
cover object through the authorized map source. Signed source cannot
mint an extra opponent, imported game character, copyrighted asset,
impossible arena timer or arbitrary serialized win condition.

Both combatants have actual position, horizontal facing, three-lane
movement, health, stamina, meter, finite guard pool, stun, attack recovery,
airborne interval, grounded/crouch mode, actual parry, hits, whiffs,
combo, damage ledger and ringout counts. Movement increments only through
real unoccupied intermediate cells and pays its own physical stamina.
Eight differentiated original attacks are registered: jab, cross,
kick, sweep, uppercut, grapple, projectile and special. Their range,
damage, stamina cost, guard zone and original special-meter expense differ.
Unreachable attacks physically whiff rather than awarding score, damage
or a combo. Original ranged strikes are stopped by real authored cover
and visually reduced by real fog; airborne attacks avoid true ground
sweeps, while crouching avoids high non-special strikes.

High and low guards block different physical zones. Properly timed
parries consume stamina, neutralize genuine incoming strikes, and
stun the opponent, but **expire after their current frame interval**;
one permanently activated defensive shield is not allowed. Guard
pressure drains guard durability, guard break creates recovery/stun,
grapples bypass static guard at close range, and hitstun and recovery
constrain subsequent attacks. Enemy behavior depends on real distance,
stance, player action history, available stamina, active stun and
defensive versus aggressive versus adaptive authored AI policy.
Hit-confirmed combos and earned special meter provide real strategic
progression, with bounded combo limit and damage scaling.

A round ends only because a combatant actually loses health or the
authenticated round timer is reached. Knockback changes live spatial
position, and an authorized ringout can end a round only after genuine
combat pushes a fighter beyond a real edge. Multi-round victories require
the configured number of **actual round wins**, with resetting
positions, health and stamina between rounds and a persistent record
of both sides' historical results. A lost fight cannot be resurrected
by posting a fake action, edited win flag or refunded damage receipt.

### Fifty typed controls and functional Studio

The editor has been extended from five to **50 typed
gameplay-affecting design axes**. They govern grid width, best-of
rounds, per-fighter health and stamina, attack cost, fatigue/recovery,
hitstun/parry timing, airborne movement, finite guard durability,
combo limits/damage, damage and pushback, ringout policy, real stage
hazards and cover, AI style/adaptation, special/projectile meter costs,
round clocks, optional original accessibility auto-guard and replay
determinism policy. Existing timing, rollback-compatibility and
input-buffer knobs remain explicit, distinct authored values.

The Studio renders a physically separate original three-lane
match arena, player and opponent colored geometric sprites,
environmental hazards, intact cover, airborne and parry states,
real combat HP/stamina/meter/guard/stun/combo, round tallies,
ringout counts and frame time. All game-playable commands are
drawn from the original strict action registry, with a keyboard
mapping for approach/retreat, three-lane sidesteps, jab, kick,
jump and parry. A separate eight-tool original scene painter
can move fighter spawns, adjust permitted real hazards/cover,
change original weather and scene theme, then requires new
exact-source validation. Painting never mutates the operating
game through a hidden permission path.

The independent Windows/Linux regression lane tests genuine
spatial whiffs, two actual KOs for match victory, opponent combat
wins, distinct high/low blocking, parry stamina and recovery,
stamina-conserving combos, original paid projectile/special,
fog/cover interactions, ringouts, forged source/spawn rejection,
portable original save replay, Studio controls, hybrid assembly
and the offline no-native-certification CLI. Those checks need
their own exact-head passing result before a CI pass is claimed.

**Honest scope:** The original reference is a bounded turn-frame
game, not a high-frame-rate 3D/2D fighting engine with animation
cancel data, independent controller latency certification, verified
online rollback netcode, network matchmaking, a large roster,
motion-captured character animations or licensed commercial
publication. Its user-facing edits and replay contracts are
original and modular; native and device assurance remain separate
tasks.

## RTS fidelity supplement — seventy-seven real controls

The original RTS editor further advances from 72 to **77 typed
gameplay-control axes**. Actual ranged fire now checks intervening
physical wall, building and friendly-body cover using an original
grid line-of-sight test. Target designation can issue a legal
move-then-fire order, but the attack does not shoot through
opaque world geometry. Rain physically reduces safe ranged
attack reach, and desert campaigns consume additional real
logistics energy. Enemy forces are now able to attack and destroy
the actual friendly command base from authentic nearby positions,
producing a distinct real battle-loss cause. Authorized player
victory halts the opposing simulation before a contradictory
post-victory defeat can be invented. This deliberately goes
beyond labels for weather, stance or enemy behavior.

Dedicated adversarial regression cases cover obstructed
projectiles, body-blocked ranged attacks, actual rain reach,
desert resupply accounting, surviving base HP loss and an
opposing side's legitimate command-destruction victory.
The 77-control matrix is an authored tactical reference, not
a claim of verified multi-thousand-unit native RTS performance.


## Fighting family upgrade — two-peer deterministic rollback laboratory

The nineteenth original Fighting editor now has **52 typed gameplay and
rollback controls**. The separately authored
advanced_fighting_rollback.py supplies an executable original
**two-player arena frame-input simulation**, beyond the normal
one-player-versus-NPC demonstration. Both actors use the original
fighting hitbox, parry, guard, stamina, meter, recovery, movement,
stage hazards, ringout, knockout and round-victory rules. The signed
record captures each player action, alternated input priority,
actual simulation transitions, stage source identity and a
cryptographically chained sequence of frame-result receipts.

Authentic input streams must have the same frame count (up to
128), valid registered commands, exact bounded seed and matching
authored stage. The preexisting rollback_compatible switch now
explicitly authorizes or rejects actual deterministic rollback
execution. New rollout settings add a **1–30-frame correction
window** and a separate **0–32 corrected-frame budget**.
Predictions are never authoritative state. Any late actual
opponent input is accepted only within those bounds; reconciliation
replays both entire original input histories from source. Corrections
older than the budget, free-winner commands, fabricated player state,
unregistered actions, altered settings and faked source digests
fail closed.

The original CLI now supports fighting-peer-replay,
fighting-peer-verify, fighting-rollback and
fighting-rollback-verify. The supervised local Studio
server has corresponding /api/fighting-peer-replay and
/api/fighting-rollback endpoints. The graphical editor
adds an original two-peer input lab to submit blue player,
predicted opponent and actual opponent commands, reporting
corrected frames, final authoritative world digest, HP,
match outcome and independent verification rather than
presenting prediction as a final match.

The cross-platform regression includes complete original
two-peer knockouts, valid late correction convergence,
source custody, alternate frame priority, parry timing,
forged HP or win receipts, old-frame rejection,
excessive correction rejection, disabled rollback
policy, CLI parity, Studio source proof and valid
no-native/no-network flags. These are programmatic
reference tests; they need successful exact-head
CI results before being regarded as independently
validated.

This is **not yet live networked multiplayer**:
network transport, player authentication, remote
hardware input-latency measurement, NAT traversal,
anti-cheat deployment, frame-level desync tracing
and platform performance certification remain
separate future product milestones. No commercial
multiplayer release claim follows from deterministic
two-peer replay alone.


### Advanced fighting combat fidelity and prediction reversal

The same original Fighting family now exposes **55 independent
typed control axes**. Added combat rules are observable in both
one-player and authentic dual-peer reference gameplay:
combos expire after an authored number of *real elapsed fighting
simulation frames*, dashes move at most two physical unblocked
tiles while spending explicit additional finite stamina, and
feints disrupt a real opponent guard only inside configured
physical interaction range. Distant feints still cost stamina,
but no longer act as a magical map-wide posture edit.
Original arena knockback is now also resolved one tile at a
time, stopping on real authored cover rather than tunneling
through intermediate stage geometry. A disabled original
cover/hazard budget generates zero stage objects rather
than fabricating an object contrary to the editor settings.
Starting meter may not exceed its typed capacity.

The independent rollback runner applies the same dash and
feint physics to the two real participant streams, retains
actual clock-frame changes for explicitly elapsed 60/240
frame inputs and records them in signed turn evidence.
The rollback correction engine now handles a particularly
important **premature predicted knockout**: when a speculative
opponent action ended the guessed game but a later physical
authoritative parry prevents the knockout, the predicted
record is truncated at its authentic provisional endpoint
and the complete actual game replays and continues. The
receipt explicitly labels provisional-frame truncation
rather than representing a guess as genuine success.

Regression cases cover physically blocked knockback,
genuine zero-object editor budgets, meter overcapacity,
dash stamina conservation, legal close feints, long-frame
combo expiration, two-player frame-clock parity, bounded
prediction correction and the reversal of an incorrect
provisional knockout through a legally timed parry.

As elsewhere, this new gameplay remains a **reference
implementation** pending exact-head Windows/Linux CI,
hardware/controller testing and independent native build
certification.


## Twentieth advanced reference family — NPC Quest & Event Director

The original World-family Quest & Event Director has progressed from a
five-field catalog into **62 actual typed controls** and a source-bound
Python reference game. This raises executable reference gameplay to
**20 of 43 families (46.5%)**, with 23 remaining authoring-only.
The bounded 7x7 reference world is neither a native game nor a
production-scale or console-certified NPC simulation.

### Genuine witnessed events and original geography

Every scene contains original bounded geography, walkable obstacles,
four finite original sites (settlement, bridge, grove, archive),
actual player/NPC spawns, geography-specific resources and original
climate and day phases. A real player walks adjacent cells and must
be physically present at a source to help, harm, collect or repair,
using real energy, material stock and site integrity. Strict scene
validation rejects overlap, invalid identity, inaccessible sites,
source budget violations, forged scene hashes and arbitrary
external scripts.

NPC residents have independent original professions, actual positions,
personal finite energy and supplies, gained cargo, trust, suspicion,
memory histories and eyewitness knowledge. Autonomous caretakers,
scouts, merchants and scribes perform real bounded acts at their
nearby original source sites. NPC-caused incidents can independently
initiate real quests **only when another legitimate resident sees
the act**. The actor cannot witness its own act, and NPC acts do not
grant the player a fabricated physical quest step or reputation gain.

Eyewitness eligibility requires spatial range, authenticated line
of sight with blocking terrain, physical day/night visibility,
climate (highland vs rainforest) and authored perception. Rumors
propagate only over bounded physical resident-to-resident edges,
with snapshot knowledge to prevent instant unlimited gossip chains.
They retain source event ID and the explicit rumor-only authority
label; hearsay cannot be promoted to first-hand testimony.
Direct observations and rumors have independent finite memories
and optional decay.

### Real procedural quests, branching endings and persistent worlds

Each original quest binds a physical incident, actual originating
actor, event ID, witnesses, cause type, source location, procedural
rule ID, and independently attested testimony. The player must
physically meet a trustworthy non-suspicious eyewitness, commit
a support/exploit branch, perform further source-site actions,
and return to that actual site to resolve the outcome. It cannot
auto-approve from rumor, skip site actions or rewrite a committed
choice. Alternative resolutions consume resources, change actual
landmark integrity, grant different bounded rewards and modify
NPC/public standing; incomplete events may expire. Campaign
victory may be terminal or allow ongoing play, quests and new
NPC events through the separate persistent nonterminal world option.

The original Studio now displays an actual 49-tile grid with
player, source sites, NPC positions, eyewitness and hearsay
symbols; a 12-tool source painter, site/NPC selection, real
registered world actions, recorded causal events, testimony
and active quest completion status. Edited sources require
renewed exact scene validation and digest review.

Original regression coverage on the Windows/Linux advanced
game workflow now includes eyewitness geography, daylight,
climate, believable suspicion/trust, non-omniscient rumors,
autonomous NPC-caused quests, finite resources, alternative
choices, postgame activity, signed save/continue, hybrid
assembly and forged source/state rejection.

### Evidence and release boundary

Committed tests are not passing verification: at the latest
observed branch head GitHub reports zero PR workflow jobs
or commit status checks, and PR #3642 remains draft and
nonmergeable. The reference simulation is not native
hardware proof, online multiplayer, a large-scale
AI-trained character society or console/store readiness.
