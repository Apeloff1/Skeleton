# Cooperative league scoring author

Use `python -m skeleton scene-market-party-league-author demo` for an
original playable market victory with a transactional scoring-rule edit.

An editor can call `edit --league-json JSON --patch-json JSON
--expected-state-digest SHA256`. The source and all prior scored attempts
are immutable. Edits are accepted only on an empty league, under an exact
optimistic digest lease, with a nonempty typed subset of existing rules.
Weights are validated by the canonical league scorer; stale edits, no-ops,
unknown fields and weights that reward failure are rejected.

`verify-edit --original-json JSON --receipt-json JSON` independently
replays the edit and rejects tampered receipts, even if their checksums
are recomputed. `preview --league-json JSON --checkpoint-json JSON`
scores an actual replay-verified winning checkpoint, records an offline
attempt, exports and reimports the league, and verifies the ranking.

This author tool never changes market currency, inventory, quest outcomes
or stored scored attempts. The output is an integrity receipt, not a
cryptographic author signature or consumer release qualification.
