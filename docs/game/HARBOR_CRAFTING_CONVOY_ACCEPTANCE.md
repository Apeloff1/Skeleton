# One-command original game acceptance

`python -m scripts.game.harbor_crafting convoy-accept` runs the authored Lantern Quay convoy from validated source to a real victory: finite material gathering and lantern crafting, collision-safe movement with a moving merchant, tactical escort/ambush combat, dock delivery, portable game package, deterministic replay, append-only CAS journal, five earned quests and both choice-dependent relief/salvage endings.

The result is a compact JSON acceptance receipt containing the original source and authored boards, exact player actions, independently reconstructed plan/package/play/journal/ending digests and an earned outcome summary. No generated duplicate game snapshots are embedded. `python -m scripts.game.harbor_crafting convoy-verify-accept --convoy-acceptance receipt.json` reconstructs every subsystem and rejects fabricated rewards, altered route or forged source-to-runtime claims even when the outer digest is resealed.

For another authored convoy, supply `--source world.json --convoy-board route.json --convoy-contracts quests.json`. A source that cannot genuinely earn the full playable path or either ending fails closed; no synthetic completion or fallback reward is issued.

Focused regression: `pytest -q skeleton/testing/test_harbor_crafting_convoy.py skeleton/testing/test_harbor_crafting_convoy_package.py skeleton/testing/test_harbor_crafting_convoy_solver.py skeleton/testing/test_harbor_crafting_convoy_contracts.py skeleton/testing/test_harbor_crafting_convoy_acceptance.py`. Passing these is not a substitute for exact-head CI, signed provenance, consumer device qualification or independent review.
