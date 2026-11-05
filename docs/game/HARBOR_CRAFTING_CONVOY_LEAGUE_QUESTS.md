# Cross-round convoy league mission and event engine

The original Lantern Quay championship includes a mandatory cross-round
mission chain: craft the first lantern, repel the canal raider, deliver
relief, protect the homecoming cargo, repel the marauder, and reach the dock.
The first three objectives are prerequisites for the later homecoming
objectives. Points and a complete ending are awarded only when the
replay-verified underlying convoy reports prove those events occurred.

Authored objectives have stable IDs, a round binding, a kind, a target,
topologically ordered prerequisites, a points value and a required flag.
Validation rejects duplicate IDs, cyclic or forward prerequisites, unknown
enemies, uncraftable items, invalid thresholds, boolean-as-integer tricks,
source mismatches and unbounded boards.

The transactional quest editor accepts a CAS board digest, bounded edits
and optional replayed preview. Its portable revision is independently
reconstructed during verification. Gameplay state is never mutated by an
edit preview. Failed and partial league saves can still show earned
objectives but cannot claim the championship quest ending.

CLI: `league-quests`, `league-verify-quests`,
`league-quest-status`, `league-quest-author`, and
`league-verify-quest-author`. The authored example is
`harbor_lantern_quay_convoy_league_quests.json`.
