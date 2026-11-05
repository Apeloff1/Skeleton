# Owner-private mixed replay continuity handoff

Use `python -m skeleton app mixed-library-continuity-handoff` with
matching old/new signed and unsigned JSON descriptors, independent source,
archive, save, public key, signature and signer-policy pins, plus
`--trusted-local-operator`.

Publication uses `--output <new-private-receipt.json>` and never overwrites a
destination. Inspection uses `--inspect-receipt <receipt.json>` with a
**separately distributed** `--expected-receipt-sha256 <hex>`.

Both operations reexecute the old and new replay histories for every game.
They reject lost actions, forked saves, a signed-to-unsigned downgrade,
policy-history substitutions, source swaps and receipt custody changes.
A failed post-publication recheck leaves uncertain receipts for operator
quarantine; it never deletes a pathname that may have been replaced.

No executable is signed and no consumer device, rights ownership, current
revocation feed, persistent rollback counter or release is qualified.

Focused acceptance:
`pytest -q skeleton/testing/test_app_offline_mixed_game_library_continuity.py skeleton/testing/test_app_offline_mixed_game_library_continuity_handoff.py`
