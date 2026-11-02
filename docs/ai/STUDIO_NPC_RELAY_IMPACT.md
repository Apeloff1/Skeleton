# NPC knowledge relay counterfactual impact

This is an original, source-bound Studio A vertical. An operator first uses the existing
NPC knowledge relay editor to produce two private canonical receipts. The impact
compiler independently replays both against the same original catalog source,
quest session, rendezvous and knowledge exchange. It reports added, removed,
modified, blocked and delivered routes. The summary and offline HTML review
omit NPC prose; the full private JSON custody receipt retains both original
source-bound inputs so that exact replay remains possible.

The `affected_scene_ids` list identifies authored scenes requiring review. A
`delivery_regressions` count is calculated only from proven sandbox delivery
transitions. No NPC speech, native cognition, model inference, consumer/device
readiness or release certification is claimed.

Run `python -m scripts.studio_npc_relay_impact_cli --project PROJECT
--expected-source SHA256 --baseline PRIVATE_BASELINE_JSON
--candidate PRIVATE_CANDIDATE_JSON --prompt --publish PRIVATE_DIRECTORY`
with existing private files and a pre-existing owner-only directory. Restore
with `--restore PRIVATE_DIRECTORY` and the same source digest. Publication
is exclusive and fsynced; overwrites, symlinks, stale leases, duplicate JSON
keys and mismatched source/session/exchange receipts fail closed.

The registered Jeeves tool is `studio_original_npc_relay_impact`, with
`skeleton.jeeves.studio_npc_relay_impact_request.v1` arguments. Tool calls
are read-only and operator-gated. The optional playable manifest is available
only when both source-replayed relays independently qualify and no proven
delivery is lost; it refers to the canonical HTML5 quest bundle, not native
NPC integration. The bounded router may reject large receipts; use the CLI
for larger private comparisons rather than weakening its request budget.

Use `--render-review PRIVATE_DIRECTORY` to write a separate, exclusive,
script-free CSP-restricted HTML review containing changed route identifiers,
status transitions, proof hashes, and source/impact digests. The review never
claims native NPC speech or exposes authored NPC dialogue prose.
