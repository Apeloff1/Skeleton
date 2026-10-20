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
