# Original interactive world assembly

This is the source-complete integration seam for three independently authored
planes: nonmonetary resource economy, original character transformations and
branching NPC conversations. All five sources (canonical world, reviewed cast,
reviewed economy, reviewed arcs and reviewed dialogue) must be present and
approved. A single world-wide exclusive lease prevents source mixing during
compilation, verification and saved-player replay.

\`world-interaction --store DIR inspect --world-id ID\` returns source
digests, individual plane proofs and a cross-plane affordability proof.
The cross-plane proof explores bounded actual world/flag/resource states and
requires every authored dialogue-to-world-choice handoff to be affordable
in at least one reachable state. This closes a correctness gap between a
world-valid conversation and an economically impossible player choice.

\`compile --world-id ID --expected-digests-json JSON\` accepts an exact
five-key source lease and publishes one CSP-protected HTML5 player, one
typed deterministic engine recipe, and a SHA-256 artifact receipt.
\`verify --world-id ID\` recomputes exact outputs under the same lease.
\`player --world-id ID --slot SLOT\` replays a canonical saved player
session across economy and character arcs and exposes available conversations.
Jeeves has a read-only \`world.interaction_preview\` tool; operator review,
source writes and compilation remain separate.

The offline player supports NPC dialogue choices, resource costs/gains,
character belief changes, earned world flags, endings and restart without
external assets, eval or network access. All strings use textContent.
The engine recipe is a source-level handoff to game builders, not a compiled
executable, release, device or consumer qualification. Exact-head regression
tests and mandatory CI are still required.
