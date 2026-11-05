# Reviewed original chapters and acts

Studio A's chapter/act editor organizes **existing original world scenes** into
readable chapters and acts without duplicating game systems or inventing
content. Every scene must belong to exactly one act, and every act belongs to
one chapter. All scene/choice/flag transitions remain governed by the
canonical world graph: detours, revisits, hidden routes and doublebacks are
preserved rather than incorrectly linearized.

## End-user workflow

Create a canonical world, then author a JSON proposal with \`prompt\` and
\`chapters\`. Each chapter has \`id\`, \`title\`, \`summary\`, and \`acts\`;
each act has \`id\`, \`title\`, \`summary\`, and \`scenes\` (ordered original
scene IDs). Chapters and acts are ordered by the author, not generated bulk.

\`\`\`sh
python -m skeleton world-chapters --store PRIVATE propose --id worldone --file proposal.json
python -m skeleton world-chapters --store PRIVATE publish --id worldone --file reviewed-source.json --create
python -m skeleton world-chapters --store PRIVATE inspect --id worldone
python -m skeleton world-chapters --store PRIVATE editor --id worldone --expected-digest SOURCE_DIGEST
python -m skeleton world-chapters --store PRIVATE approve --id worldone --expected-digest SOURCE_DIGEST --note "Original chapters reviewed"
python -m skeleton world-chapters --store PRIVATE compile --id worldone --expected-digest APPROVED_DIGEST
python -m skeleton world-chapters --store PRIVATE verify --id worldone
python -m skeleton world-chapters --store PRIVATE player --id worldone --slot reader
\`\`\`

The offline editor edits author-facing chapter and act descriptions and
exports **unapproved** JSON for explicit re-review. The typed read-only Jeeves
tools \`world.chapters_propose_preview\`, \`world.chapters_preview\`, and
\`world.chapters_player\` never mutate or grant approval.

## Proof and engine handoff

The proof validates exact scene coverage, chapter/act identity, bounded
cardinality, actual reachable entry witnesses, and all cross-act choice
transitions. The player view derives current chapter/act and visited
sections from a replay-verified, source-leased session. Compiled HTML5 shows
authored chapter/act headings and only visited progress. The typed engine
descriptor carries exact world/chapter digests, chapter structure, entry
witnesses and cross-act choices for downstream builders.

Private descriptor-anchored source files, exclusive world-wide edit leases,
SHA-256 output receipts, strict CSP, inert JSON and no network access are
mandatory. Stale world revisions, malformed structures, forged sessions,
symlinked artifacts and unreviewed compilation fail closed. The handoff is
**not consumer/device or release qualification**.
