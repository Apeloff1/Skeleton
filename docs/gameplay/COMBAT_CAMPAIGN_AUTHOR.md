# Transactional player combat campaign editor

`python -m skeleton combat-campaign-author demo` edits the original
campaign's earned reward and replays its actual winning human actions.
`run --source-json '<json>' --edits-json '<json>' --expected-source-digest
<digest>` atomically applies a bounded batch under an exact source lease.
`verify --report-json '<json>'` replays the full edit journal, gameplay
preview and portable save to reject forged or stale results.

Supported edits: `set_reward`, `set_turn_limit`, `set_actor_stat`,
`reorder_encounters`. Every edit revalidates the canonical campaign
schema; hero stats propagate across all encounters to preserve identity.
No mutation is published if any edit is invalid or the batch is a no-op.
Optional `--preview-actions-json` plays the authored game using the
canonical human reducer. The response includes the exact new source,
replay-derived checkpoint, decision board when active, portable bundle,
and edit-chain receipts. Digests are not authentication signatures.

Focused test: `python -m unittest skeleton.testing.test_combat_campaign_author -v`.
No release certification is implied without successful final-head CI.
