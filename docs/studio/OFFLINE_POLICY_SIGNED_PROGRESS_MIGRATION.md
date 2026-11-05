# Policy-bound signed game and private-save migration

`migrate-policy-signed-progress` composes an independently pinned local
Ed25519 trust policy, detached signature verification, canonical original-game
installation, private replay-save migration and independent post-migration
playability acceptance. It adds a strict key revocation gate before **either**
output is reserved, without weakening existing signed migration contracts.

The command requires `--archive`, `--destination`, `--original-save`,
`--migrated-save`, `--public-key`, `--signature`, `--policy`, the five
independently obtained `--expected-*-sha256` pins (archive, manifest, save,
public key and policy) and `--trusted-local-operator`.

Use `--preflight-only` for a read-only check of policy, source, save and both
destination paths. This is an observation, never a reservation lease. Normal
execution rechecks before publication and after canonical migration. Both
outputs are fresh/no-clobber; a late failure **must retain** the outputs for
manual quarantine and cannot be treated as an atomic transaction.

The policy's epoch does not prove freshness or prevent rollback. No consumer
device, executable signature, rights or publisher identity is certified.
Canonical acceptance: `python -m pytest
skeleton/testing/test_app_offline_policy_signed_progress_migration.py -q`.
Exact-head CI and security gates must pass before promotion.
