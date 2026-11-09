# Dragon Living Worlds — no mandatory victory, shifting spaces, postgame and long-lived universes

**Scope:** Original seeded game-world runtime, authenticated editor interface,
bounded interactive exploration, replayable story/choice consequences,
changeable mazes, signed continuation, durable operator-configured SQLite saves,
and lazily indexed very large compositional design spaces.

**Not claimed:** A rendered Minecraft-style voxel engine, animal/creature AI,
photorealistic terrain streaming, production-ready open-world RPG cinematics,
Nintendo-style physics, hundreds of thousands of compiled binaries,
1.8 billion independently original games, or automatic legal clearance.

## 1. Core principle — playability is independent of an ending

The old constructive maze system is valuable for a user explicitly asking for
a completable puzzle. It is **not a universal world design law**.

Dragon now treats these as independent state-machine attributes:

- **Playable:** The player currently has a legal next action.
- **Win condition defined:** An ending exists and might be reached.
- **Story ended:** At least one particular narrative outcome was experienced.
- **World ended:** The chosen lifecycle actually terminates ordinary play.
- **Postgame:** An ending was reached and the environment, settlements,
  factions, resources, routes and choices are still interactive.
- **Unending:** The world intentionally has no fixed final objective.
- **Restartable run:** A player run can end and restart while game-world
  rules and authored content remain valid.
- **Hardcore run:** A life can end through actual resource depletion.
  A new run is possible, but the previous run is not silently rescued.

A world with no ending is not classified as unsolvable or broken. It is a
legitimate, playable stateful environment. Constructive, guaranteed-solution
maze worlds remain available as a **different selectable world class**.

## 2. Actual world styles

The initial 32 authored rule profiles include:

- Creative construction and terraforming sandboxes
- Survival, persistent survival and living ecologies
- Original open-world narrative, post-story exploration and wasteland-like
  design (no proprietary game expression, brands or borrowed maps)
- Multiple realm adventures, realm hopping, island/sky/ocean/space worlds
- Mutable labyrinths, shifting dungeons, rotating towers, living castles
- Time-loop mazes, metroidvania-style exploration, roguelites and hardcore runs
- Colony/city construction, farming/life simulation, trading and transportation
- Science exploration, frontier strategy, social simulation and generational
  worlds

A rule profile is an implemented collection of abstract world actions and
conditions. A style name alone does **not** mean a full 3D renderer, vehicle
physics, quest-writer model or enemy AI is already implemented.

World lifecycle can be selected independently from genre when compatible:
unending, optional endings, postgame, multiple endings, mandatory completion,
restartable runs and real-resource permadeath.

## 3. Choices really change subsequent gameplay

The server recomputes and validates every action. A chosen route is not
merely a link in a taxonomy.

Game actions can:

- Move a player in a coordinate world with terrain and shifting doors
- Survey territory, discover actual spatial sectors and open portals
- Forage food/wood, mine ore and crystals, build shelter, craft, farm,
  terraform and research
- Trade resources, recruit allies, support rival social groups, negotiate
  or challenge hostiles
- Pay resources for conditional transport, travel across distinct realms
- Earn one of multiple optional story conclusions
- Continue playing in an altered era with persistent faction alignment,
  settlement construction, research, resources and experienced endings
- Restart a run after a death or the terminal state of a finite campaign

Factions have materially different consequences. Supporting settlement
interests improves civic reputation and may diminish wilderness allegiance.
The reverse choices matter as well. Particular endings have real conditions,
grant real benefits and leave enduring flags in the world.

The implemented outcomes are civic union, wilderness guardianship, star
exploration, knowledge preservation, merchant compact and world restoration.
Multiple conclusions can be experienced in suitable postgame worlds. No
procedural narrative is assumed automatically compelling to human players.

## 4. Mazes that change as the player moves

A dynamic corridor is no longer a static wall with a renamed sprite.

- Eight time phases determine which maze edges are physically open.
- Every real movement, wait or other action advances the phase.
- A rotating safe compass exit and a seeded topology make the local door
  network move between different configurations.
- A waiting player can allow a blocked passage to become reachable.
- Some world styles apply rotating walls across multiple world layers.
- The game can deliberately have **no final maze exit**, remaining an endless
  navigable and evolving labyrinth.

There are two independent bounded route planners:

1. **Time-expanded BFS**, searching actual movement, wait and rest transitions
   to an optional player-selected destination.
2. **Temporal A-star**, using admissible Manhattan distance with the same
   genuinely executed game mechanics.

The search includes world coordinates, mutable phase and available energy,
and then replays the entire returned action history through the canonical
original game runtime. Bounded search failure means **not proven within the
budget**, not automatically that the world is impossible to win.

The authenticated editor can examine eight actually generated door snapshots,
compare the independent solvers and play a route one move at a time.

## 5. Multiple world systems

A world may contain 1–12 generated realms. Real portal actions require
actual discovery or research and a usable portal hub. Player location,
chapter, resource history and progress persist across realm changes.

This supports a basis for authored multi-world campaigns as well as
open-ended world-hopping sandbox journeys. Worlds can also use survival,
story or transport rules simultaneously. In this implementation a portal
does not yet imply side-scrolling platformer gravity, aircraft flight or
stellar navigation physics.

The earlier certified World Atlas remains the option for campaigns whose
**every region must have a winning route**. The Living World runtime is the
choice for world systems where mandatory completion would be inappropriate.

## 6. Huge compositional address space — truthful counting

The world runtime exposes 1,600,000 indexed base addresses and ten variation
slots per base world: 16,000,000 reproducibly addressable base variants.

The compositional lattice additionally combines actual supported world-style
and lifecycle profiles. It has more than **3 billion reversible valid generator
configuration addresses**. Ten replayable route-policy slots per such design
produce more than **30 billion addressable path slots**.

Crucially, these are **addresses, not completed games**. They are not proof of:

- Distinct subjective experiences, effective uniqueness or independently
  original expressive content at every address
- 3 billion generated/saved worlds or 30 billion tested paths
- Human enjoyment, commercial publication rights or platform approvals
- Collision-free literary/story originality across the address space

Every *requested* design address is deterministically materialized as a
bounded typed original world. Its requested path can be independently
replayed and verified before displaying any claim of success. The creator
can inspect a specific large index without enumerating the full space.

Profiles are compositional, and design capacity can scale without allocating
billions of Python objects, network calls, full maps or third-party game files.

## 7. Long-duration state: signed and durable

A backend cannot simply trust a client's claim to own an endgame, a million
resources or a faction victory. The implementation has two layers:

**Renewable signed checkpoint**

- The service requires the operator's unique environment secret:
  SKL_DRAGON_LIVING_WORLD_SIGNING_KEY
- The secret must be at least 32 bytes and is never embedded in the code.
- A token has canonical versioned state, exact world identity, original
  source fingerprint, authenticated owner scope, game-history digest and
  a seven-day expiry.
- HMAC verification precedes interpreting any submitted game state.
- Each request advances by at most 192 real actions; consecutive requests
  can continue beyond that total.
- A token can be intentionally branched like a player save point, subject
  to the user's own permissions.

**Durable SQLite account save**

- Uses the existing operator-configured SKL_DRAGON_PRACTICE_DB_PATH.
- Each account has ten bounded save slots, scoped by opaque owner identity.
- The server signs game state for integrity and checks source fingerprint,
  world ID, style, lifecycle, owner and gameplay digest before restoring.
- Expired seven-day sessions can be recreated from an intact durable save
  and resume the exact original world and story state.
- Saving over an occupied slot requires explicit replacement and the
  exact prior save digest. Stale requests fail instead of silently
  overwriting somebody's later choices.
- No anonymous viewer may create a saved game or invoke high-cost
  creator operations.

These are real durability and security controls. They do not claim
automatic backups, disaster recovery, offline cloud synchronization or
unlimited administrative retention.

## 8. Interfaces, service routes and evidence

Use the Dragon Living Worlds creator from Studio or World Forge. It offers:

- World/style/lifecycle/seed/variation authoring
- Current original biome and landmark tiles, weather and moving-door phase
- Interactive movement, resource usage, exploration, factions and endings
- Postgame continued play and several independent path strategies
- Dual changing-maze BFS/A-star destination search
- Incremental signed progression and safe rewind
- Local history export and validated restore
- Durable SQLite saving and reissued signed checkpoints
- A compositional index inspector that materializes an actual requested
  design rather than pretending all indexed alternatives were built

The authenticated API surface is under:

    /api/dragon-academy/native/production/worlds/catalog
    /api/dragon-academy/native/production/worlds/preview
    /api/dragon-academy/native/production/worlds/play
    /api/dragon-academy/native/production/worlds/alternatives
    /api/dragon-academy/native/production/worlds/route
    /api/dragon-academy/native/production/worlds/journal
    /api/dragon-academy/native/production/worlds/indexed-design
    /api/dragon-academy/native/production/worlds/maze/analyze
    /api/dragon-academy/native/production/worlds/checkpoint/advance
    /api/dragon-academy/native/production/worlds/checkpoint/inspect
    /api/dragon-academy/native/production/worlds/store
    /api/dragon-academy/native/production/worlds/restore
    /api/dragon-academy/native/production/worlds/saves

## 9. Validation gates and future native delivery

The Dragon Native ROM Build workflow now contains a dedicated living-world
lane for pure Python replay, 32 style profiles, play-without-victory, faction
outcomes, changing mazes, alternate routes, HMAC, durable DB state and
compositional indexes, plus actual evidence artifacts.

Local validation from the repository root:

    python -m compileall -q skeleton/ai/webcrawler/dragon_living_world.py skeleton/ai/webcrawler/dragon_living_world_routes.py skeleton/ai/webcrawler/dragon_living_world_checkpoint.py skeleton/ai/webcrawler/dragon_living_world_store.py skeleton/ai/webcrawler/dragon_living_maze_solvers.py skeleton/ai/webcrawler/dragon_living_world_lattice.py
    python -m pytest -q tests/test_ai_dragon_living_world.py tests/test_ai_dragon_living_world_routes.py tests/test_ai_dragon_living_world_checkpoint.py tests/test_ai_dragon_living_world_store.py tests/test_ai_dragon_living_maze_solvers.py tests/test_ai_dragon_living_world_lattice.py
    python -m pytest -q backend/tests/test_dragon_living_world_routes.py backend/tests/test_dragon_living_world_checkpoint_routes.py backend/tests/test_dragon_living_world_store_routes.py backend/tests/test_dragon_living_maze_routes.py backend/tests/test_dragon_living_world_lattice_routes.py

**Not complete:** a streaming 3D/voxel renderer, detailed AI ecology and
creature simulation, multi-console runtime compilers for each style, actual
world persistence stress under concurrent production load, subjective
difficulty certification, world compression weights and global originality
research clearance.

Game titles from other publishers can inform genre design but their maps,
source, proprietary ROM data, artworks, stories and recognizable trademark
expression must not be copied into original output. Separate human/legal
review remains required before commercial game distribution.
