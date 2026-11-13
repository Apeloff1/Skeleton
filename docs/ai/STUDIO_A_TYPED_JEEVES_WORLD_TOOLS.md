# Studio A — typed read-only Jeeves world tools

`python -m skeleton world-tools --store PRIVATE manifest` returns the static
versioned tool registry. `invoke --request-json JSON` accepts a strict
`jeeves.world.tool_request.v1` envelope containing `schema`, `tool`,
`world_id` and exact typed `args`.

Supported tools include `world.proof`, `factions.propose_preview`,
`factions.inspect`, `factions.player`, `evidence.propose_preview`,
`evidence.inspect` and `evidence.player`. Preview results are original-
author typed proposals, not unverified claims of autonomous generation.
Actual player views come from durable canonical sessions. The returned
result has a deterministic digest and explicit `persisted: false` and
`authority: read_only_no_mutation` markers.

No model-callable tool can approve, edit, compile, or write. An operator must
use `world-factions` or `world-evidence` with exact digest leases and
explicit review. Unknown tool names, surplus arguments, arbitrary paths and
unearned player choices fail closed. This is a typed integration boundary
for future Jeeves planners, not a claim that a provider or UI model runtime
has been configured or release-certified.
