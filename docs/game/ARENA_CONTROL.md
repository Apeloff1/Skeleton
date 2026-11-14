# Offline Tactical Control-Point Game

The `arena-control` mode extends the canonical tactical arena with original
capture objectives. Its only way to move, attack, guard or rest is through the
existing turn-validated, wall-aware, collision-aware canonical arena engine.
A capture is earned after a legal action only when a living actor occupies an
authored zone. Each occupied zone scores its authored points for that actor's
team. The source has a strict score target and action budget. A threshold
winner takes priority over combat termination on that action; simultaneous
threshold winners draw. A canonical combat win also ends the game, while
exhausted turns or a canonical draw end without a winner.

`python -m skeleton arena-control demo` plays the original Lantern Harbor
canal beacon match: scout moves east, warden moves west, and scout guards.
The western beacon awards two accumulated points, so wayfarers win. All
actions, positions, capture receipts, scores, parent save digests and the
nested canonical arena are independently replayed from the authored source.

Use `arena-control new --source-json ...` to start; `play --source-json ...
--actions-json ...` to apply a bounded list of legal canonical actions;
`resume --session-json ... --actions-json ...` to continue a checkpoint;
`verify --session-json ...` to rebuild a save from the source and action
journal. `pack --session-json ...` exports a portable JSON checkpoint;
`unpack --package-json ...` verifies its manifest and full nested replay.

`arena-control-author demo` edits the original score target and previews
the playable result. `edit --source-json ... --operations-json ...
--expected-digest ... --actions-json ...` applies a transaction of up to
16 source-fenced edits; `verify --source-json ... --receipt-json ...`
reexecutes the transaction and preview. Supported edits: set-score-target,
set-max-actions, set-zone-points and move-zone. Unknown keys, duplicate
zones, wall placements, stale digests, no-op edits and illegal preview
actions fail closed without mutating caller source.

This is offline deterministic integrity, not cryptographic authentication,
network multiplayer authority, asset provenance or device qualification.
Maximums: 8 zones, 96 actions, 2 MiB JSON export, 200 target points.
