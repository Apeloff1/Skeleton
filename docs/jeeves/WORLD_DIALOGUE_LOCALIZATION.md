# Reviewed original branching NPC dialogue language editions

This is an independently editable localization plane for **branching NPC
dialogue**, not a duplicate of world scene/choice localization. A typed
proposal binds to exact canonical world, reviewed cast and authored dialogue
digests. Each locale edition must cover every conversation, node and player
response exactly once, in canonical order. Locale tags are bounded to
\`xx\` or \`xx-YY\`. No machine translation, implicit network request,
unreviewed fallback or claim of linguistic accuracy is made.

\`world-dialogue-locales propose\` creates an unapproved source edition
with one user-supplied node/response translation. Other nodes initially
retain original text as explicitly reviewable placeholders. The operator
must review and edit every translation before approval. \`save --create\`
persists the source, \`edit --expected-digest\` updates a locale or node,
and \`approve --review-note\` requires reviewed cast and dialogue.
\`editor\` emits a CSP-bound offline JSON export UI. \`compile\` emits a
language-selectable HTML5 NPC conversation player, typed engine recipe and
SHA-256 receipt. \`verify\` rejects stale sources or artifact tampering.
\`player\` replays a saved canonical player session into a selected locale.
Jeeves exposes only read-only typed proposal, inspection and player previews.

Only dialogue utterances/responses are localized by this plane; canonical
world scene and ending strings remain in their source language. This is
reviewed original source, not a complete translated game or device release.
