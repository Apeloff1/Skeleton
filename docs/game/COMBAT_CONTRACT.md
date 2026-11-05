# Combat mission contracts (offline playable vertical)

Run `python -m skeleton combat-contract demo` to play the original bridge-watch
mission. The result contains a canonical turn-combat session, objective progress,
earned inventory and credits, an ordered event journal, a save lineage and
source/state digests. No network, provider, script execution or external assets
are required. Use `simulate --source-json JSON --actions-json JSON` for authored
missions; `resume --session-json JSON --actions-json JSON` for checkpoints;
`verify`, `export`, and `import` for portable replay-checked saves.

The source schema `skeleton.combat_contract.v1` accepts a canonical
`turn_combat` scenario, player team, unique objective IDs, and a reward.
Defeat objectives require a named opposing actor's HP to reach zero; guard
objectives count only player-team guard turns; speed objectives require the
player's victory by an authored turn bound. A victory without all objectives
finishes as failed with **no** reward. A lost or drawn combat also grants no
reward. No client action can assign credits or inventory.

Every imported session is rebuilt from the original scenario and every
canonical action; nested combat receipts, event ordering, save ancestry,
objective gates, inventory and currency must match. Reject unknown schema
fields, duplicate IDs, unknown actors, unbounded inputs and forged rewards.
Hashes are corruption detection, **not** a signature or proof of ownership.
Author rights, marketplace provenance and device release remain separate gates.

Regression suite: `pytest -q skeleton/testing/test_combat_contract.py`.
This vertical extends the existing combat runtime without changing its
source schema or relaxing any release/security checks.
