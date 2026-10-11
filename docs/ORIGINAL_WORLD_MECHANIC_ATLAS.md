# Original World-Law & Mechanic Atlas — October 2026

**Owner:** Existing `skeleton/game/generation` domain.  
**Status:** Committed, deterministic **design-recipe compiler**; **not** 1.57 quintillion built games.  
**Version:** `original-world-atlas.v2`.

This work responds to the need for a truly expansive game builder rather
than a palette-swapping level generator. A world is defined by an *original
causal invariant*, a *player-controlled lever*, and an *ending policy*. A
mechanic is defined by its *trigger*, *effect on the world*, and *drawback*.
The catalog does not import copyrighted maps, scripts, characters, game
assets, platform firmware, or protected SDK material.

## Verified authored inventory and capacity

| Layer | Count | Authoring and implementation status |
| --- | ---: | --- |
| Original world premises | **1,296** | 81 causal domains, 16 independent world laws each |
| Independently authored mechanic specifications | **712** | Each has trigger, proposed effect and stated drawback |
| Derived, world-specific action levers | **1,232** | Drawn from authored worlds; **cost model not implemented** |
| Mechanic/lever design entries | **1,944** | Exactly 24 selectable designs in every domain |
| Explicit authored cross-domain bridge descriptions | 52 | Original pairings retained; further bridges are inferred hypotheses |
| Cross-domain interaction hypotheses per recipe | 55 | One for every pair among 11 represented domains |
| Mechanics and levers in each recipe | 12 | Two native-domain entries plus ten distinct foreign domains |
| Topology design tags | 12 | Not equivalent to implemented map generators |
| Era options | 40 | Independent from world originality |
| Chronology settings | 32 | Historical, alternate, branching, cyclic and other times |
| Invented theology models | 24 | Non-theistic, invented pantheons, animism, oracular settings, etc. |
| Theme options | 81 | Up to eight theme tags in a single experience |
| Emotional tones | 24 | Ultra-snuggly to nightmarish; independent comfort 0–100 slider |
| Visual styles | 32 | Retro pixels, illustrated modes, physically based render targets |
| Simulation-realism profiles | 12 | Symbolic to hyperrealism **targets**, not validated physics |
| Hardware-target tags | 41 | Platform adaptation requests, **not** certified builds |
| Executable abstract mechanic kernels | 8 | Deterministic Python prototypes; not console/3D gameplay |
| Exact indexed design combinations | **37,341,018,089,543,468,949,354,074,603,520** | Combinatorial recipes, not independently reviewed games |

The exact number of distinct world/mechanic recipe identities is

```python
from math import comb

total = 1296 * comb(24, 2) * comb(80, 10) * (24 ** 10)
assert total == 37_341_018_089_543_468_949_354_074_603_520
```

Each recipe selects two of the world's 24 entries, chooses ten of the other
80 domains, and chooses one of 24 mechanics or levers from each chosen
domain. The 55 pairwise bridges are only **interaction proposals**; 52
pair types have authored interpretations, while other pairings use visibly
labeled inference templates. Entries with `cost_specified=False` require
genuine playable effects and balanced costs before implementation.

Recipe uniqueness guarantees a different world ID or mechanic identity.
It does **not** guarantee meaningful experiential diversity or
compatibility; combinations must pass causal consistency, accessibility,
quality, originality and runtime checks before promotion.

Presentation dimensions **never multiply the independent authorship count**.
An original world rendered as cozy pixel art and then as cinematic 3D is
one original causal foundation with two presentation configurations.

## User-facing and engine-facing contract

```python
from skeleton.game.generation.original_world_compiler import (
    TOTAL_VARIANTS, blueprint_at, blueprint_for_world, blueprint_from_seed,
)

# Exact-addressable deterministic design blueprint, no remote model call:
design = blueprint_at(1_000_000_000_000)
assert design.realization_status == "design-only"
print(design.world.title, design.ending_policy, design.recipe_id)
for mechanic in design.mechanics:
    print(mechanic.title, mechanic.trigger,
          mechanic.state_change, mechanic.drawback)

# Or select a seeded deterministic sample:
same_design = blueprint_from_seed("my-world-design-v1")
```

`recipe_id` is a SHA-256 digest of a canonical world ID plus mechanics ID
set and compiler version. It does not hash implementation artifacts or imply
a runtime has built a game. `as_dict()` copies the projection for
serialization without exposing mutable registry objects. The compiler
does not write stores, run background jobs, call providers, or mint AI
competence XP.

## Comparison: rule domains must change actual play

| Domain | Example mechanic | What the player actually changes | Possible systemic consequence |
| --- | --- | --- | --- |
| Topology | Occlusion Drift | Unobserved doorway edges | Routes become unstable under surveillance gaps |
| Time | Future Collateral | Present action budget | Debt is charged to future tactical opportunities |
| Ecology | Trophic Bargain | Predator/prey links | An ecologically displaced population moves |
| Law | Appeal Rewrite | Cause/evidence relations | Prior decisions require legally coherent repair |
| Physics | Spoken Gravity | Local gravitational vector | Speech can destabilize a bridge |
| Infrastructure | Last Train Rewire | Transit station destinations | Scheduling changes the map |
| Identity | Split Persona | Memory and agency allocation | Different bodies acquire inconsistent histories |
| Machines | Component Referendum | Maintenance permissions | Repair becomes organizational negotiation |
| Economy | Mass Credit | Mass and credit balances | Construction raises physical carrying costs |
| Language | Tense Storm | Weather event ordering | Grammar has meteorological impact |
| Mortality | Age Burden Transfer | Age liability | Resurrection requires real consenting sacrifices |
| Voyage | Endless Survey | Explorable frontier | No artificial last map square is required |
| Belief | Myth Repayment | Future event obligations | Fiction can produce society-wide real-world debt |
| Civilization | Promise Foundations | Trust-based construction slots | Broken promises degrade the city |
| Scale | Recursive Stair | World nesting and clock rate | Navigation requires parent coordinate and time lineage |
| Performance | Stage Legislation | Temporary physical law | An enacted performance can govern the arena |

There is a major gameplay distinction between an action that changes a
number and an action that rewrites a *law*. When possible, the runtime
should reveal the specific affected agents, causal graph, costs, recovery
paths and world history. An invisible number buff does not qualify as a
successful implementation of a world-law mechanic.

## Twelve composed original experience specifications

1. **The Clockwork Refuge:** A living factory metropolis elects replacement
   parts, accumulates debt in construction mass, and sends refugees along
   rotating subways. A repaired machine can make housing heavier and
   therefore unaffordable.
2. **The Unseen Parliament:** A city whose doors follow traveler fears
   uses visitor-only elections to alter its exits. Surveillance can keep
   elected routes open but endanger dissidents.
3. **The Reef of Tomorrow:** Habitats move between dates like islands;
   ancestral species memory changes ocean migration, so rescuing a
   population may erase its present ecosystem.
4. **The Court of Empty Names:** Citizenship follows surrendered names,
   object rights veto tool use, and historical testimony collapses when
   the witness learns the outcome. Justice must remain possible without
   omniscient evidence.
5. **The Funeral Orchestra:** Revived performers inherit communal
   commitments; playing a lost city's acoustic pattern restores structures
   while consuming memories of the dead.
6. **The Unending Cartographic Voyage:** Frontier terrain keeps extending,
   harbor access is one-way, and companions age into new roles.
   Exploration itself is the point; there is no victory flag.
7. **The Chorus of Molecules:** Communities inhabit the chemical
   bonds of a giant living organism. Coordination at one scale produces
   conservation debt at another; no single zoom level tells the truth.
8. **The Province That Cannot Finish:** Every successful map publication
   physically changes the geography, relocating already-discovered
   objectives. Victory can be mathematically impossible by design, but
   local projects remain meaningful.
9. **The After-Campaign Constitution:** A war can end, but appeal law,
   trade, rebuilding, and faction legitimacy continue evolving.
   Ending the central quest starts the postgame simulation.
10. **The Orchard of Forgotten Selves:** Citizens grow temporary
    personalities and adopt abandoned ancestors. One moral victory may
    destroy a useful skill or destabilize a legal obligation.
11. **The Theatre of Conditional Fire:** An audience's expectations
    control ignition; performances vote for temporary natural laws.
    A persuasive cast can weaponize belief, requiring safety and consent
    counter-mechanics.
12. **The Rain-Bred Borderlands:** Weather-bearing animal herds steer
    migration, border markers are citizens, and pollination is contractual.
    Military conquest does not solve drought; ecological diplomacy does.

These are assembled *design hypotheses*, not twelve already completed
runtimes. In each case, implementers should identify the specific game
state, causal change, conflict policy, persistence model, and concrete
player feedback before describing it as playable.

## Game forms that must remain valid

**Finite:** An achievable endpoint exists; victory may transition to a
separate persisted postgame ecology and economy.

**Postgame:** Main campaign closure does not stop NPC schedules, settlement
change, infrastructure evolution or exploration.

**Persistent and sandbox:** The player's objective may be local, emergent,
or absent; world state outlives a session.

**Unwinnable:** Win condition is intentionally absent or logically
inconsistent, with disclosure and accessible gameplay still required.
Avoid trapping users in a faux-win grind.

**Looping:** Reset may rewind only some subsystems; player knowledge,
social memory, debt, or structural damage can persist.

**Branching:** Player actions create mutually exclusive consequences; the
history ledger must record which paths were taken.

**Open:** Optional objectives and exploration may expand indefinitely,
subject to storage/resource budgets and finite per-tick work.

A changing maze is not only a shuffled bitmap: its adjacency, entry
conditions, observation rules, recoverability and navigation receipts
are stateful. An infinitely expanding world is not a proof of infinite
content: use bounded streamed chunks, compact world seeds and monotone
world identities, with persistence and recovery defined.

## Realization ladder — gaps not hidden

1. **Catalog** (present): authored world premises and mechanic effects with
   explicit costs and temporal/ending intentions.
2. **Indexed compilation** (present): stable combination IDs, domain
   diversity, compositional bridges and seed replay.
3. **Machine-checkable rule graph** (next): typed state channels, resource
   conservation, action preconditions, mutually exclusive effects, world
   event receipts, configurable but bounded procedural operators.
4. **Executable game simulation** (next): deterministic engine interpreters
   for representative rules; 3D/2D/voxel/graph adapters, conflict handling,
   replay, savegame and migration.
5. **Player-facing editor** (next): mechanic import/export, visual rule
   dependency graph, conflict diagnosis, cost preview, undo, accessibility,
   narrative/ending policies and postgame state inspection.
6. **Hardware realization** (next): platform budget estimates and honest
   source/compiled/emulator-tested/device-tested readiness per target.
7. **Adversarial originality review** (next): perceptual similarity,
   narrative and level-layout duplication screens, trademark/copyright
   review, no unlicensed game code, no impersonated franchise identity.
8. **Evidence-backed quality promotion** (next): independent playtest
   outcomes, meaningful agency metrics, novelty evaluation against a
   licensed/provenance-safe corpus, stable performance and rollback.

A large theoretical recipe space is not enough. The game-builder must be
able to *implement*, *explain*, *playtest* and *differentiate* the sampled
worlds, and must not confuse source generation with runnable ROMs. The
Dragon native-game pipeline remains the hardware adapter boundary.

## Reproduction and validation

```bash
python -m pytest -q tests/test_original_world_mechanic_atlas.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

The file-level content does not alter service topology, provider adapters,
credentials, public endpoints, persistence ownership or runtime authority.
A PR must pass its exact-head checks before this layer is called integrated.

## IP and machine-knowledge guardrails

All authored atlas entries describe abstract mechanics and original
settings. New game projects must use independently created characters,
dialogue, level geometry, sound, art and code. Mechanic ideas alone do not
grant rights to copyrighted game assets, narrative expression, source
code, trademarks or restricted platform SDKs. The crawler/Dragon can cite
and study authorized sources under the repository's established knowledge
promotion workflow, but no unverified scraped assets or proprietary code
should enter the generated world.

**Honest maturity statement:** 1,296 authored world laws, 712 independently
specified mechanic concepts and 1,232 derived world levers are cataloged.
The vast indexed space is design-only until runtime/evaluation promotion.

## October 2026 expansion: eras, chronologies, religions, themes, fidelity

`skeleton/game/generation/world_styling.py` declares these axes separately.
A world can be Neolithic and animist, contemporary and secular,
a far-future invented pantheon, or an explicitly contradictory alternate
history. Each combination remains a *design request* until the supporting
asset pipeline and simulation engines demonstrate it.

Emotional comfort and presentation realism are orthogonal: a
high-fidelity physically simulated village may be exceptionally comforting;
an eight-bit low-resolution dungeon may be genuinely nightmarish.
Choose comfort and realism independently over integer ranges 0–100.
`WorldStyling` rejects unknown identifiers, non-integer sliders, repeated
themes and unbounded theme lists.

`world_experience_manifest.py` projects a recipe and styling into a
deterministic `experience_id`. The core `recipe_id` does not change
when art, theology, chronology or emotional intensity changes. Its
compatibility findings identify uncosted world levers, inferred mechanic
interactions, fidelity demands that exceed unverified retro budgets,
and mismatches between requested comfort and intense tones.

**No runtime extrapolation is counted as an additional authored original.**
For example, a gentle, dense-garden version of a branching historical
world and a hyperrealistic, frightening, distant-future version may share
the same core authorial premise but produce different experience digests.

## Eight bounded executable mechanic kernels

The atlas now includes a small abstract Python interpreter at
`skeleton/game/generation/original_world_simulator.py`.
It implements only these action IDs:

| Mechanic | Executable state change | Constraint actually checked |
| --- | --- | --- |
| `time-m01` Future Collateral | Borrow 1–3 actions into the current turn | Future action debt is repaid; bounded ceiling |
| `topology-m02` Occlusion Drift | Rotate a five-room traversal cycle | Only on unobserved transition; never removes a room |
| `ecology-m02` Rain Herding | Move rainfall between two regions | Total precipitation is exactly conserved |
| `serenity-m01` Soft Rest | Restore energy in a safe abstract scene | Energy capped; player spends an action |
| `survival-m01` Resource Intake | Gather food into a player reserve | Local wildlife/food reserves decrease equally |
| `crafting-m04` Repair Workflow | Restore shelter durability | Wood, energy and actions decrease |
| `physics-m02` Shadow Momentum | Shift a bounded simulated momentum state | Energy costs and momentum bounds enforced |
| `infrastructure-m01` Last Train Rewire | Rotate transit destinations at last train | Preserves connected room-cycle identity |

Every accepted transition records a deterministic SHA-256 evidence digest.
Illegal requests fail without mutating frozen state. Tick advancement pays
future-action debt. The simulator supports replay and source-code tests.

It is deliberately named **abstract simulation**; it does not render a
world, run its 1,944 candidate actions or compile hardware-native game
binaries. Only a small proportion of the candidate mechanic catalog is
connected to this interpreter.

## Offline preview — executable user-facing entrypoint

```bash
python -m skeleton.game.generation.original_world_cli \
  --seed gentle-history \
  --era paleolithic \
  --chronology remote-past \
  --theology animist-invented \
  --theme comfort \
  --theme mystery \
  --tone ultra-snuggly \
  --comfort 100 \
  --realism 95 \
  --simulation-realism environmental-sim \
  --hardware-target pc-windows \
  --brief

python -m skeleton.game.generation.original_world_cli \
  --index 123456789 \
  --era deep-future \
  --theology cosmic-mythic \
  --theme cosmic-horror \
  --tone nightmarish \
  --visual-style photorealistic-target \
  --simulation-realism hyperrealism-target \
  --realism 100 \
  --demo-rules
```

The latter command includes an **independent** abstract simulation demo.
The simulation is not a compilation of the sampled recipe; that distinction
is stated in the command output.

Focused tests:

```bash
python -m pytest -q \
  tests/test_original_world_mechanic_atlas.py \
  tests/test_original_world_simulator.py
```

## Unfinished integration work, expressed plainly

- Mechanic catalog: 712 independently cost-described specifications and
  1,232 derived levers require complete typed execution semantics,
  compatibility gates and economically coherent outcomes.
- World variation: 12 topology tags are design hints. Dynamic mazes,
  streaming voxel terrains, multiple dimensions and open-ended frontiers
  need dedicated runtime realizers and save/replay policies.
- Porting: 41 hardware choices are *tags*, not 41 executable emitters.
  Continue using Dragon's existing per-platform native source,
  compiler and emulator verification lanes. Do not bundle proprietary
  SDKs, firmware or licensed game assets.
- Visual quality: a photorealistic render target does not prove
  physically accurate simulation. Benchmark each supported adapter,
  motion system, animation budget, accessibility setting and model.
- Authorship: 1,296 distinct written premises and 712 separately described
  mechanic implementations are useful source material, not
  externally peer-reviewed originality proofs or independent games.
- Shipping: no evidence here demonstrates that all game styles or original
  worlds have been transformed into finished playable software. Preserve
  the design-only status until proven otherwise.
