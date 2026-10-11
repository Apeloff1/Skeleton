# Original 10× Spatial World Forge — 12,288,000 indexed configurations

**Implementation:** `skeleton/game/generation/original_world_tenfold_*.py`  
**Status:** Dedicated abstract Python reference runtime and offline game CLI. A
finished native game, procedural voxel engine, platform-certified binary,
audio-visual production, or independently authored story is **not** implied
by addressable numeric world configurations.

## Actual scope and provenance

The previous generation offered 102,400 mode-bound foundations and
1,228,800 advanced gameplay configurations. This version adds **ten
individually specified spatial architectures** with executable transit
rules and resource hazards, not ten cosmetic appearances.

| Indexed layer | Cardinality | Formula |
| --- | ---: | --- |
| Composed authored causal-law bases | 10,240 | Existing 128 new roots × 80 authored regimes, each with domain bridge |
| Gameplay structures | 10 | Platform, puzzle, tactics, survival, colony, racing, stealth, commerce, exploration, rhythm |
| **Spatial gameplay foundations** | **1,024,000** | 10,240 × 10 genres × 10 spatial architectures |
| Distinct continuation contracts | 12 | Chapters, endless, roguelite, dynasty, factions, sandbox, mystery, seasonal, rescue, campaign, civilization, branching |
| **Advanced addressable game configurations** | **12,288,000** | 1,024,000 × 12 continuation arcs |

The last line is a **nested superset**, not additive with the previous
million configurations. No additional individually hand-written root-world
premises were introduced by multiplication; the root-world premise inventory
remains **1,424**. No skin, seed, color, texture, hardware target, chronological
era or difficulty slider contributes any factor to these counts.

All configurations have exact index/ID, original root and regime,
genre ID, architecture ID, and continuation rule. Legacy
`advanced_at` and `foundation_at` numbering remains untouched.
The new index/unranking scheme is:

```text
spatial_index = ((base_index * 10) + gameplay_form_index) * 10 + architecture_index
world_index = spatial_index * 12 + progression_index

spatial_index: 0..1,023,999
world_index:   0..12,287,999
```

Both can be lazily resolved without constructing the giant index in RAM.

## Ten actual spatial simulation engines

A twenty-four-node abstract scene is used for each pilot. This is a bounded
reference topology: **not** a rendered map, volumetric world, million-region
geography, hardware-accelerated voxel system or comprehensive production
engine. Its distinct laws are:

| World architecture | Actual graph behavior | Player intervention and cost |
| --- | --- | --- |
| Civic Lattice | A six-by-four orthogonal grid | `pave` consumes mined materials, adds safe shortcuts and reduces road hazards |
| Turnback Spiral | Winding path; optional distant hinges | `splice` builds material-backed cross-map routes |
| Witnessing Labyrinth | Seed-deterministic connected spanning tree plus shifting optional edges | `anchor` spends mined materials and verified evidence to stabilize a shortcut |
| Finite Archipelago | Four disconnected islands with ring roads | `ferry` finances pier links; crossing islands consumes real stored fuel |
| Descending Strata | Four geology layers, six rooms each, narrow shafts | `brace` adds shafts and reduces deep-rock hazard |
| Sky Canopy | Vertical forest platforms with shifting wind diagonals | `tether` preserves dangerous bridges and reduces fall exposure |
| Orbital Constellation | Six orbital rings, phase-dependent docking transfers | `align` consumes propellant and material to keep windows accessible |
| Pocket Realms | Twelve outer and twelve inner chambers | `attune` consumes materials and explicit civic trust for usable portals |
| Reconfiguring City | Persistent safe circuit plus rotating phase corridors | `stabilize` permanently preserves selected emergency passages |
| Living Abyss | Ocean-floor grid with periodic tidal shortcuts | `seal` spends materials and reduces deep oxygen and pressure cost |

Navigation is validated against the **current actual graph**, not guessed
routes. Illegal, disconnected, ungated or unresourced moves are rejected.
Every accepted traversal costs finite stamina; inter-island and orbital
transfers debit fuel, deep sea and pocket travel debit oxygen, and
architecture-specific hazards cause persistent risk.

Surveying discovers only actually reachable new sites. Material extraction
uses SHA-derived *finite per-site geological capacity*; extraction from one
site persists without depleting all other sites. Resupply transfers mined
materials into the shared gameplay/civic supply inventory rather than
creating free goods; repairs and architecture interventions consume real
stocks. Local state and source-game state are combined into a complete,
deterministic, checksum-validated save envelope with chained action hashes.

The old genre mode and campaign continuation states are embedded, so an
orbital tactical world or underwater survival world can execute the earlier
genre and arc actions in the same game and persist both histories.
The shared runtime is a real playable **abstract simulation**; all ten
architectures do *not* have individually designed art assets, NPC ecosystems,
fully simulated 3D geometry, or bespoke authored campaigns.

## Command-line play and integration

```bash
python -m skeleton.game.generation.original_world_tenfold_cli --inventory

# Index the very last entries without enumerating 12m objects.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --page 12287997 --limit 3

# Build and travel a physical grid.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --base 0 --form puzzle --architecture lattice --arc endless --interactive

# Travel an archipelago with real ferry construction.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --base 0 --form survival --architecture archipelago --arc sandbox \
  --interactive

# Safely explore orbit transfers across time windows.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --base 12 --form tactics --architecture orbit --arc roguelite \
  --interactive

# Execute a reproducible scripted expedition.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --base 0 --form puzzle --architecture lattice --arc endless \
  --actions-json '[{"layer":"spatial","verb":"extract","amount":2},{"layer":"spatial","verb":"travel","target":1},{"layer":"mode","verb":"toggle","target":0},{"layer":"causal","verb":"end_turn"}]'

# Replay after saving to a self-contained local file.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --index 12287999 --interactive --save saved-tenfold.json

python -m skeleton.game.generation.original_world_tenfold_cli \
  --load saved-tenfold.json --interactive --save saved-tenfold.json

# Existing original-world preview now supports the new layer as well.
python -m skeleton.game.generation.original_world_cli \
  --spatial-index 1023999

python -m skeleton.game.generation.original_world_cli \
  --tenfold-index 12287999 --brief
```

The interactive terminal distinguishes `spatial`, `mode`, `arc`,
and `causal` actions, for example `spatial ferry`,
`spatial travel 5`, `mode guard`, `arc reflect`, and
`causal end_turn`.

## Verification and maturity gates

The `Original World Atlas` GitHub workflow checks exact-head integration,
compiles modules, runs all prior original-world tests and new dedicated
topology, causality, persistence and CLI tests. The new tests verify the
10× indexing formula, exact source compatibility, full traversal graphs,
disconnected archipelago and pocket gates, temporal route changes,
physical costs, per-site resource depletion, replay, tampering detection,
and real nested genre controls.

**The user-facing tenfold world namespace is not tenfold more independently
written stories, or proof of tenfold richer individual games.** The next
completion gates are:
- Bespoke executable behavior for the large corpus of original fictional
  world laws rather than shared abstract meters.
- Unbounded/sparse chunking beyond the current 24-sector architecture
  reference, including native voxel/mesh rendering and physical collision.
- NPC population and generational economies acting across all ten
  architectures, rather than only the prior four adapted original worlds.
- Complete gameplay genre breadth (FPS, RTS, fighting, visual novels,
  sports simulation, musical instruments, production-grade open world),
  editor UI, homebrew compilation, legal/IP analysis, and human playtests.
- Deterministic benchmark and replay proof on consumer hardware, game
  packaging, accessibility, user content authoring and creator workflows.

That boundary is an intentional integrity requirement: an enormous design
namespace should support a game-production pipeline, **not substitute for
verified production deliverables**.


## Pathfinding as an engineering primitive, not a cosmetic waypoint

`original_world_tenfold_navigation.py` supplies a deterministic,
resource-conscious Dijkstra route planner for all ten topologies.
It calls the **actual navigation transition function**, including
current changing passages, energy, propellant, oxygen, hazard and
consent/portal preconditions. A path across disconnected islands is
not returned without a built ferry service; an uncalibrated pocket
gateway cannot be bypassed by optimistic map geometry.

Four route objectives are implemented: `balanced`, `fastest`,
`safest`, and `fuel-frugal`. These are explicit cost preferences,
not promises of global optimality across future stochastic world
phases. Search is bounded to 4096 expansions and never guesses
that a twelve-hour journey can fit four remaining turn actions.

Route plans carry the source location, current phase, current
event head, exact graph nodes and resource estimates. Executing
a route rejects a changed source state, performs full immutable
simulation and returns only if every movement passes. Routes too
long for the present action budget are provided as **plans only**,
not partially executed when the user requests atomic travel.
Changing maze, wind or orbital phases requires re-planning.

```bash
# Inspect a preflighted, resource-accounted route.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --base 0 --form puzzle --architecture lattice --arc sandbox \
  --route-target 1 --route-priority safest

# Execute only when every route action can be completed this turn.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --base 0 --form puzzle --architecture lattice --arc sandbox \
  --route-target 1 --execute-route

# Calibrate a portal first; only then can the planner enter the pocket.
python -m skeleton.game.generation.original_world_tenfold_cli \
  --base 0 --form puzzle --architecture pocket --arc sandbox \
  --actions-json '[{"layer":"spatial","verb":"attune"}]' \
  --route-target 12 --execute-route
```

Interactive play also supports `route N` for an inspectable
preflight plan and `go N` for an atomic execution attempt.
Every route taken produces individual event receipts that remain in
the game's save/replay chain.
