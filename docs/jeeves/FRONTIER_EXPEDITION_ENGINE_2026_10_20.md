# Frontier Expedition — Actual Game Mechanics, Routing and Playthroughs

## Executable capabilities added

The game expedition engine executes deterministic progression through explicitly
connected 3D worlds built with original authored source evidence. The engine
does not call a cloud provider or physical device location, nor does it claim
that the Python simulator has been validated on Godot hardware.

Unlike a roadmap axis or descriptive editor catalog, the runtime actually
implements travel, enforces unlock and equipment prerequisites, mutates stamina,
health, story flags, collectibles, rest, interactive landmarks, victory states,
and saves/replays the exact authored choices and world state.

### Implemented interaction domains

- Layered ground, settlements, ruins, sky islands, caves, underwater regions,
  forests, ice, volcanoes and airships; coordinate-bounded source nodes.
- Author-controlled directed and bidirectional travel, including rope bridges,
  climbing, swimming, diving, gliding, updrafts, airships, portals, rail and boat.
- Quantified travel energy and elapsed time, carried-mass penalties, terrain
  traction, precipitation, skill, exposure, visibility and storm turbulence.
- Aerial navigation visibility equipment gates. No real GPS data is accessed.
- Connected, resource-constrained Dijkstra routing optimizing travel time,
  safety, energy or scenery. Abilities and quest flags can unlock later links.
- Real alternative routes by forbidding concrete links, rather than duplicating
  a cached plan. No imagined shortcuts or graph gaps.
- Seeded original sky-island world authoring with a guaranteed highland route,
  optional ruins/portals/reef/caverns, detours and scenic connections.
- On-foot interaction, limited rest sites, actual collectible/quest rewards,
  destination victories and terminal post-game action rejection.
- Source-bound, hash-linked per-action gameplay receipts and deterministic
  save-state replay with full history/graph/ability continuity checks.
- A real Forge Studio bridge: placed prefabs become traversable interactable
  landmarks bound to the original prefab content digests; candidate navigation
  is played through before portable, source-stamped engine data is emitted.

### How game projects use it

Use author_studio_expedition(StudioProject, ArchipelagoProfile) to build a typed,
playable world from an existing authored Studio project, or
compile_studio_expedition(project, profile) to produce a source-bound candidate
including multiple executed playthrough receipts, prefab bindings and portable
game/frontier/expedition.json. The portable JSON is designed for a target engine
loader, not a claim that the engine loader exists or that native code ran.

The runtime supports ExpeditionEpisode.step(ExpeditionAction(...)) for real
game-state progression, find_route() for executable goal paths, and
ExpeditionEpisode.restore() for exact saved replay. Bad source IDs, unconnected
travel, missing equipment, no stamina, unsafe coordinate data, altered game
saves, changed source and missed victory conditions fail closed.

### What remains unverified

These milestones do not constitute a finished AAA game, an independently
qualified native Godot build, a months-long stress result or automatically
completed MDM-001..MDM-100 volumes. A real Godot loader, asset rendering,
controller capture, physics authority and full first-install playthrough remain
separate integration and verification work. Explicitly simulated evidence must
not be presented as hardware or commercial production proof.


## Standalone real Godot 4 game export

The engine now emits a runnable Godot 4 project, not only JSON candidate
navigation data. emit_expedition_godot_project() creates project.godot,
a main scene, engine-executed expedition.gd, original world JSON and player
capability source, plus player instructions. The scene builds visible 3D
landmarks, route lines and a controllable camera around the authored world.
UI Up/Down chooses edges, Enter takes a valid connected route, and Escape
rests only at actual rest points. In-engine state updates health, stamina,
travel time, first-time discoveries, collectibles, unlocked quest flags and
victory or defeat. The scene uses Godot's native input and emits clearly
labeled untrusted native observation lines for independent replay.

The Forge Studio compiler includes these playable project files by default,
and a source-bound, per-file SHA-256 manifest. attach_expedition_godot_project()
permits addition to an existing game but refuses replacement of nonidentical
native files. An explicit include_godot=False choice permits simulation-only
builds without generating a native project.

Regression tests verify resource closure, seeded byte-for-byte reproducibility,
invalid or replaced source refusal, added-asset overwrite refusal, compiled
Forge integration and (when the executable exists) real Godot headless scene
startup. A test skipped because Godot is unavailable is not a passing
native playthrough claim. The compiler's native_playtest_completed flag remains
false until an independently observed native playthrough is provided.


## Candidate-native playthrough replay and independent route verification

The Godot 4 runtime now emits the exact authored world digest and traveler
profile digest alongside source identity on every emitted game action.
inspect_native_expedition_trace() checks bounded native stdout records against
an independently instantiated ExpeditionEpisode replay, including:

- Exact world, original source, project and player identities.
- Real directed graph movement, blocked route rejection and equipment gates.
- Stamina/health accounting, game-clock drift, scene landmarks and visited nodes.
- Quest flags, authored collectibles, victory state and action ordering.
- Per-action candidate receipts, duplicate record rejection and original start
  identity, including explicit incomplete-playthrough checks.
- Strict JSON parsing without duplicate fields, nonfinite data, unbounded
  vectors, absent initial spawn or forged native-authority assertions.

This adapter does not grant native process authenticity: a synthetic JSON
trace could describe a legitimate simulated session. Its report explicitly
states that the source gameplay was replay-verified while engine origin
attestation remains false. A real native run still requires its test job,
binary identity and captured process provenance to be independently checked.


## Seven implemented development milestones (2026-10-20)

The new expedition delivery is implemented in distinct source owners, all
attached to the existing Forge/Jeeves app rather than a sample-only plan.

1. Native Godot autoplay accepts a deterministic source-constrained route
   from the actual route solver. The engine navigates every connected edge,
   updates game state, prints candidate observations, and terminates with
   an explicit winning-state receipt (or exits nonzero).
2. An actual Godot 4 runner checks the binary version, runs the standalone
   project headlessly, captures the complete process log, verifies the
   terminal game result, and independently replays all emitted observations.
   Missing Godot, engine failures and incomplete gameplay are hard failures.
3. The CLI exports complete original seeded projects with SHA-256 file
   evidence and atomic no-overwrite publication, and optionally runs native
   verification. Its simulated reports never impersonate engine results.
4. Real multi-seed campaign QA executes full routes across original worlds,
   headwinds, storms, rain, turbulence, fog, and equipment variations,
   including explicitly blocked cases and objective comparison receipts.
5. SQLite save games retain every actual action with source-bound replay,
   restart-safe typed restore, optimistic concurrency, idempotent writes,
   tamper checks, and hash-linked generations.
6. Independent release assurance checks file source closure, playable goals
   via two independently reconstructed routes, QA case receipts, objective
   quality axes, source-linked content reviewers, and actual native evidence
   if provided. No model may manufacture legal clearance, reviewer authority
   or production completion merely by filling a JSON field.
7. Seven real Jeeves Studio operations bind projects from host-owned
   authority: inspect, preview, QA, release inspection, session start, state
   action and original Godot export. The preexisting registry's exact-command
   host authorization and tool grants remain mandatory. No direct unapproved
   files, providers or hardware access is granted to Jeeves.

Each host's finite batch or engine job supports project continuation through
durable game/queue receipts. Remaining work includes real multihour native
playthroughs, expanded cutscene/asset pipelines and signed legal approval;
nothing here constitutes completion of 100 roadmap bundles.
