# Convoy quest chains and earned economic endings

The original Lantern Quay convoy contract board is `skeleton/game/gameplay/fixtures/harbor_lantern_quay_convoy_contracts.json`. It defines five source-bound quests: forge a real lantern, reach the first crossing, defeat the authored canal raider, preserve the full cargo hull, and earn the dock delivery. Dependencies are acyclic and checked against preceding authored quest IDs. Every award derives from the verified canonical crafting actions and replayed convoy combat/waypoint state.

`convoy-contract-run --convoy-report convoy.json --convoy-contracts board.json --convoy-choice relief --require-all` produces a portable, replay-verified quest outcome. Choosing `relief` grants reputation only when hull is at least two; choosing `salvage` grants credits only after at least seven actually earned bounty units. The two endings are mutually exclusive in each saved outcome, and neither can be obtained from a fabricated score or an incomplete convoy.

`convoy-contract-verify --convoy-contract-report result.json --require-all` independently reconstructs all quests, their prerequisites and consequences. `convoy-contract-status` lists unearned required quests. `convoy-contract-author --convoy-report convoy.json --convoy-contracts board.json --convoy-contract-edits edits.json --expected-convoy-contract-digest SHA256 [--convoy-contract-report result.json]` performs an optimistic transactional edit and optional replayed preview; `convoy-contract-verify-author` reconstructs it.

Test with `pytest -q skeleton/testing/test_harbor_crafting_convoy_contracts.py`. The JSON digests establish integrity only, not signed provenance. Exact-head CI and review remain required before promotion or release.
