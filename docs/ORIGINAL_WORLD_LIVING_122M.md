# Original Living Worlds — 10,240,000 foundations / 122,880,000 configurations

**Design version:** `original-world-living-10x.v1`  
**Implementation:** `skeleton/game/generation/original_world_living_10x_*.py`  
**Status:** Bounded offline Python reference simulations, not independently
written game scripts, 3-D engines, production NPC models or console binaries.

## Exact scale and why it is not numerical fiction

The previous spatial world layer had 1,024,000 indexed causal foundation,
genre and architecture compositions, with 12 continuation contracts making
12,288,000 advanced game configurations.

This wave introduces an independent, **mechanically executing** living-world
axis: ten separately authored autonomous simulation laws. Each offers
three distinct player interventions and its own turn-by-turn physical
or social state dynamics. No cosmetic, hardware, seed, era, palette, or
difficulty multiplier contributes to the headline.

| Layer | Count | Description |
| --- | ---: | --- |
| Individually written original world-root premises | 1,424 | Previously authored fictional causal premises; not all bespoke playable |
| Composed authorial root/regime laws | 10,240 | 128 separately written roots × 80 independently authored consequence regimes plus 160 explicit bridges |
| Executable gameplay forms | 10 | Platform, puzzle, tactics, survival, colony, racing, stealth, commerce, exploration, rhythm |
| Distinct executable spatial reference laws | 10 | Civic grid, spiral, labyrinth, archipelago, strata, canopy, orbit, pocket realms, phase city, abyss |
| New **independently written living system rules** | **10** | Distinct premises, scarce stocks, actor processes, failure conditions, and intervention mechanisms |
| **Living gameplay foundations** | **10,240,000** | 10,240 base laws × 10 genres × 10 topologies × 10 living systems |
| Real continuation contracts | 12 | Bounded temporal and story arc mechanics |
| **Advanced living configurations** | **122,880,000** | 10,240,000 × 12 arcs |
| New living-specific player verbs | **30** | Three state-changing interventions per autonomous law |
| Individually handwritten new 122.88m world premises | **0** | The 122.88m are machine-composed combinations, never independently handwritten |
| Certified native game releases | **0 verified** | No generated native game binaries in this implementation |

Previous inventories are **nested within this design space, not additional
numbers to sum into a fictitious world count**. Older `foundation_at`,
`advanced_at`, `spatial_at` and `tenfold_at` continue addressing
the same source items with unchanged numeric ranks.

This layer has the exact index formulas:

```text
base:            [0, 10_239]
form:            [0, 9]
architecture:    [0, 9]
living system:   [0, 9]
arc:             [0, 11]

spatial_index = ((base * 10) + form) * 10 + architecture
living_foundation_index = spatial_index * 10 + living_system
world_index = living_foundation_index * 12 + arc

living_foundation_index range: 0..10_239_999
world_index range:             0..122_879_999

source_tenfold_index = spatial_index * 12 + arc
```

Each exact index resolves lazily, deterministically and without allocating
122 million records. IDs include versioned SHA-256 causal design signatures,
original source references and provenance.

## Ten new actually executing living-world systems

| World law | Three actual interventions | Autonomous world-turn changes and conservation |
| --- | --- | --- |
| The Hungry Web | `reseed`, `graze`, `protect` | Finite seed banks germinate into vegetation; herbivores eat plants and predators consume a real prey herd. Starvation can end a population |
| The Settlement That Remembers | `house`, `welcome`, `ration` | Finite homes support households; citizens eat real food; shortages drive departures and unrest; arrivals wait for space |
| Traveling Markets | `dispatch`, `escort`, `unload` | Cargo physically moves through a two-world-turn delivery clock. Missing escorts risk losses; buyers cannot pay for nonexistent inventory |
| The Borrowed River | `irrigate`, `dam`, `release` | Variable rainfall fills finite dams, evaporation reduces stored water, overflow causes persistent flood damage and irrigation consumes reservoir contents |
| The Night Grid | `generate`, `charge`, `route` | Generation consumes real spatial-world fuel; electricity serves demand; scarcity produces outages and wear |
| Fictional Spore Accord | `isolate`, `remedy`, `study` | Fictional affected, unaffected and recovered organism cohorts exchange population; finite remedies and isolation prevent free cures |
| The Patient Machines | `design`, `assemble`, `service` | Automated builders execute real queued designs, consume parts and accumulate wear; physical maintenance restores work capacity |
| The Evidence Commons | `observe`, `verify`, `teach` | Observations must pass material-backed peer verification; only supported knowledge diffuses into a public commons, while unverified rumors persist |
| Treaty of Three Valleys | `petition`, `pledge`, `mediate` | Faction tension accumulates when obligations remain; promises require physical offerings; resolution spends trust |
| Debt of Repeated Mornings | `record`, `hasten`, `reconcile` | Delayed effects mature after bounded turns, debts persist and unresolved paradox pressure increases hazards; no rewind alters earlier receipts |

The fictional spores are a **fantasy ecosystem mechanic**, not a real-world
clinical or epidemiological model. All population and ecological models
are game-scale approximations and must not be represented as scientifically
predictive.

## The four nested control layers

The player's selected game contains:

- `living VERB`: one of the three meaningful interventions permitted by
  the selected autonomous system; spends actual resources and action points
- `spatial VERB`: movement, extraction, structures, infrastructure and
  physical travel under the chosen topology
- `mode VERB`: actual control of the selected platform, puzzle, tactics,
  survival, colony, racing, stealth, commerce, exploration or rhythm reference game
- `arc VERB`: persistent generational, narrative, faction and other
  continuation effects; `causal end_turn` drives the underlying source
  world and living clock together

Every accepted command generates a deterministic SHA-chained receipt.
The save envelope contains all embedded four-layer state and a checksum,
rejects unexpected fields, audits exact source IDs and validates temporal
synchronization. SHA-256 save checksums are **integrity checks, not
cryptographic authentication against a malicious person who recomputes them**.

An explicit crisis/objective director reads actual live state instead
of providing arbitrary completion badges. It records real player
intervention receipts, independently observed world ticks, and
domain-specific stability conditions. It can recommend finite
repair action or warn that a settlement is starving, a trade route
is unescorted, power is failing, artificial organisms are affected, or
temporal debts remain unpaid. A stabilized local system does not
override an authored world's deliberately unwinnable or open-ended policy.

## Run a real offline reference world

```bash
# Confirm exact provenance figures, without style or theme multipliers.
python -m skeleton.game.generation.original_world_living_10x_cli --inventory

# Jump to the last three indexed configurations without loading all entries.
python -m skeleton.game.generation.original_world_living_10x_cli \
  --page 122879997 --limit 3

# Play an original ecosystem on a living archipelago.
python -m skeleton.game.generation.original_world_living_10x_cli \
  --base 0 --form survival --architecture archipelago \
  --system trophic --arc endless --interactive

# Run a civic simulation in a changing phase city.
python -m skeleton.game.generation.original_world_living_10x_cli \
  --base 0 --form puzzle --architecture phase \
  --system diplomacy --arc branching --interactive

# Operate a constructed power grid in an orbital tactics world.
python -m skeleton.game.generation.original_world_living_10x_cli \
  --base 0 --form tactics --architecture orbit \
  --system power --arc roguelite --interactive

# Demonstrate credited knowledge promotion and measurable objectives.
python -m skeleton.game.generation.original_world_living_10x_cli \
  --base 0 --form puzzle --architecture phase \
  --system knowledge --arc mystery \
  --actions-json '[{"layer":"living","verb":"observe"},{"layer":"living","verb":"verify"},{"layer":"living","verb":"teach"},{"layer":"causal","verb":"end_turn"}]' \
  --objectives

# Maintain save history offline.
python -m skeleton.game.generation.original_world_living_10x_cli \
  --index 122879999 --interactive --save living-save.json

python -m skeleton.game.generation.original_world_living_10x_cli \
  --load living-save.json --interactive --save living-save.json

# The original atlas can preview both new tiers without renumbering prior worlds.
python -m skeleton.game.generation.original_world_cli \
  --living-foundation-index 10239999

python -m skeleton.game.generation.original_world_cli \
  --living-index 122879999 --brief
```

Terminal commands include `living reseed`, `living dispatch`,
`living remedy`, `living verify`, `living reconcile`,
`mode toggle 0`, `spatial travel 1`, `causal end_turn`,
`goals`, `status`, `help`, and `quit`.

## Verification and honest remaining work

The dedicated `Original World Atlas` workflow compiles the new and
previous game modules, runs the prior atlas and physical-simulation
regression suites, checks 122.88m index boundaries and exact source
round trips, tests all ten intervention systems and their autonomous
turns, validates 100 living/spatial pairings and all 120 genre/arc
pairings, checks resource conservation, persistent chronology,
tampering rejection, actual CLI play and save/load, and executes a
complete mini-journey through the oldest and newest atlas APIs.

**This wave adds meaningful systemic simulation logic, not millions of
independently written worlds.** Critical remaining deliverables:
- Individually authored narrative content and bespoke executable
  world mechanics at the scale of the target counts.
- Full character/entity AI, habitats and behavior trees across the
  physical topologies rather than bounded population meters.
- Big worlds: sparse/chunked open terrain, streaming meshes,
  real collision, weather, rendering, animation, audio and camera control.
- Real editors, playable 2D/3D builds, native packaging and licensed
  homebrew pipelines, with legal and originality reviews.
- Consumer-grade device performance, safe fault recovery,
  adversarial simulation verification and user playtesting.
- Human judgments of actual distinctness, depth and quality; indexed
  coverage is not commercial readiness or fun.

The PR remains **draft and unmerged** until its exact-head checks and
repository-wide integration gates are resolved.
