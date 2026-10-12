# Game Studio: Trusted Fast NPC World Forks

Date: 2026-10-12 (Europe/Oslo). Status: draft until exact-head CI.
Parent PR #3690, followed by #3689 and #3686; no main merge.

## Real fast-path milestone

The original chunked timeline verified saved games and alternate history,
but ran the same prefix from genesis once for each alternative. The new
module authenticates a source checkpoint and precise action cursor once,
then keeps an integrity-checked snapshot in a single trusted Python process.
Multiple original story futures use this authenticated state as their
starting point, simulating only the divergent suffix commands.

It uses the EXISTING chunked-world action, active-LOD and schedule functions:
there is no second, subtly divergent gameplay implementation. Each suffix
produces original before/after state digests, source eyewitnesses, actor
movement, inventory and quest consequences, and the exact official chain
head. Complete branch receipts must equal original full-replay results,
not merely share a victory flag or a final state.

Only an independently verified original bookmark may become a preparation
cursor. The engine checks its source scene identities, action hash and state
hash, and copies the actual world so future branches cannot mutate one
another. Any illegal player command rejects the fork without changing the
prepared authority.

## Precise performance and trust guarantees

Trusted preparation authenticates the original source once, then each
same-process branch executes only its new suffix. A bounded batch supports
up to 12 distinct named original alternative histories, with the original
checkpoint included just once instead of redundantly in every result.

Cross-process trust is intentionally DIFFERENT: importing or externally
verifying results triggers full independent source replay for every branch.
No client JSON snapshot can grant execution authority, no content hash is
mistaken for a cryptographic user signature, and no GPU performance or
constant-time durable restore speed is claimed.

The batch reports explicitly count original prefix authentications, suffix
transitions and repeated prefix actions during forks. These are source
operation counts, not invented consumer-hardware timing benchmarks.

Each source-bound outcome retains an original world digest, ledger head,
clock, physical actor count, detailed and deferred actor work, physical
steps, supplies and earned nonterminal quest progression.

## Product surfaces

Code: skeleton/ai/game_builder/advanced_fast_chunk_snapshot.py
Tests: tests/test_game_builder_fast_chunk_snapshot.py

CLI: fast-chunk-forks and verify-fast-chunk-forks.
Authenticated Studio routes: /api/fast-chunk-forks and
/api/fast-chunk-forks-verify.
Visual Studio: Fast Branch Lab with original source cursor selector,
up to 12 entered original branch action arrays, head/time/actor/resource
comparison, and full independent source validation.

Cross-platform exact-head workflow:
.github/workflows/game-builder-fast-chunk-snapshots.yml
Includes complete parent-source equivalence, adverse input/forgery tests,
multiple 35x35 seed games, CLI and Studio permissions on Ubuntu and Windows.

## Timestamped changes

2026-10-12 — Added trusted one-time source preparation
(reduces repeated simulation of common original game history).

2026-10-12 — Executed original game rules directly against copied
source-validated state (preserves physical, memory and economy invariants).

2026-10-12 — Added bounded multi-branch authority, isolated result
summaries and complete historical chain receipts (less redundant evidence).

2026-10-12 — Separated trusted in-process optimization from full untrusted
source import verification (prevents fast-path custody bypass).

2026-10-12 — Added Studio, CLI, adversarial tests and exact-head CI
(transparent source evidence and release restrictions).

## Next

Persistent crash-safe local snapshot files require an explicit cryptographic
authority boundary and proof of native transition equivalence. Native Godot
chunk games, larger NPC populations, game-store release and AI weight
promotion are not claimed. All PRs remain draft until exact-head validation
and stack integration.
