# Studio A — Source-bound NPC transit feasibility

This vertical composes the canonical temporal-window receipt with the
scene scheduler's authored site/NPC sequence. Operators provide a bounded
directed graph of estimated site-to-site travel ticks. A deterministic
shortest-path proof checks every repeated NPC appearance against its
previous scene's end tick and the next scene's start tick.

Unknown routes are explicit conflicts, not zero-cost teleportation.
A late arrival blocks playable handoff. The proof does **not** claim
measured movement, native collision, hardware qualification or release.

The prompt `plan source-bound npc transit estimates` produces an empty
edge graph for operator completion. The CLI accepts `--temporal-receipt`
and exactly one of `--prompt` or `--graph`; use `--publish` for a
private no-overwrite receipt, `--restore` for canonical replay, and
`--playable-manifest` only when every transition is feasible.

The static Jeeves tool `studio_original_npc_transit` exposes the same
typed, authorization-gated read-only proof. It never calls an external
provider or executes user-supplied source. All receipts carry exact
source/session/temporal identities and fail closed on tampering.
