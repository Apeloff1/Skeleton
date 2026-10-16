# Jeeves Labyrinth, Canon Causality and Dragon Navigation Evidence

This slice introduces real, replay-verified pathfinding and world topology
checks, page-safe narrative-causality receipts, and source-bound Dragon studies
of operator-selected travel. It is *not* a new engine replacing the canonical
Director simulator or an automatic claim of Hollywood writing.

The goal is to turn dense worlds, unconventional routes, alternate endings and
long story histories into systems Jeeves and the player can actually inspect.

## 1. Navigate an actual original game labyrinth

An approved game source and a started Director session are required.

```bash
# Explain reachability of the entire authored directed world graph
python -m skeleton dev game jeeves director-topology \
  --project ./original_game --source design/director_campaign_source.json

# Find up to five alternatives to an actual reachable scene
python -m skeleton dev game jeeves director-route \
  --project ./original_game --session hero_a \
  --destination scene_03 --route-profile scenic --alternatives 5

# Or let Jeeves find an active authored quest objective
python -m skeleton dev game jeeves director-route \
  --project ./original_game --session hero_a --route-profile quest
```

Profiles are `fastest`, `scenic`, `quiet`, `novel` and `quest`.
The route policy is a deterministic, positive-cost preference over **real
Director scene links**, not a claim of physical scenery/terrain analysis.
`novel` uses replayed prior scene visits; `quest` uses actually active stage
locations after checking prerequisite quests. Every proposed travel step is
executed **in memory** through Director's typed `available_director_actions`
and `director_step`; the actual player journal is unchanged.

The route includes the full ordered sequence, projected ending state, session
head SHA-256, original source SHA-256, distinct regions, unvisited areas and
shortest-hop comparison. A change to game progress invalidates the plan, so
never treat an old suggestion as an action authorization. The native Godot
client has a **Find quest route** button and asks the player before executing
the suggested first movement.

This is a bounded *per-query* search of the candidate frontier with a
linear-time BFS fallback. It never claims to enumerate all possible labyrinth
paths, and the search budget is **not** a lifetime cap on game projects,
sessions, authored worlds, or training loops.

The topology report distinguishes one-way links, dead ends, disconnected
regions, return-to-start reachability, and quest stages inaccessible from
the opening location. The Jeeves production board surfaces the same structural
risks without asserting a creative-quality pass.

## 2. Replay the causal history of a long-form story

```bash
python -m skeleton dev game jeeves director-causality \
  --project ./original_game --session hero_a --page 1 --page-size 100

python -m skeleton dev game jeeves director-story-contrast \
  --project ./original_game --session hero_a --other-session alternate_ending
```

The causal ledger replays the full session against **exact canonical world and
journal evidence**, with append-only causal state checks. It inspects:

- Real interactions, scene travel, turn chronology and inventoried resources.
- Quest dependency precedence, stage completions and outcome methods.
- Flags associated with actual player choices, including when they arose.
- Authored cast appearances and the ordered scenes in which those events ran.
- Unfinished quest stages and their still-missing prerequisite quests.
- Differing outcomes across two sessions, with the first different action.

Only the requested evidence page is returned, while the full session is
verified. This does not shorten the **stored game journal**, impose an artificial
story chapter limit or silently drop a completed route. The summary is hashed
and bound to the live head; it must be recomputed after game actions change.

Typed replay can prove causal integrity. It cannot, on its own, objectively
certify literary voice, originality, emotional depth or actor-performance
quality. Those must be reviewed independently.

## 3. Dragon learns from verified routes without mislabeling exploration

```bash
python -m skeleton dev game jeeves dragon-navigation-study \
  --project ./original_game --session hero_a

# After reviewing the exact study_sha256:
python -m skeleton dev game jeeves dragon-navigation-study \
  --project ./original_game --session hero_a \
  --approve <study_sha256>
```

Dragon replays the entire session again and compares real travel between
successive interactions with the shortest authored route. It collects
successful scene visits, meanders and avoidable *relative hops*, plus a
bounded top-20 set of the most divergent travel sequences. Long session
counts remain complete; only how much verbose detail is returned is bounded.

A scenic detour may be a good game-design feature or a deliberate player
choice. Dragon therefore does **not** infer dissatisfaction, user tastes, or
hidden game footage from distance measurements. The approved, create-only
research receipt is placed in `.jeeves/dragon_replay_candidates/`. No
transformer checkpoint or production weights are modified by this operation.

## 4. Specialized verification and realistic scope

```bash
python -m unittest tests.test_jeeves_director_labyrinth_causality
python -m unittest tests.test_jeeves_director_media_e2e
python -m unittest tests.test_jeeves_director_branch_policy
```

Tests focus on actual typed Director movement, route state equality and
source drift, topology, paginated causal results, divergent branches,
Dragon evidence approval, and a local authenticated HTTP request from a
Godot-compatible navigation client.

This development pass adds **no repository-wide CI workflow or compulsory
merge gate**. Run the dedicated tests and a Godot 4 startup/full visual
playthrough on the installed build before signing native gameplay readiness.
The work is currently intra-world routing across approved authored scenes:
interplanetary transport, nested worlds, dynamic NPC social simulation,
high-fidelity production art and production checkpoint training remain
separate future engine milestones.
