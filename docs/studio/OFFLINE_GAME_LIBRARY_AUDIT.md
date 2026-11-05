# Offline original-game library audit

The canonical command \`python -m skeleton app audit-offline-game-library\`
inspects between one and eight **already installed** original game sources.
Each entry supplies six independently held fields: \`installed_source\`,
\`archive\`, \`private_save\`, \`expected_manifest_sha256\`,
\`expected_archive_sha256\`, and \`expected_save_sha256\`.
Pass one \`--entry '{"installed_source":"...","archive":"...",...}'\` per game
and the explicit \`--trusted-local-operator\` acknowledgement.

Each game undergoes the existing source/archive/save cross-custody assurance,
including actual offline replay. The batch captures descriptor identities
before the first pass, between passes, and after a second independent pass.
Any failed game, repeated path, duplicate project identity, malformed pin,
symlink substitution, inode replacement or receipt disagreement fails the
entire batch. No partial success receipt is published.

The result contains only per-game project identity, independent hashes,
world/replay digests, bounded action/file counts, and a canonical digest
over the ordered receipts. It deliberately excludes private filesystem paths
and private save contents. No files are created or modified.

The inspection is observational, not a persistent filesystem lease.
It does not establish archive signing, signer freshness, originality rights,
Apple/Windows/Android device qualification, native Godot execution, or
consumer release certification. Required exact-head CI and security gates
remain independent and mandatory.
