# Studio A: typed original-world canon workbench

The \`world-canon\` command is an operator-reviewed deterministic proposal and
edit compiler, not a claim that an LLM generated content or that the game is
qualified on a consumer device. All text comes from the author's supplied brief
and explicit subsequent edits. It provides an immediately playable offline HTML
choice experience and a versioned JSON handoff for downstream game builders.

## Source → typed proposal → persisted edit → verified compile

\`\`\`sh
python -m skeleton world-canon --store ./private-worlds propose \
  --id lantern_marsh --premise 'A courier carries a sealed message.' \
  --protagonist Iris --region 'Lantern Marsh' --goal 'Deliver the message.'
python -m skeleton world-canon --store ./private-worlds inspect --id lantern_marsh
\`\`\`

Inspect returns a SHA-256 source digest. To revise, write an explicit JSON
operation with \`action\` and \`value\`, then use:

\`\`\`sh
python -m skeleton world-canon --store ./private-worlds edit \
  --id lantern_marsh --expected-digest <CURRENT_DIGEST> \
  --operation-file ./reviewed-edit.json
python -m skeleton world-canon --store ./private-worlds compile \
  --id lantern_marsh --expected-digest <NEW_DIGEST>
\`\`\`

Supported operations: \`add_scene\`, \`add_choice\`, \`add_ending\`,
\`replace_scene\`, \`replace_choice\`, \`replace_ending\`. Each operation must
produce a valid complete world; create related nodes in the appropriate order.
For nontrivial structural edits, use a new authored source revision rather than
temporarily accepting broken continuity. Every ending requires a deterministic
choice witness, and all scenes must be reachable. The compiler rejects
reachable dead ends, unknown references, duplicated IDs, invalid flags,
noncanonical Unicode, unbounded search, and stale source digests.

The emitted HTML is offline, requires no network or assets, uses DOM text nodes
rather than HTML injection, and carries a CSP-hashed player script. The world
manifest is embedded as JSON, including proof witnesses and source digest.
The CLI reports the HTML SHA-256 for downstream artifact verification.

Custody uses POSIX descriptor-anchored no-follow reads and writes, exclusive
per-world lock files, fsync and atomic replacement. A leftover lock is a
fail-closed recovery hold and must be investigated before manual removal.
The output is not signed; SHA-256 detects accidental or malicious alteration
only when the expected digest is held by a trusted party. Do not treat it as an
authentication or release certificate.

## Focused validation

\`\`\`sh
python -m pytest -q skeleton/testing/test_jeeves_world_canon_workbench.py
\`\`\`

This vertical does not assert compatibility with Studio B's canonical scene
engine, device qualification, review approval, or any exact-head CI gate.
Those integrations require separately proven adapters and acceptance fixtures.
