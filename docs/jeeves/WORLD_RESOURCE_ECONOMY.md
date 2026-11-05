# Reviewed original resource economy

The world-economy vertical extends canonical original scene/choice authoring with
bounded, nonmonetary resource costs and gains. It does **not** handle real money,
payments, or player purchases. A world prompt produces a typed proposal, which
must be persisted and explicitly approved by an operator. Editing always resets
approval. The source binds to the exact world digest.

Use the operator CLI:

    python -m skeleton world-economy --store ./private-worlds propose \
      --world-id harbor --prompt "Original supplies" --resource-id supplies \
      --name Supplies --initial 1 --capacity 5 --choice-id pursue_goal \
      --cost 1 --gain 0

Use the returned JSON with \`save --create --source-json JSON\`, then
\`approve --expected-digest SHA --review-note "Reviewed original economy."\`.
\`compile --expected-digest APPROVED_SHA\` emits a source-verified offline
HTML5 playable, a typed engine recipe, and a digest-bound receipt. \`verify\`
reconstructs all outputs under the world lease and rejects tampering. \`player
--slot SLOT\` replays an existing canonical saved session against the reviewed
economy. \`editor --expected-digest SHA\` emits a CSP-bound offline UI whose
exports are always unapproved.

A deterministic bounded graph exploration proves every ending reachable,
every reachable non-ending state playable, every authored effect exercised, and
every resource balance within capacity. Unaffordable and overflow transitions
are disabled. State explosion fails closed at 4096 states. The browser uses
textContent and a SHA-256 CSP; it does not fetch external assets. The engine
recipe is a source-level handoff, not a built binary or device qualification.

Jeeves read-only tools: \`world.economy_propose_preview\`,
\`world.economy_preview\`, \`world.economy_player\`. Tool calls cannot approve,
publish or mutate source. The CLI is the sole operator write authority.

Security regression coverage includes stale world leases, duplicate resource
identifiers, integer and capacity bounds, stale optimistic edits, unreviewed
compile refusal, forged approval, symlinked output, tampering, and replay of
resource-gated choices. Focused tests and exact-head CI must pass before merge.
