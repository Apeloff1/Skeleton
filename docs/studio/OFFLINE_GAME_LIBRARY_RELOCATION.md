# Read-only original game library relocation assurance

\`python -m skeleton app audit-offline-library-relocation\` compares two
independently pinned original-game library inventories, each containing 1–8
installed games, original archives and private replay saves. Use repeated
\`--before\` and \`--after\` JSON entries in the same strict six-field
format as \`audit-offline-game-library\`, and supply
\`--trusted-local-operator\`.

Every old and new game is independently replayed from source/archive/save,
with descriptor identities fenced across the entire audit and a second
complete verification pass. Project identities must match as sets; each
original archive pin, manifest pin, save pin, world digest, replay digest,
action count and source file count must be unchanged. Installed roots must
be distinct. Any divergence rejects the entire batch without a success
receipt. Results omit private filesystem paths and use sorted project IDs.

This is **verification after relocation**, not a migration operation. It
does not move or rewrite saves, prove atomicity across directories, authorize
a publisher, sign an executable, establish device compatibility, or release
the application. Existing security and exact-head CI holds remain mandatory.
