# Market vertical: replay-verified economic custody

The `scene-market-accept` acceptance command now checks an independently
recomputed economic witness alongside canonical play, interactive checkpoints,
editor receipts and portable session import. This closes the gameplay
source-to-replay-to-economic-provenance loop for the **single authored market**.

Every coin is traced to a canonical pickup, every purchase to a finite offer,
every crafting change to authored input/output quantities, and every delivery
to a one-time inventory spend and reputation award. An attacker who changes
the ledger and recomputes ordinary checksums still fails acceptance because
the witness is recomputed from the original source and action journal.

The report adds `ledger_checksum`, `ledger_portable_checksum`,
`ledger_credits_earned`, `ledger_credits_spent` and
`ledger_tamper_rejected`. No compatibility-breaking save schema change
is made. Ledger evidence is not identity authentication, proof of author
rights, multiplayer anti-cheat or target-device release qualification.

Focused validation: `python -m pytest skeleton/testing/test_scene_market.py
skeleton/testing/test_scene_market_ledger.py
skeleton/testing/test_scene_market_acceptance.py`. Full exact-head CI
and device acceptance remain mandatory before promotion.
