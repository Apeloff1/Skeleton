# Transactional combat contract authoring and interactive play

Run `python -m skeleton combat-contract-author demo` for a complete
source-digest-leased author edit and a canonical gameplay preview. The editor
accepts `run --source-json JSON --edits-json JSON --expected-digest SHA256`,
with optional `--preview-actions-json JSON`. `verify --report-json JSON`
reconstructs the edit transaction and gameplay preview. Edits support
set_reward, set_player_team, add_objective and remove_objective, with strict
field validation, an exact prior source digest, at most 32 operations, atomic
copy-on-write, and no-op rejection. A preview may **fail** its objectives:
the authoring tool never changes that outcome to success or mints rewards.

Run `python -m skeleton combat-contract-play --demo` to control the player's
team in a JSON-lines interface. Opponents use the existing deterministic
offline combat policy; `--manual-opponents` permits controlling all teams.
Each turn prints actor, targets, HP and state digest; submit one JSON action
per prompted turn. Invalid actions get bounded retries. EOF and malformed
inputs fail closed; no implicit victory is produced. The terminal mission
event includes earned inventory and a replay-verified checkpoint. Supply
`--source-json JSON` for an authored contract or `--resume-json JSON` to
resume a checkpoint from the same source. The interactive combat journal is
replayed through the contract engine before rewards are displayed.

Tests: `pytest -q skeleton/testing/test_combat_contract.py
skeleton/testing/test_combat_contract_author.py`. This is an offline CLI
playable vertical; consumer device, external provenance and release readiness
remain unqualified.
