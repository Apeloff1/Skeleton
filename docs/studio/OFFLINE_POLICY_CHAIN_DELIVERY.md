# Pinned signer-history playable delivery assurance

`python -m skeleton app policy-chain-delivery-assurance` combines an
independently pinned 2–16 epoch trust-policy chain, an actual detached Ed25519
source signature, installed original game reconciliation, and owner-private save
replay. It is a read-only consumer handoff *inspection*, not a release approval.

Supply `--installed`, `--archive`, `--save`, `--public-key`,
`--signature`, all four independent archive/manifest/save/key SHA-256 pins,
and a chronological `--policy PATH --expected-policy-sha256 HEX` pair per
snapshot. Explicit `--trusted-local-operator` acknowledgement is mandatory.

The last supplied policy must admit the exact pinned signer. Every snapshot is
checked before and after installed-game replay; same-byte inode substitution
fails. Revocation and epoch checks are pairwise monotonic. Historical snapshots
are not authoritative evidence that the final policy is the current one.
No network fetch, private signing key, source installation, migration, or
package publication is performed. Native executable signing, device testing,
publisher identity, content rights, and all security/release gates remain held.
