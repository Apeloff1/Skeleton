# Cinder Ridge: authored missions with replay evidence

Run `python -m skeleton.game.gameplay.ridge_rescue.missions_cli inspect` to
inspect the original authored mission graph. Each node has a unique stable ID,
a bounded score, explicit prerequisite IDs and a source-bound condition. Source
parsing enforces a forward-only acyclic graph, unique identifiers, a maximum
of 64 nodes and 1,000 total possible points.

Use `evaluate --journal saved.json` to evaluate a real gameplay journal.
The engine verifies its world, action chain, journal hashes and final state,
then replays every prefix to determine the earliest earned turn. Rescue,
crafting, raider defeat, shelter, storm, trading, beacon and ending conditions
are derived from actual gameplay; no client-supplied completion flags are
accepted. Protection and salvage endings belong to an exclusive finale group.

Use `author --expected-head SOURCE_SHA --operation JSON` to change one
node's title, points, prerequisites or condition transactionally. The editor
reparses the entire DAG and rejects stale source revisions, invalid targets,
cycles, missing dependencies and excessive rewards. A revision can be
replayed with `verify-author`.

Use `export --journal saved.json --output earned.json` and
`verify --bundle earned.json` to create and validate a portable
source+journal+report envelope. SHA-256 is an integrity digest, not an
authentication signature. The verifier independently derives all badges and
scores from the source and action history. Bounded source and export sizes
prevent unbounded processing. This module does not mint game credits or bypass
the core economy; points are achievements only.
