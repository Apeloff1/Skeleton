# Offline Combat League Coaching Career

Use \`python -m skeleton combat-career demo\` to play three original
Harbor League seasons without network access. The result is a canonical
replay-verified career save. \`new --source-json\` accepts a source
with \`schema_version: skeleton.combat_league_career.v1\`,
\`career_id\`, an authored eight-entrant \`league\`, \`seasons\` (1–4),
and \`training_tokens\` (0–seasons).

\`advance --session-json ... --choice-json ...\` plays one season.
A choice is either \`{"kind":"rest"}\` or
\`{"kind":"train","entrant_id":"amber_guard","stat":"attack"}\`.
Training consumes one token and adds one bounded stat point to the
selected entrant for that season only. Entrant identity and league
rounds remain source-bound. Unknown entrants, exhausted budgets,
out-of-bounds stats and malformed inputs fail closed without changing
the supplied save.

\`verify\`, \`board\`, \`export\` and \`import\` operate on canonical
JSON. The journal contains full league match receipts, source digests,
winners, and a parent-linked save chain. Verification recomputes every
season from original source and choices, rather than trusting saved
scores, rewards or checksums. Bundles provide corruption detection,
not authenticated signing. No consumer/device release claim is made.
