# Signed game and private progress migration under pinned signer history

`python -m skeleton app migrate-policy-chain-signed-progress` requires
independent source ZIP, manifest, save and public-key SHA-256 pins and an
ordered 2–16 snapshot signer-policy history. Supply `--archive`,
`--destination`, `--original-save`, `--migrated-save`, `--public-key`,
`--signature`, the four `--expected-*-sha256` pins, and a chronological
`--policy PATH --expected-policy-sha256 HEX` pair per snapshot.

`--trusted-local-operator --preflight-only` performs read-only admission
without reserving either output. Without `--preflight-only`, the canonical
signed migration installs the original playable source into a fresh destination
and publishes an independently pinned private replay save. Historical policy
snapshots are checked again after migration. No existing destination or save
may be overwritten. If a late check fails, retain both outputs for quarantine:
the two publications are not an atomic transaction and automatic rollback
is intentionally disabled. This is not policy freshness, native device
qualification, rights certification, or consumer release approval.
