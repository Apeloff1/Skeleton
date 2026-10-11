# Original World-Law & Mechanic Atlas — October 2026

**Owner:** Existing `skeleton/game/generation` domain.  
**Status:** Committed, deterministic **design-recipe compiler**; **not** 1.57 quintillion built games.  
**Version:** `original-world-atlas.v1`.

This work responds to the need for a truly expansive game builder rather
than a palette-swapping level generator. A world is defined by an *original
causal invariant*, a *player-controlled lever*, and an *ending policy*. A
mechanic is defined by its *trigger*, *effect on the world*, and *drawback*.
The catalog does not import copyrighted maps, scripts, characters, game
assets, platform firmware, or protected SDK material.

## What exists in this delivery

| Component | Implemented | Meaning |
| --- | --- | --- |
| Authored world-law designs | 128 | Sixteen rule domains, eight independently described premises each |
| Authored mechanic designs | 192 | Sixteen domains, twelve trigger/effect/drawback specs each |
| Mechanic selection | 12 per recipe | Exactly two from the seed world's domain and ten from distinct others |
| Rule-bridge hypotheses | 52 authored pairs | Explicit semantic explanations for cross-domain consequences; not engine execution |
| Structural topology tags | 12 | Design hints for dynamic maze, streaming voxel, recursive and other world realizations |
| Ending continuity policies | 7 | `closed`, `open`, `postgame`, `persistent`, `unwinnable`, `branched`, `looping` |
| Exact-addressable design combinations | 1,570,802,912,571,949,056 | Unique *world + mechanic recipe* tuples; NOT independent playtested games |

The exact indexed recipe count is

```
128 * C(12, 2) * C(15, 10) * 12**10
= 1,570,802,912,571,949,056
```

There are 128 authored worlds. Each has 12 locally relevant mechanics and
15 other domains with 12 mechanics apiece. Each recipe picks two local
mechanics and one from each of ten chosen external domains. It is *not*
a count based on multiplying irrelevant paint colors, audio settings,
difficulty values, or hypothetical yet-to-be-implemented features.

Different recipe tuples are guaranteed by indexed combinatorial unranking.
**They are not guaranteed to be different player experiences.** Full design
novelty, fun, legal clearance and runtime correctness need separate review.
The combinatorial cardinality is not a claim of millions of manually
authored world's foundations, nor evidence of executable mechanics.

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

**Honest maturity statement:** 128 authored laws and 192 mechanic designs
are real additions; the exactly indexed 1.57-quintillion-space is a design
assembly capacity, not the count of verified playable games.
