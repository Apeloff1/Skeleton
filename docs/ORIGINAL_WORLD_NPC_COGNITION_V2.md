# Original Worlds — Cognitive NPC Society (actual implemented v2)

**Status:** Real offline player-facing NPC engine in draft PR #3641.  
**Scope:** One authored original-world product session; bounded 1–32 locally
simulated individuals per turn. Not an LLM, human-equivalent personality,
large-language dialogue synthesis, commercial crowd engine or 100,000
simultaneously embodied world agents.

## Replacement of the first-generation profession-only bots

The first generation supplied twelve real jobs but a fixed work/rest
routine. The new `original_world_npc_cognition_v2.py` owns per-citizen
immutable minds, independent drives, explicit survival priorities,
autobiographical observations, learned work policies, contractual duties,
realistic material movement, civic building crews and accountable
relationship histories. Product turns now call `smart_npc_tick`, and the
world's terrain, NPC bodies and cognitive day must advance together.

Each person keeps a stable body ID, physical grid position, health,
stamina, hunger, inventory, profession and relationship traits.
Individual cognitive state adds bounded curiosity, empathy, discipline,
prudence, temperament, morale, stress, loneliness, active goal, goal
persistence, learned utility adjustments and a sixteen-entry memory
buffer. Their eight temperaments are authored strategy/affect priors,
not merely avatar colors. A deterministic SHA256-derived seeded
personality is stable across saves and replays.

The ten executable goal families include:

- Finite food acquisition, emergency self-feeding and actual health survival
- Fatigue management and recovery
- Bounded memory/perception-based work and physical material delivery
- Contracted resource procurement with real recipient and due quantity
- Physical surveying and targeted geographical investigation
- In-person medical aid with actual resource costs and patient healing
- Friendship and trust formation requiring co-location
- Escrow-backed cooperative building by distinct skilled residents
- Patrol/guard behavior and risk-weighted caution
- Supportive neighborhood presence with different goal duration

**Perception is not omniscience.** Citizens read the current cell and
directly adjacent passable cells. Their individual memory stores real
observations of food, wood, stone and water, with original witness, grid
coordinates, confidence and time. They can pursue remembered locations
via bounded traversable paths, update beliefs after depletion and explore
nearby unknown regions. Recall is fallible (prior resource stock may be
gone), and remote claims never magically extract resources.

## Experience and decision feedback

Each individual has ten bounded learned utility offsets (−12 to +12).
These affect later goal decisions, but cannot override hard survival
needs without actual tradeoffs. Rewards are assigned only for measured
world operations: delivered goods, actual harvesting, successful
treatment, physical construction, real exploration and mutually present
interaction. Blocked plans receive a negative adjustment. Merely
thinking about an objective, rendering an animation, or repeating an
idle turn produces **no** learning reward. Decisions and adjustments
are persisted within the world save and validated on reload.

The implementation is transparent deterministic symbolic/utility
learning—not a trained transformer, gradient-derived deep RL system
or validated model of human preferences.

## Social and intersubjective knowledge

Relationships are typed, directional-identity-safe bond edges with
bounded trust, affinity and reciprocated aid. Citizens must be physically
co-located and actually choose a social/care action to strengthen
a relationship. Loneliness is a live drive; real interaction reduces it,
rather than NPCs accumulating invisible relationship points.

After repeated in-person meetings and sufficient trust, a resident can
pass on a real positive stock observation to another. Retold memories
retain the **original observation date and first-hand witness**, while
confidence decreases with transmission. The recipient can plan a
journey using the report, but cannot falsely certify having personally
seen it. Memories have bounded capacity and do not turn into official
knowledge simply because they are popular.

The player can use `npc interview ID [wood|stone|food|water]` to obtain
a fresh, unused, truly first-hand statement from a nearby person.
Each authorized interview consumes an actual player action and credits
at most one world evidence token. Identical testimony
(person, material, position, observation time) is deduplicated.
Repeat questioning cannot mint unbounded evidence; second-hand
reports are not promoted as independent eyewitness claims.

Statements are saved with a checksummed provenance record. A SHA256
checksum is **not** an authentication signature for adversarial clients:
trusted server authorization and event signatures are future work.

## Economy and truly cooperative infrastructure

Players may commission specific citizens to gather quantities of
food, wood, stone or water. The citizen's cognitive job commitment
persists over multiple turns, but hunger, health and fatigue can
interrupt or reprioritize it. Completed quantity increases only
when a real citizen returns real carried inventory to the depot.
The work contract never generates goods.

The separate `npc project hearth|mill|beacon X Y` command
escrows physical wood and masonry at project creation and requires
the player to pay one action and civic trust. A building exists
**only after distinct skilled builder/engineer residents physically
reach the commissioned site and contribute the specified labor**.

| Project | Wood escrow | Stone escrow | Distinct skilled workers |
| --- | ---: | ---: | ---: |
| Hearth | 2 | 1 | 2 |
| Mill | 1 | 3 | 3 |
| Beacon | 2 | 2 | 3 |

Incomplete projects remain incomplete. The same resident cannot
claim multiple distinct-worker contributions. Cancelled projects
return unused escrow; completed projects cannot be cancelled.
Occupied, inaccessible or hazardous building sites cannot bypass
physical collision. All construction is reflected on the world
map and persistent sparse terrain save.

Cooperation is thus a real causal condition, not a summary claim
that some abstract NPC population has become more skilled.

## Compassion and survival consequences

A hungry citizen can consume actually carried food, a stocked
depot meal, or food from its own physical local tile. All decrease
the corresponding real stock by one. When supplies are absent,
the NPC may pursue remembered food or suffer documented hunger
and eventual declining health. No invisible food respawn exists.

A care-focused NPC must move along passable terrain to reach
a real patient and consume one local warehouse water resource.
That exact patient's health improves, and a witnessed mutual-aid
relationship forms. Resources are consumed once; two characters
cannot receive fictional restorative credit from the same unit.
The NPCs have neither real medical knowledge nor epidemiological
authority: these are game mechanics.

## Studio usage

```bash
# One full world with real cognition and native desktop controls.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox --desktop --save myworld.json

# Inspect one resident's actual mental state and personal work receipts.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox --npc-profile 0

# Commission an order and verify completion after *physical* world ticks.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox --inhabitants 1 \
  --actions-json '[{"layer":"npc","verb":"commission","target":0,"option":"food"},{"layer":"causal","verb":"end_turn"},{"layer":"causal","verb":"end_turn"}]' \
  --npc-report

# Reserve real materials for a shared build and inspect its ledger.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox \
  --actions-json '[{"layer":"npc","verb":"project","option":"hearth","x":0,"y":0}]' \
  --npc-report

# Run adversarial long-horizon scenarios without mock NPC actions.
python -m skeleton.game.generation.original_world_npc_laboratory \
  --scenario food-shortage --turns 24 --population 12
python -m skeleton.game.generation.original_world_npc_laboratory \
  --scenario public-construction --turns 24 --population 12
```

Interactive commands: `minds` for whole local society,
`person 0` for detailed biography; `npc commission 0 food 2`,
`npc cancel 0`, `npc project hearth 0 0`,
`npc cancel_project 0`, `npc council`,
`npc interview 0 food`, `causal end_turn`, `status`.

The native GUI lets the user click visible residents to select
an individual, inspect goals, and offer verifiable interviews
or commissioned food work. The complete game command palette
accepts the same scoped NPC commands.

## Verification: evidence rather than inflated counts

`Original World Atlas` tests exercise independent identity,
individual goals, 16-entry memories, bounded honest perception,
resource-depletion response, health and hunger, commissioned jobs,
two-/three-skilled-worker construction, material escrow/refunds,
social loneliness and relationships, eyewitness interviews,
third-party knowledge confidence, learned goal feedback,
deterministic full replay and complete save migration.
The long-horizon laboratory independently executes five scenarios:
baseline, food shortage, injured community, social isolation and
public construction. It reports actual citizen decisions, mortality,
health, morale, surviving resources, projects, social ties, positive
experience, earned learned-policy adjustments and exact saved-state hash.

In this implementation **one original player session simulates
up to 32 local citizen bodies**. The vast combinatorial game address
space does not multiply that count into an instantiated crowd.
External machine learning, coherent natural language dialogue,
cross-chunk thousands-of-NPC streaming, strategic combat, full kinship,
persistent family lineages, genuine human-level cognition and
multiplayer authoritative audit remain substantial *unimplemented*
products. This is a serious step beyond a job-tag state machine,
not a claim to have finished every future NPC capability.
