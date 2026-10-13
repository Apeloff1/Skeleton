# Original Game Studio — Historical Physical NPC Spatial Lens

Date: October 12, 2026 (Europe/Oslo). State: draft, exact-head CI required.
Stack: physical 128-NPC authority #3695, residency index #3700,
verified action histories #3690, and prior original Game Studio milestones.

## Milestone — true past world snapshots, not fabricated replay animation

The original residency index answers where each uniquely embodied citizen
physically is **at the end of a source game**. This milestone allows a user
to select **one to twelve increasing historical game turns**, including
genesis, intermediate steps and the current end, and reconstructs each
source-verified original NPC world at that real turn.

Historical reconstruction uses the original typed source settings,
content-addressed authored scenes, exact seed, reviewed chunk/LOD policy
and the original *prefix of player action commands*. Each historical
game snapshot is independently recreated from the real source runtime;
its final action-chain head and source identities must match the
corresponding prefix of the complete original playthrough. Any mismatch
is rejected before a spatial view is shown.

Each authentic original turn uses the same physical chunk-residency
index as #3700, preserving real NPC IDs, tile coordinates, current
player cell, chunk membership, detailed-versus-deferred status, source
digest and actual movement receipts.

## What is genuinely compared

For every source-authenticated selected epoch the result contains:

- Exact historical game turn and original action-chain head.
- Physical location of every originally instantiated resident.
- Population counts in **every** chunk, including empty chunks.
- The actual resident count and player tile at that turn.
- IDs of residents whose positions changed between chosen epochs.
- Count of genuine one-tile NPC movements in the corresponding real
  source action ledger interval, whether or not the final tiles differ.
- Cumulative actual detailed and deferred NPC work.
- The actual loaded chunks for the original player's position.
- Bounded source-verified nearest-neighbor residency queries for the
  chosen chunk, with candidate scope, paginated residents and the
  exact original source head.

A purported resident position change must have an actual movement
event from the original source interval. This does not require
inventing an intermediate path between two snapshots: the exact
gameplay trace contains the movement events, while snapshots display
only the positions that were **actually simulated**.

## Fidelity, trust, performance and proof

- Completely replays the original source receipt before accepting
  untrusted historical input or a query result.
- Exact historical turns must be increasing, distinct integer values
  not exceeding the original finite action list length. Booleans,
  out-of-range epochs, reordered or unrecognized queries are rejected.
- Verifies each prefix using the original source game kernel and
  rechecks every historical chunk index and data integrity.
- The output contains the complete reviewed source once and compact
  past-world summaries. It does not include twelve redundant full
  replay logs embedded inside every historical epoch.
- Historical verification independently reconstructs the entire
  indexed result and rejects changed actor locations, chunk
  populations, claimed movement, LOD budgets, source hashes,
  actor IDs, false release claims and forged milestones.
- A counter reports the number of extra original prefix actions
  reexecuted to build the historical views; this is deliberately
  correctness-first, **not constant-time snapshot access**.
- No interpolated offscreen NPC activity, speculation, changed
  source project files or core AI model weight promotion.

All hashes are source content-integrity evidence, not cryptographic
user signatures. The runtime is a CPU original-reference simulator,
not native Godot execution or universal game hardware certification.

## Operator tools

Engine:
skeleton/ai/game_builder/advanced_historical_spatial_lens.py

Tests:
tests/test_game_builder_historical_spatial_lens.py

Offline CLI:
original-spatial-history --record SOURCE --turns EPOCHS --query QUERY
verify-original-spatial-history --record SOURCE_HISTORICAL_RECEIPT

Token-protected local Studio:
POST /api/original-spatial-history
POST /api/verify-original-spatial-history

Visual Dialogue Studio:
Historical Spatial Lens beside Chunk Residency Index. Review actual
game turns (or select real genesis, midpoint and current tick), query
the already selected real original chunk, and inspect verified
population/citizen physical history and authentic real actor movements.

Dedicated cross-platform CI:
.github/workflows/game-builder-historical-spatial-lens.yml
Actual full replay, noninterpolated historical snapshots, forged
evidence rejection, source seed parity, and CLI/Studio auth tested
on Ubuntu and Windows at exact PR head.

## Dated improvements, October 12, 2026

- Added exact-turn source-world reconstruction (extends current NPC
  index into inspectable physically legitimate historical positions).
- Added chunk occupancy and per-body changes between chosen epochs
  (supports reviewing real NPC relocation rather than approximate
  animation or invented paths).
- Added source action-chain validation of every past frame and actual
  movement totals (rejects forged movement or retroactive eyewitnesses).
- Added bounded spatial queries in every original historical snapshot
  (preserves fidelity budgets and near-player inspection).
- Added Studio/CLI exploration and Ubuntu/Windows adversarial CI
  (independent source and user-access verification).

## Next work

Subsequent major milestones can add a compact durable history index,
verified chunk-delta snapshots for faster past-state access, event
subscriptions and a native Godot execution plane that reproduces
exact source movement evidence. Any such acceleration requires a
separate correctness and hardware evaluation gate. This draft remains
unmerged, and no full-app completion percentage is asserted.
