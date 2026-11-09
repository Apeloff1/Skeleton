# Original Worlds — Era-aware NPC population and hardware fidelity

> **Updated population policy (October 11, 2026):** The 16,384
> regional census and 32-local-NPC examples below describe the original
> **legacy v3 stress/reference configuration**, not the default for newly
> generated worlds. New games derive realistic, genre-aware budgets from
> all 41 registered consoles/PC targets, nine PC hardware generations,
> ten playable genres and 40 world eras. Newly generated games now cap
> **local persistent NPC slots at 24** and **offscreen aggregate census at 144**,
> usually substantially less. Existing saved large worlds remain loadable.
> For the currently authoritative defaults and commands, see
> [Console, PC and Genre NPC Fidelity](ORIGINAL_WORLD_NPC_PLATFORM_GENRE_FIDELITY.md).
> Hardware certification and objectively measured industry averages are
> not claimed.


**Implementation scope:** Directly executable original-world gameplay for all
40 existing era names, persistent local NPCs, sparse remote settlements,
material-backed trade and optional embodiment of named residents.

**Nonclaim:** A census of 16,384 is not 16,384 simultaneously running
individual AI personalities. The distinctions below are part of the public
game report and the native rendering, not hidden implementation details.

## Real game capacities

The era policy comes from the canonical 40-entry `ERA_LEVELS` technology
mapping; the demographic model does not multiply the number of separately
authored games. Era controls local professions, brains, regional census
and visual/activity budgets. Future worlds grow rather than installing
more global full-depth Python objects.

| Era example | Max local physical named NPCs | Default initially active local identities* | Background census | Regions |
|---|---:|---:|---:|---:|
| Primordial Earth / Early Life | 1 compatibility observer | 1 | 0 | 0 |
| Paleolithic | 8 | 6 | 24 | 2 |
| Bronze Age | 11 | 9 | 384 | 8 |
| Classical Antiquity | 14 | 12 | 1,152 | 14 |
| Early Industrial | 20 | 18 | 4,800 | 26 |
| Digital Network | 26 | 24 | 12,544 | 38 |
| Interstellar / Posthuman / Cosmic | 32 | 30 | 16,384 | 50 |

*Two local body/memory slots are reserved for subsequent genuine births or
regional migrants, except in the single-observer prehuman compatibility tier.
The one local compatibility observer for primordial or early-life games is a
**tool-facing reference-game agent**, not a claim that humans existed then.

Every local person retains an individual unique body, health, hunger,
profession, evolving mind, witnessed memories, social connections, physical
labor, original-game role contracts, mentorship, government participation
and family continuity when the corresponding world action occurs.
**The expensive cognitive planner is separately budgeted per day.**

A regional district retains: physically passable anchor coordinates, living
census, finite food pantry, group morale, hardship, historical deaths, last
time actually processed, fractional ration accounting, and an immutable
per-world event chain. Remote groups are **simplified cohort simulations**.
Their health and food are tracked at district resolution. A district is not
a global container granting unlimited offscreen food extraction.

## Four consumer-device fidelity presets

| Preset | Max actively planned local minds per world turn | Offscreen district update policy |
|---|---:|---|
| `economy` | 3 | Up to 1 district per turn |
| `balanced` | 7 | Technology-tier budget (usually 1–5) |
| `vivid` | 16 | Up to 8 districts per turn |
| `unrestricted` | 32 | Up to 8 districts per turn |

The planner selects **actual named local people** by survival urgency,
real contract obligations, physically nearby player interaction,
specific construction/medical/family need, and deterministic fairness.
Only selected residents run expensive perceptual searching and
per-person action planning. All **unselected bodies remain real**:
they still experience world time, hunger, aging, health consequences and
saved physical identity, but cannot invisibly teleport, build, perform
offscreen trade, generate resources, receive imaginary diplomas,
or vote on events while asleep.

These are bounded **simulation work quotas**, not fabricated frames per
second or hardware benchmark results. CPU runtime will vary by actual
machine and test environment. Users can change the workload preset
without erasing resident brains, census, memory, inventory or histories.
Visual impressions are independently capped at up to 64 anchored sprites,
and are labeled as decorative crowd proxies with **no autonomous cognition,
inventory, voting or independent resource ownership**. Region pins and
real people use separate graphical glyphs.

## Real regional economy, route latency and starved settlements

Every generated district starts with a **finite initial food reserve**.
Its simplified residents consume rations as actual regional world time
passes. A capped number of district ledgers update each turn, catching up
the elapsed days with fixed-point fractional-food bookkeeping; they
experience declining morale and population when food is short.
A world does not mint food simply by increasing its historical era.

The player can send physically owned food to a regional district or
request stocked food from a district. The source pantry/depot is debited
**at departure**, a persistent caravan records origin, direction, amount
and travel time, and delivery waits for actual world turns. If the
destination warehouse is full, the food remains committed in transit;
there is no free duplication or instantaneous arrival. Source,
in-transit, destination and consumed quantities form the conservation
ledger.

## A real cohort can become a genuine named citizen

`population recruit REGION` is possible only when the player has
physically reached the corresponding passable district site, has a
free era-authorized local NPC slot, and spends actual civic trust and
one gameplay action. A single **counted** regional resident is deducted
from the region's census. The game creates one new, persistently named
and located NPC body, one seeded but individual mind, one adult age,
and an irreversible migration receipt tying the person to the source
district. Existing citizen memories, families, jobs and identities
are not regenerated.

Repeated recruitment cannot create citizens once a region is empty or
the high-fidelity capacity is full. The background census and local
body count are conserved across promotion, apart from actual births
and documented regional mortality.

## Commands

```bash
# A 40-era game with manually budgeted thinking, region pins, ambient crowds.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox \
  --era interstellar --npc-fidelity economy --desktop \
  --save interstellar-world.json

# Inspect real census, objective CPU budgets and finite regional food.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox \
  --era interstellar --npc-fidelity economy \
  --population-report --show-map --radius 16

# Physical material transport from home to regional depot.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox --era digital-network \
  --actions-json '[{"layer":"population","verb":"dispatch_food","target":0,"option":"to-region","amount":2},{"layer":"causal","verb":"end_turn"}]' \
  --save network-game.json --population-report

# Interactive game:
# districts
# population set_detail vivid
# population dispatch_food 0 to-player 3
# [walk physical steps to the actual regional site shown on the map]
# population recruit 0
# person 30
# causal end_turn
```

The entire embedded Python game and its module dependencies can be
distributed using `original_world_product_bundle.py`. Windows/Linux
native executables are built and separately smoke-tested by
`original-world-native-builds.yml`. Neither the Python artifact
nor platform binary is a signed commercial game, a licensed
historical asset package or a console homebrew ROM.

## Acceptance and adversarial invariants

This milestone adds unit/integration proof covering:
- All 40 era classifications and scaling budgets.
- Historical profession gating; no paleolithic engineers.
- Prehuman regional census zero rather than invented human settlements.
- 30 detailed initial interstellar people, plus two local future slots.
- Bounded region count and constant-work scheduling regardless of census.
- Concrete survival/emergency prioritization of a distant named citizen.
- `economy` (3), `balanced` (7), `vivid` (16) and
  `unrestricted` (32 maximum) individually planned minds per turn.
- Passive individual bodies never mint cargo, expertise, movement, or votes.
- Strict census conservation between background and actual named promotion.
- Real physical location/trust/slot checks for recruiting a regional resident.
- Material conservation across all caravan steps, including late arrivals.
- Empty pantry hardship and mortality, not free meals.
- Persistent district event heads and checksum-backed replay.
- Real SVG, PPM, ASCII and Tk overlay distinction between regional aggregates
  and individually interactive NPC sprites.
- Exact-head game tests and Windows/Linux build smoke.

## Completion boundary

This is a measured **local-plus-regional LOD milestone**. It does not
claim real-time whole-planet population simulation, an individual
neural-network mind for every world inhabitant, 16,384 physically animated
people, high-quality unrestricted spoken dialogue, multi-world political
simulation, biologically validated demographic history, native consoles,
or commercial frame-rate certification. Those remain further substantial
milestones. Performance must be measured on real target consumer hardware
rather than inferred from a population number.
