# Advanced Game Studio — 128-NPC Fair Physical Streaming

Date: 2026-10-12 (Europe/Oslo). Draft pending exact-head CI.
Dependency stack: unified NPC world #3686, streaming #3689, timeline
#3690, fast source forks #3692 and history index #3694.

## Real bounded physical NPC world

The original 21x21 or 35x35 chunked CPU reference world supports up to
128 persistent distinct original NPCs. Four are source-authored and the
others are deterministic original residents generated from the source seed,
each tagged with honest original provenance. No character is presented
as copied or imported from a commercial title.

The detailed simulation limit is distinct from the population size:
4–32 actual detailed NPC update slots per tick. Deferred NPCs retain exact
last physical position and cannot teleport, witness events, cause hidden
quests or claim unperformed activity. Source-line-of-sight still uses the
full original expanded map geometry.

## Two deterministic fidelity policies

- nearest: unchanged physically closest priority with stable source ID ties.
- fair: eligible NPCs gain progressively more priority after each detailed
  turn they miss. Actors outside the current loaded chunks remain deferred
  and never receive pretend detailed updates.

Each actor records actual tile steps, detailed turns, deferred turns,
current and longest deferral streak, and deferred turns during which the
actor was inside a loaded eligible chunk. The world scheduler records
detailed updates, deferred turns, physical movements, eligible deferred
turns and largest historical deferral streak.

For N actors across T ticks, detailed updates plus deferred actor turns
must equal N multiplied by T. An individual actor cannot move more tiles
than its actual detailed updates. These are verifiable work counters, not
inferred performance or GPU hardware benchmarks.

## Practical original game capability

Existing original physical harvesting, firsthand eyewitness events, finite
resource payments, real speaker trust and earned quest consequences remain
source-verified. Studio allows 8/16/24/32/64/96/128 persistent residents,
detailed NPC budgets up to 32 and selection of nearest vs fair policies.
Every fairness decision is replayable from exact source scene, seed and
registered game actions, without arbitrary user-provided state injection.

New cross-OS tests execute 128 real NPC identities on both world sizes,
check uniqueness and occupancy, enforce one-tile physical moves, compare
actual detailed/deferred work, and reject forged counters, source identities
and unknown policies. Original timeline bookmarks and branch continuation
remain source-bound under the new typed options.

## Time-stamped change history

2026-10-12 — Persistent original NPC count increased 32 to 128
(expanded actually instantiated social world population).

2026-10-12 — Detailed actor budget increased 16 to 32
(expanded honest high-fidelity simulation options).

2026-10-12 — Implemented deterministic deferral-aware scheduler policy
(spreads high-detail attention within physically eligible population).

2026-10-12 — Added full actor and aggregate deferred-work accounting
(prevents fabricated mass simulation and hidden progress claims).

2026-10-12 — Added Studio controls, strict original option validation,
source-forgery tests and exact-head Ubuntu/Windows CI
(makes expanded gameplay auditable).

## Limits

Not every resident is fully detailed on every turn. Fairness cannot
guarantee service for an actor outside eligible chunks and is not a
starvation-free proof for arbitrary maps. This milestone does not certify
native Godot execution, million-NPC games, multi-world memory import,
commercial release, or automatic AI weight improvement. PR stack remains
draft and unmerged until integration validation.


## Exact per-turn fidelity custody (added 2026-10-12)

The source event frame now records an explicit LOD fidelity receipt on
**every turn**, not only a final counter. It includes each selected original
physical NPC identity, how many bodies received actual schedule updates, how
many were deferred, how many nearby eligible residents remained unserved,
the actual loaded chunks, cumulative maximum deferral streak, and the
zero-phantom-work count.

Runtime conservation: actually_detailed + deferred = physical_actor_count
on every frame, with no duplicate selected actor IDs. This is a source
evidence constraint rather than a rendering estimate.

The trusted fast-fork engine uses the identical receipt calculation. Its
branch must equal complete from-genesis canonical game history, including
per-turn NPC selection, physical movement and deferred work. Source
reexecution rejects altered cohort IDs or unearned simulation credits.

The Studio exposes each turn's factual selected/deferred work and the
source chain digest. This distinguishes catalog existence from actual
detailed execution.

2026-10-12 — Added per-turn original actor selection and deferral custody
(improved deterministic fairness scrutiny and work accounting).

2026-10-12 — Propagated exact fidelity receipts to optimized fast forks
(prevents a second replay pathway from omitting actual simulated work).


## Physical occupant collision exclusion (added 2026-10-12)

The source-world expanded spawn planner now reserves the player's actual
starting cell as well as every NPC's cell. The actor scheduler pathfinder
reserves the player's CURRENT tile before each NPC one-tile step. A player
movement command also refuses to enter an embodied resident's tile before
it spends stamina. Post-schedule collision checks reject any NPC overlapping
the player or another resident. This applies to both 21x21 and 35x35
environments, all configured citizen counts and either LOD policy.

Tests exercise multiple seeds with 128 residents in both world sizes and
perform a deliberately invalid player-into-NPC move against the real movement
rule. Success means the command is rejected with no resource debit.

2026-10-12 — Prevented NPC/player occupancy conflicts in spawning,
pathfinding and movement (improved physical-world consistency).


## Preservation of authored gameplay routes (October 12, 2026)

Additional original citizens spawn outside the central, reviewed quest
source chunk. This prevents procedural population expansion from silently
placing a physical body on the original quest route or objective anchors.
NPC scheduling treats the source site's interaction cell as a reserved
player-accessible anchor: residents can approach the site but cannot occupy
its exact interaction tile. Player/NPC collision exclusion remains strict
and the movement engine does not teleport either body.

Targeted integration tests execute the *full, original witnessed
harvest -> firsthand testimony -> paid support -> five physical repairs ->
earned restoration* sequence with 16, 64, and 128 citizens on both the
21x21 and 35x35 world geometries. The source identity, actual NPC testimony,
material costs and verified conclusion are preserved, rather than weakening
the collision rule to make older tests green.

2026-10-12 — Preserved original authoring/playability under high population
(fixed collision-safe provenance placement and unblocked quest interaction
anchors; adds full game regression coverage across six population/map pairs).
