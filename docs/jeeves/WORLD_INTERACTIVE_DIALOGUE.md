# Original interactive dialogue graph

A new authored conversational vertical connects original NPCs and world
scenes to actual player choices. Nodes are original NPC utterances, responses
either lead to another node or hand off to a canonical world choice. Finite
graph validation rejects cycles, unreachable nodes, dead ends, absent speakers,
unearned choice targets, duplicate IDs, stale cast/world digests and excessive
source or graph sizes. The bounded proof supplies a response-path witness for
every authored world-choice handoff.

The operator uses \`world-dialogue propose\` to obtain a typed unapproved
proposal. \`save --create --source-json JSON\` persists it under the world
lease. \`edit --expected-digest SHA --operation-json JSON\` accepts
\`upsert_node\`, \`upsert_conversation\`, \`remove_conversation\` or a bounded
atomic \`batch\`, clearing approval on every change. \`approve\` requires
reviewed cast and explicit review note. \`editor\` publishes an offline CSP
authoring UI that exports unapproved JSON. \`compile\` publishes a CSP-bound
HTML5 conversation player, a typed engine recipe, and a source-digest receipt.
\`verify\` reconstructs outputs and rejects tampering.

\`player --slot SLOT --conversation ID --responses-json JSON\` previews
response replay against a canonical saved session. \`choose\` additionally
requires the exact session and dialogue digests and commits the resulting
canonical world choice atomically under the world-wide lease. A dialogue
cannot write session state without an earned canonical world transition.

Typed Jeeves read-only previews expose proposal, inspection and saved-session
conversation replay without granting approval or publication. All gameplay
content is original, no remote assets or network access are used, and the
source-level recipe is not a built executable or device qualification.
