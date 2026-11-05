# Playable combat stamina

Canonical combat owns HP, attack, defense, turn order, guard, rest and victory.
The stamina overlay owns only bounded per-actor energy costs and recovery.
An unaffordable action is rejected before canonical combat changes.

Run python -m skeleton combat-stamina demo for an original earned victory.
simulate plays authored turns; resume continues a replay-verified checkpoint;
verify checks all source, combat and stamina receipts; export and import
package a deterministic offline save. legal exposes only affordable actions.
author uses an expected source digest as a compare-and-swap edit lease and
can preview actual gameplay before accepting an edited balance.

Authored source fields: schema_version skeleton.combat_stamina.v1,
scenario (canonical turn_combat.v1), player_team, max_stamina, attack_cost,
guard_cost, rest_gain. No arbitrary scripts, remote calls or implicit grants.

Run pytest skeleton/testing/test_combat_stamina.py and mandatory exact-head
CI. Checksums detect corruption but are not signatures or release evidence.
