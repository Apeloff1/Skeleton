# Original Worlds — playable implementation wave (2026-10-11)

**Status:** Four original-world causal laws are implemented in bounded,
offline, deterministic game simulations on PR #3641. The remaining
1,292 worlds are authored designs, **not** playable builds. Gameplay
here means working text-mode simulation, not completed graphics, voice,
native console binaries, or hyperrealistic physics.

## Run the unified game

```bash
# Solo world with shifting scenery, goals, choices and 34 world action verbs.
python -m skeleton.game.generation.original_world_play_cli \
  --mode campaign --world topology-02 --interactive

# Living community: twelve autonomous NPCs, real jobs, travel, resource
# constraints, personal trust and 15 social actions.
python -m skeleton.game.generation.original_world_play_cli \
  --mode living --world civilization-01 --interactive

# One persistent campaign across four original worlds. Distinct climate,
# civic consequences, maze and quilt remain stored in their own realms.
python -m skeleton.game.generation.original_world_play_cli \
  --mode nexus --interactive

# Bound script, deterministic output, optionally persist to a local save.
python -m skeleton.game.generation.original_world_play_cli \
  --mode nexus --seed three-lanes \
  --actions-json '[{"verb":"weave","amount":2},{"portal":1},{"verb":"end_turn"},{"portal":2},{"verb":"redirect_rain","option":"west","amount":2}]' \
  --save my-world.json --show-map

# Resume using the corresponding mode; save structure is strictly validated.
python -m skeleton.game.generation.original_world_play_cli \
  --mode nexus --load my-world.json --interactive --save my-world.json
```

For one-world use the scripts and interpreter have no dependency beyond the
standard library and the repository's authored world catalogs.

## Four explicitly executable authored world laws

| World ID | Original premise | Implemented behavior |
| --- | --- | --- |
| `topology-02` | Blindside District | Unobserved corridors change each world tick; player observation delays changes; player can anchor expensive changing connections; shortest path always remains possible through the stable connected backbone |
| `ecology-03` | Rain Eaters | Migratory animals redistribute a conserved twelve-unit rainfall budget; agricultural yield and sector recovery respond to the regional balance; player can actively steer herds |
| `civilization-01` | Town of Unfinished Oaths | Players pledge and fulfill resource-costed obligations, earning trust and raising actual civic buildings; unfulfilled promises do not produce free architecture |
| `serenity-05` | The Unfinished Quilt | Resource-costed community textile work strengthens relationships and provides restorative comfort; the project remains indefinitely expandable without a forced completion condition |

Each world has twelve addressable sectors, bounded deterministic initial
ecology, ordinary passages plus changeable connections, finite renewable
resources, local construction, farming, research, social relations, and
a nonterminal chapter/postgame transition.

`original_world_campaign.py` implements 34 selectable player verbs plus
turn advancement. Examples: travel with adjacency checking; observe and
stabilize maze edges; forage, chop, quarry and draw water from actual
sector stocks; sow, irrigate and harvest local crops; eat and recover energy;
craft tools, build and repair; trade with fixed material/coin pricing;
aid, teach, research, vote, promise, fulfill, explore, restore; direct animal
movement and rainfall; create a quilt and persist its consequences.

Verbs are **playable actions**, not 34 fully independent implementations
of every referenced authored mechanic. Some are bounded adaptations of
broader catalog concepts. Complete source-mechanic fidelity needs its own
promotion gate and engine interpretation.

## Resident intelligence is real simulation, not an LLM assertion

`original_world_society.py` and `original_world_living_session.py`
instantiate twelve individually identifiable residents in three villages.
Each resident has a profession, home, current position, energy, health,
morale, personal trust, skill and hunger. Occupations include farming,
forestry, building, healing, scholarship, commerce, scouting, teaching,
diplomacy, weaving, fishing and guardianship.

NPCs commute across the actual current navigable map (one connected edge
per autonomous tick, not instantaneous teleportation). Farmers, fishers,
foresters and builders remove physical food/wood from sectors and allocate
them to village stock, while personal needs consume finite food supplies.
Learning and healthcare modify individual state. Workers cannot produce
materials from already depleted terrain.

Player-resident actions include greeting, sharing food and water,
balanced local trading, skill instruction, care, petitions, donations,
civic project commissions, festivals, dispute mediation, interview,
invitation to join a traveling party, and voluntary dismissal.
A resident must be physically present to communicate; no remote
teleport-contact. Up to two companions may follow traversed paths.

Long-term society state, campaign effects and event receipts can be
saved and replayed. The game uses bounded deterministic rules; this
does not pretend to be an independent artificial general intelligence
or unconstrained learned NPC model.

## Four-world system with conservation

`original_world_nexus.py` keeps all four world states independently.
Only the active traveler has portable inventory. On portal departure,
portable goods and health move to the destination, while the previous
realm's carried inventory is cleared. All world terrain, discovered
sectors, civic promises, built structures, progression and postgame
state persist independently.

Portal use consumes a finite travel charge and traveler energy; crafting
a new charge requires local wood, stone and money. Travel is available at
identified settlement portals in a four-world ring. Other worlds continue
autonomous seasonal development when a local turn advances. We do not
simulate offscreen travelers as if their duplicate bodies were present.

A separate hash-chained nexus history records realm travel and acts.
Save/load checks canonical content digests and validates every nested
world. SHA digests provide reproducible identification and accidental
corruption detection, **not cryptographic authentication against a
malicious save editor**.

## Scenario and platform progression

The era, theology, chronology, theme, visual, comfort and realism
catalog remains separately available through
`world_styling.py` and `world_experience_manifest.py`.
These axes are currently **design manifests**; the playable text-mode
simulator does not promise that changing them has built graphical
assets or genuine physical hyperrealism.

The new game modes are an additive Python reference runtime that can
inform Dragon's native platform compiler. No claim is made of tested
PlayStation, Nintendo, Xbox, ROM, emulator, Windows installer or
portable console execution. Future platform-specific adapters must
lower simulation budgets and preserve critical rules, with provenance
and license checks, before adding a verified support label.

## Executable verification

```bash
python -m pytest -q --noconftest \
  tests/test_original_world_mechanic_atlas.py \
  tests/test_original_world_simulator.py \
  tests/test_original_world_campaign.py \
  tests/test_original_world_campaign_cli.py \
  tests/test_original_world_nexus.py \
  tests/test_original_world_society.py \
  tests/test_original_world_play_cli.py
```

The repository's `Original World Atlas` CI workflow tests every mode
on the exact PR commit, compiles the generation package and runs playable
scripts for all four world-law adapters.

### Honest completion denominators

- Authored worlds: 1,296 / 1,280 target (exceeded).
- Four executable world-law adapters / 1,296 authored world premises
  (approximately **0.31%** of the written world-catalog foundations).
- 34 turn-based action verbs + 15 social verbs. These are playable
  interactions, not a claim that 49 of 712 catalog mechanics have complete
  fidelity; the original abstract eight-rule prototype remains separate.
- Four connected worlds and twelve working simulated NPCs, against an
  eventual much larger platform vision.
- Production-readiness across modern/abandoned native hardware, lifelike
  animation, hyperreal physics, procedural universe-scale terrain, finished
  UI and legal/aesthetic review: **not verified**.

Next high-value implementation domains: original-law compiler with typed
preconditions and effects; mutation-safe streaming terrain; persistent
NPC societies across realms; world-level quests with divergent outcomes;
era-realization and theological causal adapters; budgeted physics/render
capability tiers; platform-native playable artifacts.
