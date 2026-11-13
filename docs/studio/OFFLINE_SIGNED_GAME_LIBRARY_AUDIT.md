# Signed original-game library assurance

The \`audit-signed-game-library\` application command checks 1–4 separately
installed original games, each with a private save, detached Ed25519 public key
and signature, and 2–16 independently pinned historical signer policies.

Each \`--entry\` is strict JSON with paths \`installed_source\`, \`archive\`,
\`private_save\`, \`public_key_file\`, \`signature_file\`, and ordered \`policies\`;
pins \`expected_archive_sha256\`, \`expected_manifest_sha256\`,
\`expected_save_sha256\`, \`expected_public_key_sha256\`, and ordered
\`expected_policy_sha256\` must be supplied independently. Explicit
\`--trusted-local-operator\` is required.

The audit replays the canonical signer-policy-chain delivery verifier twice per
game and captures descriptor identities for every source, archive, save, key,
signature, and historical policy snapshot across the complete batch. One
failure rejects the entire batch. Receipt ordering is stable and private paths
are excluded. No filesystem mutation or release approval occurs.

Signer revocation is proven only across the *supplied pinned snapshots*. No
persistent anti-rollback state, externally trusted policy freshness, publisher
rights, native executable signature, consumer-device qualification or complete
release certification is inferred. Exact-head security and CI holds remain.
