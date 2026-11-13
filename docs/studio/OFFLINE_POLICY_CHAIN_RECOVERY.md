# Quarantined signed-game recovery under pinned signer history

`python -m skeleton app recover-policy-chain-signed-install` requires a
2–16 snapshot independently pinned chronological source signer history,
the original signed archive, detached Ed25519 public key/signature, a damaged
quarantined installation and a fresh unused destination. Pass `--quarantined`,
`--archive`, `--destination`, `--public-key`, `--signature`,
`--expected-archive-sha256`, `--expected-manifest-sha256`,
`--expected-public-key-sha256`, and repeated chronological
`--policy PATH --expected-policy-sha256 HEX` arguments.

`--trusted-local-operator --preflight-only` checks admission without reserving
a destination. Actual recovery reconstructs from independently pinned original
source, never from quarantined executable bytes. The original damaged tree
remains untouched. Every historical policy snapshot is checked across recovery
and a late failure leaves the new destination for quarantine, not deletion.
No automatic rollback, global policy freshness, native package signature,
consumer device qualification, rights or publisher identity is certified.
