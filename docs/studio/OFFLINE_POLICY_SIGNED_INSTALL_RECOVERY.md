# Policy-bound recovery of quarantined signed original games

`python -m skeleton app recover-policy-signed-install` refuses to
reinstall from a previously valid but now revoked signing key. It requires
an independently pinned local policy, original archive, detached Ed25519
signature, public key, quarantined installation, and a **fresh** destination.

Required flags: `--quarantined`, `--archive`, `--destination`,
`--public-key`, `--signature`, `--policy`,
`--expected-archive-sha256`, `--expected-manifest-sha256`,
`--expected-public-key-sha256`, `--expected-policy-sha256`,
`--trusted-local-operator`. Use `--preflight-only` for read-only
admission without reserving a destination.

Recovery never uses quarantined bytes as the new installation source,
never clears or modifies the quarantine, never clobbers an existing
destination and never silently rolls back a partial new installation.
A late failure leaves the new destination quarantinable. Policy epoch
does not guarantee freshness; consumer/device/rights holds remain active.

Focused acceptance:
`python -m pytest skeleton/testing/test_app_offline_policy_signed_install_recovery.py -q`.
Run tests and required security/CI gates on exact final SHA.
