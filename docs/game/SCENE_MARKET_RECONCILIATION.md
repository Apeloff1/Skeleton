# Market checkpoint reconciliation

`python -m skeleton scene-market ledger-reconcile --before-json '<save>'
--after-json '<save>'` verifies that the second save is an append-only
continuation of the first, for exactly the same authored source.

The verifier fully replays both saves, checks canonical journal prefix
identity, reconstructs economic ledger witnesses, and proves that credit,
inventory, purchases, crafting, deliveries and reputation changes agree with
the appended actions. It emits deterministic from/to state and save digests,
individual appended event receipts and a checksum.

Different source versions, diverging save forks, reversed histories, forged
balances and malformed checkpoints fail closed. A divergent fork is not
silently merged. A checksum is integrity evidence, not a signature.

This is a single-source offline game save continuity proof. It does not
certify multiplayer ordering, payment settlement, devices or release readiness.

Focused tests: `python -m pytest
skeleton/testing/test_scene_market_reconciliation.py
skeleton/testing/test_scene_market_ledger.py
skeleton/testing/test_scene_market_acceptance.py`.
