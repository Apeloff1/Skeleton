# Signed original-game library relocation assurance

The \`audit-signed-library-relocation\` application command compares
1–4 old and new signed game installations using the same strict JSON entries
as \`audit-signed-game-library\`. Supply repeated \`--before\` and
\`--after\` entries and explicit \`--trusted-local-operator\`.

Each installation must independently pass detached Ed25519 signature
verification, pinned multi-epoch signer history, original source/archive
reconciliation and private replay. The complete library is checked twice,
with source, archive, save, detached key, signature and policy snapshot
descriptor identities captured across both inventories. Every project,
archive, manifest, private save, signer key, policy hash chain, epoch chain,
world and replay must agree. Any mismatch fails the entire operation.

This is a read-only post-relocation assurance, not a migration tool, signer
rotation publisher, persistent anti-rollback service, consumer-device proof,
native executable signing process or release certification. Historical
revocation is proven only within independently pinned supplied snapshots.
