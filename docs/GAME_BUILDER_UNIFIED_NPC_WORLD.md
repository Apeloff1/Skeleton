# Advanced Game Studio — Original Unified NPC World Authority

Date: 2026-10-12 (Europe/Oslo). Status: **draft, awaiting exact-head CI**.

## Capability milestone: from role bridges to one physically authoritative world

The previous three-engine narrative bridge used separate geographical scenes,
clocks and player locations. This milestone implements an entirely new, playable
reference world with **one actual physical NPC body per source identity**,
one tick authority, one shared player location, a canonical 7×7 walkable map,
one local resource ledger and one ordered causal event journal.

It retains source-referenced design roles from original Dialogue, NPC Society
and Quest Director scenes. It does not falsely claim to synchronize those
older, independent runtimes in the same time and space. It runs actual new
unified gameplay using their authored source, so there is no second position
or cloned social state for a given citizen in the new engine.

### Mechanically meaningful consequences

A player moves one adjacent walkable tile at a time, paying finite stamina.
Citizens move one real tile toward authored work/home goals per world tick via
obstacle-aware breadth-first search. They may not overlap one another and
their movement is recorded with pre/post cell and exact clock. No teleporting,
NPC omnipresence or fake schedules.

Original physical actions at a world site consume material and/or stamina and
change site stock, integrity and aid totals. A site event acquires exact ID,
timestamp, physical source actor and directly observing citizens using sight
radius plus obstacles. The event remains visible in the immutable ledger even
when a resident's bounded personal memory changes.

A real player must physically encounter that **same** NPC to hear testimony.
Firsthand statements link to witnessed world event IDs; generic conversation
never becomes false eyewitness evidence. Paid social support consumes influence
and supplies in this very same state, increases genuine resident trust/bond and
locks an actual source quest branch. A site must receive every configured
material follow-up action before completion. Earned quest rewards and
optional retirement are source-grounded. An additional optional civic
council cannot be claimed without two distinct real firsthand speakers.

### Single-authority event ordering

Each action executes these phases in one deterministic order:

1. Player action changes location/resources or real dialogue/quest source.
2. Physical witness evidence is emitted to the single world ledger.
3. Residents move one allowed tile in the common schedule and clock.
4. Complete state and the preceding receipt hash are written to a chained,
   independently replayable authoritative frame.

Every frame includes the original command, before/after state digests, actor
movement, event receipts, shared tick and ordered phase labels. The full
receipt is reconstructed from three source documents, typed options and all
player actions. A client-supplied state is never used as execution input.

### Scope and bounded performance

- 7×7 map with up to four physically embodied NPCs in this first reference.
- Source-alias metadata maps playable dialogue speakers and NPC citizens
  explicitly; it does not claim hundreds of absent residents are modeled.
- Up to 96 original commands, finite quest events and bounded serialized
  state. NPCs have real speech patience, social influence, bonds, memory
  lifetime and home/work movement; chronology and eyewitness memory are
  separately traceable.
- Deterministic CPU reference gameplay: not a GPU-native game, mass
  simulation or actual ML training. No model weights change.
- Signed-looking checksums are **content hashes**, not private-key
  cryptographic signatures or a public ownership attestation.

### Code, app and verification

- Single-world source: skeleton/ai/game_builder/advanced_unified_npc_world.py
- Adversarial game tests: tests/test_game_builder_unified_npc_world.py
- CLI: unified-npc-world and verify-unified-npc-world
- Token-protected Studio JSON routes: /api/unified-npc-world and
  /api/unified-npc-world-verify; no source project mutation
- Studio Dialogue screen: editable original world actions with a readable
  single-world actor clock, positions, states, personal memories, real quest
  effects and frame-by-frame movement receipts
- Cross-platform GitHub CI: game-builder-unified-npc-world.yml, exact head,
  Ubuntu and Windows, source/CLI/server syntax, real play, tamper attempts and
  four seeded deterministic campaigns

### Timestamped improvement history

2026-10-12 — Created unified world map, actor identity and tick authority
(replaces disconnected actor positions with one physical source of truth).

2026-10-12 — Added scheduled one-tile routefinding with occupancy
(prevents resident teleporting and positional collisions).

2026-10-12 — Added physically witnessed world event ledger and independent
firsthand statements (prevents rumor-to-eyewitness promotion).

2026-10-12 — Added finite assistance, social cost, quest followup, earned
outcome and optional retirement (real game consequences, not synthetic scores).

2026-10-12 — Added exact replay and comprehensive tamper, source, spatial,
time and resource regressions (reviewable historical state integrity).

2026-10-12 — Added Studio and CLI interaction plus Ubuntu/Windows native
operating-system Python checks (actual input/replay on two OS environments,
not native Godot certification).

### Remaining future milestones

- Multi-chunk original common world beyond 7×7 and many embodied NPCs with
  bounded LOD and path/scheduling integration.
- Unified world features migrated into an independent Godot execution
  backend, tested with real native full-state parity.
- Event subscriptions, durable savegame interoperability and source-versioned
  migration across the three older reference engine formats.
- Conflict resolution for multi-user editing and AI-created rules; safety
  gates before model-weight learning or publication.

This PR is stacked on the draft social-fusion PR #3684 and its prior parents.
No merge to main or production-ready native engine is claimed.
