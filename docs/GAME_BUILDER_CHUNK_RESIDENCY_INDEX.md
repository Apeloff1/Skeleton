# Original Game Studio — Physical NPC Chunk Residency Index

Date: 2026-10-12 (Europe/Oslo). Status: draft until exact-head tests.
Parent: #3695 (128-body fair NPC simulation), #3694 (provenance),
#3692 (verified fast forks), #3690 (source histories) and #3689 (chunks).

## Real capability: inspect original physically instantiated citizens

This milestone implements a source-authenticated spatial residency table for
actual 21×21 and 35×35 original game worlds. The index enumerates **every
physically instantiated resident, exactly once**, by deterministic
chunk coordinate, original NPC identity, physical tile and source provenance.
It also preserves actual detailed/deferred tick counts.

The index is built only after independently replaying the original
CPU reference game using its reviewed source scenes, typed settings,
seed, full action history, and bound LOD policy. A hash without the real
original game is never treated as authority.

Each physical chunk has an explicit residency bucket, including empty
chunks. The index contains the source-game digest, action head, world tick,
actual player tile, physical population count, true detailed work, deferred
work, and all per-turn detail cohort proofs.

## Genuine bounded chunk lookups

Callers can select a real chunk coordinate and a neighborhood radius
of zero or one, selecting one or nine (less at map edges) original
physical chunks. Query execution enumerates only the actual chosen
bucket entries, not the entire world actor table, then sorts matching
citizens by their real Manhattan distance from the player and stable
source identity.

Source-backed filters distinguish physically instantiated residents
actually scheduled for detail on the **last world tick** from residents
whose detailed simulation was deferred. Queries also support an exact
original actor ID, stable result pages and bounded offsets/limits.

The result includes the number of actual candidate residents examined
versus the total population, the chunk IDs consulted and the exact
historical world source head. This measures *candidate scan scope*,
not hardware execution speed, which has not been benchmarked.

## Cross-chunk movement, chronology and conservation

The original game action trace is inspected for actual one-tile
NPC movements that cross chunk boundaries. The index preserves
true from/to cells, from/to chunk coordinates, tick, original actor ID
and source receipt head. Movement is not invented for deferred cohorts.

Every per-turn source LOD receipt is bound to its original game source
frame. Total true detailed updates, deferred actor turns and physical
moves must equal the original authoritative scheduler totals exactly.
A live actor cannot share a physical tile with another actor, an authored
obstacle or the player's actual location.

This is a snapshot index of a **real finished game transcript**.
It does not claim to maintain an incremental database inside the
running engine or persist a native game-world chunk file with O(1)
restore. Its expensive untrusted import path deliberately rebuilds
from original source to avoid saved-state forgery.

## Source and operator trust boundaries

- A client must provide an independently reconstructible original game
  receipt. It is reexecuted and checked before an index is emitted.
- An externally returned or uploaded residency index is itself
  reconstructed and compared byte-for-byte against original source,
  including actor tile, exact source identity, movement, clock and LOD.
- An untrusted neighborhood query independently verifies the index and
  reproduces the selected buckets and pages before approval.
- Forged NPC bodies, duplicate IDs, added offscreen action receipts,
  altered actor positions, modified source heads, false hardware or
  AI-weight improvement claims are rejected.
- Content-address hashes provide mutation evidence, **not
  cryptographic author signatures** or an assertion of release readiness.
- The Studio endpoints require its existing operator token and do not
  write to project source files or touch model weights.

## Actual integration points

Game index:
  skeleton/ai/game_builder/advanced_chunk_residency_index.py

Adversarial and integration tests:
  tests/test_game_builder_chunk_residency_index.py

Offline CLI:
  index-original-npc-chunks
  verify-original-npc-chunks
  query-original-npc-chunks
  verify-original-npc-chunk-query

Authenticated local Studio routes:
  /api/index-original-npc-chunks
  /api/verify-original-npc-chunks
  /api/query-original-npc-chunks
  /api/verify-original-npc-chunk-query

Visual Studio:
  Chunk Residency Index directly beside NPC History Index.
  Run actual original streamed world, build reviewed physical index,
  select exact chunk x/y, neighborhood radius and detail mode,
  and page through independently replayed original body positions.

Exact-head Ubuntu/Windows workflow:
  .github/workflows/game-builder-chunk-residency-index.yml

## Dated 2026-10-12 improvement ledger

- Built source-bound physical residency index (makes original
  residents spatially addressable by precise world chunk rather than
  reexamining an undifferentiated population listing).
- Indexed actual cross-chunk movement with full action-chain receipts
  (makes player-facing world navigation and source scrutiny auditable).
- Preserved per-turn exact detail selection and deferred-work evidence
  (prevents claims that unseen residents ran full simulation).
- Added bounded candidate-only chunk searches, identity filters,
  active/deferred modes, paginated neighbor inspection and counts
  (supports larger populations without unlimited result output).
- Added authenticated Studio and offline CLI, adversarial tamper
  tests, and exact-head Ubuntu/Windows CI (independent source replay
  remains authoritative).
- Reconciled the inherited source-world population regression:
  **33 original residents are now valid**, while 129 is rejected
  under the updated hard maximum (fixes obsolete test threshold).

## Remaining future milestones

A true production streaming engine needs incremental actor/chunk
residency updates during the simulation, spatially indexed collision
and eyewitness queries with independently tested asymptotic behavior,
durable crash-safe saves, real hardware/memory benchmarks and native
Godot execution. This milestone is deliberately a source-authenticated
reference index, not the completed native game engine.

Both this PR and its stacked parent remain drafts; there is no
automatic merge to main, model training or hardware certification.
