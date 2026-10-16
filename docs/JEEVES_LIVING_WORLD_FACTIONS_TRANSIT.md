# Jeeves living-world production milestone: factions, conditional labyrinths and Dragon evidence

These milestones add genuine typed, replayable game state. Travel is no longer
limited to moving along every original scene link with no consequences. A
reviewed Director campaign can include earned passage permissions, competing
guilds, irreversible world discoveries and original transport networks.

The authoritative game-state machine is still the Python Director runtime.
Godot consumes its approved scene graph, media, snapshots and action receipts.
Neither a generated blueprint nor a successful Python test alone proves
professional art, literary quality, a shipping installer or native playthrough.

## 1. Why this is an engine milestone, not a static route planner

The core implementation changes
`skeleton/ai/game_builder/quest_scene_engine.py` and adds
`skeleton/ai/game_builder/quest_world_dynamics.py`.

The typed, strictly compiled `WorldDynamics` block is an OPTIONAL addition
to the original `DirectorWorld` schema. For any legacy world that lacks it:

- the authored world payload stays unchanged;
- the SHA-256 world identity stays unchanged;
- the initial and persisted state payload stays unchanged;
- the action journal hash and its replay rules stay unchanged;
- the original travel/use/wait semantics remain in effect.

No bulk database migration and no destructive rewrite of existing projects.

For an explicitly approved living world, new immutable state includes faction
standing, permanently earned world flags, fired influence receipts and
per-passage visit/use counts. They are part of the existing canonical state
digest, journal receipts, session recovery and deterministic replay.

### What the engine actually simulates

| Primitive | Runtime behavior |
|---|---|
| Guarded walking link | Ordinary `travel:scene_id` is not offered until its explicit requirements hold |
| Original transport route | A `transit:route_id` action is offered only at its authored source or permitted reverse destination |
| Fare/resource consumption | A passage can require and consume an actually acquired original-game inventory item |
| Required story milestone | Passage opens only after a real completed quest |
| Required narrative consequence | Passage checks an actually earned story outcome flag |
| Authored world event | Passage checks a permanently earned and journal-replayed world flag |
| Forbidden outcome or world flag | Route can close after a story choice or irreversible event |
| Faction standing threshold | Route can admit or exclude the player based on actual, bounded reputation |
| Real action influence | Performing a legal scene interaction may raise/lower faction reputation and fire an event |
| Real quest-result influence | Completing an authored quest with a specific outcome may alter standing and permanently change world state |
| Transport cost | Ferry/rail/boat/portal/etc advances the canonical turn clock according to a declared integer cost |
| Optional one-way transit | Authored travel is directed unless bidirectional travel is explicitly permitted |
| Save integrity | Every turn's full world snapshot changes the cryptographic canonical state hash |

Transport modes supported by the typed authoring schema: foot, rail, ferry,
airship, portal, elevator, shuttle, taxi, boat, plane, mount, teleporter,
space and underwater. These are gameplay **logic modes**, not claims that
3D vehicles, water physics or exterior scenery have been rendered.

The new influence rules accept only recognized scene affordance identities or
actual quest-result identities. They cannot execute arbitrary Python scripts,
run shell commands, call remote APIs, write arbitrary game files or manufacture
off-world resources.

## 2. Create a denser original game in the Jeeves CLI

Begin with an existing explicitly approved Director source. Build a living
world draft **without writing or replacing** the original game:

```bash
python -m skeleton dev game jeeves director-dynamics-design \
  --project ./original_game \
  --source design/director_campaign_source.json \
  --intensity 5
```

The preview gives a stable `design_sha256`, source identity, complete
`director_world` candidate, dynamic-world source identity and a structural
audit. It requires no new external models, no licensed content, and no secret.

Intensity controls how much of the optional original transport system is
authored in this single generation pass. Level 1 introduces guild standing,
earned events, a ferry and an unlockable charter portal. Higher tiers add more
eligible gated walking shortcuts, a regional shuttle, a ticketed airship,
elevator passage and an underwater exploration route where the original graph
has the necessary scenes and item producers.

All generated routes have original stable IDs and are checked against actual
scene, item, faction and quest identities before publication.

After inspecting **the full candidate**, publish an independently named file
with an explicit content approval:

```bash
python -m skeleton dev game jeeves director-dynamics-publish \
  --project ./original_game \
  --source design/director_campaign_source.json \
  --intensity 5 \
  --approve <exact_design_sha256>
```

This creates a file named `design/director_dynamic_<digest>.json`. It will
not overwrite the original campaign, an existing game, earlier model evidence,
or a prior output with the same name. The original game source remains usable.

A reviewed dynamic source can then begin an ordinary persistent session:

```bash
python -m skeleton dev game jeeves director-session-begin \
  --project ./original_game \
  --source design/director_dynamic_<digest>.json \
  --session frontier_trial
```

All future actions and state recovery use the existing Director commands and
cryptographically linked receipts. The project can also be forked to explore
alternate morality and faction paths with the preexisting non-destructive
`director-session-fork` command.

## 3. Write specific authored conditions rather than a scripted illusion

The `director_world.dynamics` block has an exact allowlisted JSON schema.
An abbreviated example showing the conceptual structure is below; the real
publisher generates all required fields and rejects missing properties.

```json
{
  "schema": "skeleton.game_builder.world_dynamics.v1",
  "factions": [
    {
      "key": "harbor_council",
      "name": "The Harbor Council",
      "starting_standing": 0
    }
  ],
  "gates": [
    {
      "source": "scene_01",
      "destination": "scene_02",
      "label": "Chartered bridge",
      "requirements": {
        "items": [],
        "flags": [],
        "quests": [],
        "world_flags": ["harbor_charter"],
        "standings": [
          {
            "faction": "harbor_council",
            "at_least": 30,
            "at_most": 1000
          }
        ],
        "forbidden_flags": [],
        "forbidden_world_flags": []
      }
    }
  ],
  "passages": [
    {
      "key": "public_ferry",
      "source": "scene_01",
      "destination": "scene_02",
      "mode": "ferry",
      "name": "The Council Ferry",
      "cost_turns": 4,
      "requirements": {
        "items": [],
        "flags": [],
        "quests": [],
        "world_flags": [],
        "standings": [],
        "forbidden_flags": [],
        "forbidden_world_flags": []
      },
      "consume_item": null,
      "grant_world_flag": "harbor_charter",
      "reputation_change": [["harbor_council", 30]],
      "bidirectional": true
    }
  ],
  "influences": []
}
```

A passenger can board this ferry and actually earn reputation plus the world
charter. On return, the once-locked foot bridge becomes an actual legal
`travel:scene_02` action. None of this requires untracked GUI booleans or
manually forcing a quest reward. The journal records the entire causal state.

**Design responsibility:** A generated unlock can be mechanically coherent
while being dramatically inappropriate. Review its placement, story logic,
economics, tone, difficulty and final availability before making it canon.

## 4. Dynamic multi-path labyrinth navigation

```bash
python -m skeleton dev game jeeves director-route \
  --project ./original_game \
  --session frontier_trial \
  --destination scene_06 \
  --route-profile scenic \
  --alternatives 6
```

The upgraded route solver does not simply treat every map edge as open. It
explores actual canonical state transitions and observes required items, fares,
earned flags, reputation, transport travel time and competing routes. It
supports the existing fastest, scenic, quiet, novel and quest-oriented
policies.

The route report includes a fully ordered action witness and each step's
before/after state SHA-256, transport type, ticket consumption, time cost,
resulting faction standing, resulting world flags, inventory, destination,
distinct regions and a source/head-bound route hash.

It also computes a separate minimum-hop reference using real legal actions.
This reference is not a static straight-line distance between map nodes and
is not a 3D pathfinding or physics benchmark.

A route planner does not execute moves. A selected proposed first action
still goes through the same authoritative journal lock and optimistic
concurrency requirements. The Godot map shows original transit corridors in
a different style and marks locked walking gates visibly. Clicking the map
only requests a plan. Manual player interaction authorizes each action.

If an expensive search reaches its per-query memory/expansion budget, the
report explicitly marks incomplete evidence. Lack of a path under current
permissions does NOT mean the story cannot unlock one later.

## 5. Adversarial dynamic-world structural audit

```bash
python -m skeleton dev game jeeves director-dynamics-audit \
  --project ./original_game \
  --source design/director_dynamic_<digest>.json
```

The audit enumerates every typed guard and transport with its initial
availability, standing thresholds, actual item producers, producible
world flags, quest outcomes, initially unreachable quest locations,
possible no-return zones, gates without an alternative walking bypass,
unique consumable fare risks, and faction effects with no authored source.

The report creates **review work**, not false completed-game signoffs. A
faction may be inaccessible by design; a one-way ferry may be the centerpiece
of a survival quest; a scenic dead end may be important worldbuilding.
Conversely, a valid scene graph cannot by itself prove there is no stateful
softlock in every possible quest and inventory sequence.

The Jeeves production board includes a separate living-world assurance
section, deliberately distinguishing implemented game logic and risks from
unverified native animation, full state-space proof or consumer QA.

## 6. Persistent narrative consequences and screenplay continuity

```bash
python -m skeleton dev game jeeves director-causality \
  --project ./original_game --session frontier_trial \
  --page 1 --page-size 100

python -m skeleton dev game jeeves director-story-contrast \
  --project ./original_game --session frontier_trial \
  --other-session different_allegiance
```

The causality recorder now links real world-event flags, faction standing
changes, transport modes and ticket/item changes back to the exact action
sequence that produced them. It still checks quest prerequisites, stage
methods, item inventory and persistent canon outcomes. An alternate-path
contrast now detects differing world flags and faction standings even when
both players completed the same main quest.

This supports more meticulous continuity work, while leaving artistic
evaluation of character voice and screenplay craft to separate signoff.

## 7. Dragon's living-world research and training boundaries

```bash
python -m skeleton dev game jeeves dragon-world-study \
  --project ./original_game --session frontier_trial

# After reviewing the exact study_sha256 returned above:
python -m skeleton dev game jeeves dragon-world-study \
  --project ./original_game --session frontier_trial \
  --approve <study_sha256>

python -m skeleton dev game jeeves dragon-world-contrast \
  --project ./original_game --session frontier_trial \
  --other-session different_allegiance
```

The Dragon companion independently verifies journal receipts and measures
real faction changes, unlocked events, consumed tickets, transport usage,
travel modes, quest results and narrative consequences. Research packets
are content-addressed, create-only, manually approved and source-bound.

Dragon's existing empirical action-policy learner now conditions its small
replay-trained micro-model on inventory, faction standing, story flags and
world flags. This prevents a model trained in a post-unlock scene from
blindly reusing pre-unlock advice merely because the player stands in the
same physical scene.

The older Dragon navigation research separately counts transport journeys
rather than treating a portal as many impossible on-foot steps or treating
ferry rides as idle waiting. Neither system invents user satisfaction data.

**Important distinction:** This work supplies deterministic learning input,
an existing empirical micro-model pipeline, and actual transition receipts.
It does NOT claim transformer checkpoint training, visual learned weights,
successful Godot physics/rendering, data-source licensing proof, or
independent human playtesting.

## 8. Godot source and user-facing gameplay

The native export advances to `-live-v6`, preserving all earlier generated
`-live-v1` through `-live-v5` preview projects.

```bash
python -m skeleton dev game jeeves director-atlas-export \
  --project ./original_game \
  --source design/director_dynamic_<digest>.json

python -m skeleton dev game jeeves director-atlas-verify \
  --project ./original_game \
  --source design/director_dynamic_<digest>.json
```

The bundled project includes the existing original media, environment
animation, authenticated game client and directional minimap, enhanced with
transit edges, locked-gate indicators and user-visible faction/world changes.

The interface exposes the true source-backed transport action rather than
creating an insecure client-side shortcut. A character may arrive in an
animated environment with a different ambient sound, but the vehicle or
portal does not yet have a finished art-directed animated vehicle sequence.

## 9. Complete authored campaign proofs, without static-gate cheating

An opt-in, source-bound end-to-end simulation now executes **complete** authored
quest campaigns through the actual dynamic world-state machine. Earlier
campaign witness generation assumed every authored scene link was freely
walkable. It can now find legal transport/faction-state routes, pay actual
fares, earn real world flags and use only currently admitted travel actions.
It never hands itself a key, fakes an earned event or bypasses a locked gate.

```bash
python -m skeleton dev game jeeves director-dynamics-playthrough \
  --project ./original_game \
  --source design/director_dynamic_<digest>.json \
  --routes 4 --include-optional
```

The command runs each strategy and performs **another independent action-by-
action replay**, verifying the initial and final state hashes, every 256-action
segment receipt, full stage/quest completion, faction history, consumed
resources, all transport entries, permanent events, and actual narrative
outcomes. It also reports distinct end-state/outcome groups, quest-stage
checkpoints, and bounded human-readable highlights while counting the full
history.

When an authored world cannot be completed under the chosen policy, the
report names that attempted strategy and error instead of claiming a
passing game. Bounded per-query search exhaustion is not treated as proof
that a world is permanently impossible. **No live game save is created** by
the pure witness verifier; this remains Python logic E2E, not a native Godot
or user-played release certification.

The native map distinguishes source-defined transport edges, visibly
blocked walking exits and selected legal transit routes. Green route hints
mean a transport is currently permitted by the live Director state; purple
hints are declarations, not guaranteed current permissions. All actual
controller choices still cross the canonical server.

Engine-binding contract previews now include exact transit action IDs,
directed source/destination, travel duration, fare and standing conditions,
and conditional walking gates. Such declarations **never** bypass a
per-action runtime permission check.

## 10. Special-purpose regressions without global CI congestion

```bash
python -m unittest tests.test_jeeves_director_dynamic_world
python -m unittest tests.test_jeeves_director_labyrinth_causality
python -m unittest tests.test_jeeves_director_labyrinth_causality
python -m unittest tests.test_jeeves_director_branch_policy
python -m unittest tests.test_jeeves_director_media_e2e
```

The focused dynamic-world tests cover old-world digest compatibility,
initially locked passage rejection, ferry-based faction unlocks,
persistent route use counts, source tamper rejection, exact author approval,
create-only publication, real journal replay, state-bound routes,
unsigned transport rejection, Dragon evidence stability, alternate-world
comparison and source-verified Godot exports.

Actual Godot and complete Python test execution must still be run before
production readiness can be certified. No new automatic GitHub workflow or
compulsory merge-gate job is added by these milestones.

## 11. Remaining production-standard gaps

A pioneering completed game builder still needs original high-fidelity
assets, advanced NPC locomotion and conversation with original performance
and continuity, richer state-dependent economy/combat/crafting,
interior/exterior physical traversal, controller-specific native gameplay
QA, motor accessibility support, fully timed original vehicle cinematics,
original scored/adaptive music, tested save migrations and complete
start-to-ending native visual playthroughs.

Dragon additionally needs legally approved evidence sets, true production
checkpoint fine-tuning and held-out evaluation, resource-aware training,
regression scoring and versioned weight promotion gates. This slice does not
certify or claim any of those unfinished capabilities.
