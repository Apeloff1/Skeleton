# Advanced Original Game Studio — Source-Verified Streaming Timeline

Date: 2026-10-12 (Europe/Oslo). Status: draft, CI verification pending.
Parent: original chunked NPC world PR #3689, itself stacked on unified
physical NPC authority #3686 and earlier Game Studio work.

## Capability: pause, resume and branch a real physically simulated world

An original 21x21 or 35x35 NPC game can be source-replay verified and then
bookmarked at exact action ledger cursors. The bookmark is a read-only
historical receipt, not an editable actor-state snapshot.

The checkpoint API verifies the complete source game first, then bookmarks
the origin, selected actual eight-turn ledger positions and the current end.
Each cursor is bound to the exact original action digest, complete world-state
digest, stable physically embodied actor count and source game digest.
Only approved intervals from 8 to 64 turns are accepted; at most 17
bookmarks can exist in a single finite 128-action game.

A player can resume the latest cursor or explicitly fork an earlier bookmarked
turn, discarding later actions. All added commands are registered original
gameplay actions, not arbitrary scripts or saved state patches.

A branch is executed by reconstructing original source scenes, seed, typed
settings, chunk geometry, active detail budget and the exact prefix action
list, and then executing the new actions. The result is a completely new
genuine game world and chained history, not a patched copy of a JSON
dictionary. Physical actor positions, detailed/offscreen cycles, sourced
eyewitness events, finite supplies and optional quest outcomes are recomputed.

## Evidence and safety

- Reject unknown source schemas and any altered original game state.
- Reject forged action histories, actor locations, quest milestones, source
  IDs, event-head digests and modifications to timeline option budgets.
- Reject booleans, negative cursors, unattested intermediate fork points,
  unsupported or excessive actions, noncanonical nested JSON and forged
  results.
- Keep the discarded old future explicitly visible rather than pretending
  it never occurred; the new result has its own distinct source head.
- Store the entire verified original source receipt in the timeline.
- No source project writes, no core AI weight changes and no claimed
  release/hardware certification.

Replay costs are proportional to the original action stream; this milestone
is intentionally correctness-first and **does not claim constant-time
restore or incremental state snapshot acceleration**. Such acceleration
requires a separate proven checkpoint custody and state transition
equivalence milestone.

## Operator-accessible interfaces

Source implementation:
skeleton/ai/game_builder/advanced_chunked_world_timeline.py

Tests:
tests/test_game_builder_chunked_world_timeline.py

Offline CLI:
- chunked-world-checkpoint and verify-chunked-world-checkpoint
- chunked-world-continue and verify-chunked-world-continuation

Authenticated read-only Studio routes:
- /api/chunked-world-checkpoint
- /api/chunked-world-checkpoint-verify
- /api/chunked-world-continue
- /api/chunked-world-continuation-verify

Visual Studio controls: create original timeline bookmarks, select a verified
turn cursor, enter bounded alternative physical game actions, explicitly
replay the alternate history, and inspect each historical receipt and new
actor trajectory. Nothing silently overrides the original source game.

Cross-platform exact-PR-head GitHub workflow:
.github/workflows/game-builder-chunked-world-timeline.yml
It executes original game timelines and adversarial source tampering tests
under Python 3.11 on Ubuntu and Windows. Multiple world seeds with distinct
branch outcomes are independently verified after continuation.

## Dated milestone ledger

2026-10-12 — Added source-authenticated action-chain cursors
(now supports reviewable pause and timeline bookmarking).

2026-10-12 — Added original source-reexecuted continuation and
explicit alternate-history forks (actual future game physics, no state swap).

2026-10-12 — Added discarded-future custody, fork source-head proof and
separate result digest (different outcomes remain reconstructible).

2026-10-12 — Added adversarial forgery checks, deterministic multi-seed
branches and bounded proof sizes (prevents arbitrary saved state injection).

2026-10-12 — Added authenticated Studio UI, offline CLI, and Ubuntu/Windows
exact-head CI (reviewable and auditable user-facing functionality).

## Next engineering milestones

- True content-addressed local incremental state snapshots with
  independent exact-transition parity and crash-safe durable save files.
- Indexed event-ledger search, bookmark hierarchies, fast divergence
  reporting and deterministic multi-branch comparison.
- Shared world chunk paging to/from persistent secure local storage with
  explicit trust boundaries and signed operator consent.
- Native Godot streamable game worlds with real hardware performance tests.

No PR is declared merged to main and no AI model weight promotion is implied.
