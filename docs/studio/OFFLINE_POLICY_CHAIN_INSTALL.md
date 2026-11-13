# Signed original-game installation under pinned policy history

`python -m skeleton app install-policy-chain-signed-source` requires a
2–16 snapshot independently pinned chronological signer-policy history before
the canonical Ed25519-verified no-clobber original-game source installation.
The latest supplied policy must authorize the actual independently pinned key.

Pass `--archive`, `--destination`, `--public-key`, `--signature`,
`--expected-archive-sha256`, `--expected-manifest-sha256`,
`--expected-public-key-sha256`, chronological repeated
`--policy PATH --expected-policy-sha256 HEX`, and
`--trusted-local-operator`. A destination that already exists fails closed.

The installer rechecks every historical policy inode and byte sequence after
source publication and deterministic playable replay. A late failure leaves the
destination in quarantine for independent inspection, never silently deletes
it or overwrites user progress. The operation cannot establish whether the
supplied latest policy is current, cannot sign a native package, and cannot
certify publisher identity, rights, hardware, or consumer release readiness.
