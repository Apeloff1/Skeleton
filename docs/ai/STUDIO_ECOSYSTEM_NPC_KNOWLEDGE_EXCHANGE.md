# NPC knowledge exchange through verified meetings

This Studio A vertical composes three independent canonical owners:
source-authored NPC knowledge cues, source-replayed NPC rendezvous occupancy,
and the authored temporal/quest timeline. It does not invent testimony.

Use \`scripts/studio_npc_knowledge_exchange_cli.py\` with
\`--project\`, \`--expected-source\`, \`--rendezvous\`, \`--knowledge\`,
and exactly one of \`--prompt\` or \`--authoring\`. Authoring is
\`{"bindings":[{"fact_id":"...","recipient_scene_id":"...",
"meeting_id":"..."}]}\`. Every binding must name a canonical knowledge
reveal and a rendezvous between its actual source and recipient NPCs.

A transfer is delivered only if the original knowledge cue was earned in
canonical quest replay and the accepted meeting occurs after the source
scene and before the recipient scene. Otherwise the result is pending or
blocked; unearned text is not exposed. The CLI can publish an immutable,
private fsynced receipt, restore with source replay, or produce a
CSP-hashed offline editor via \`--editor-directory\`. Export from the
editor and recompile with \`--import-authoring\` and
\`--baseline-exchange\`; a stale digest is rejected.

The static Jeeves router exposes
\`studio_original_npc_knowledge_exchange\`. Handoff requires every
binding to be delivered and all rendezvous/travel proofs to pass. It
includes the canonical HTML5 quest bundle only: native speech,
knowledge transfer rendering, device readiness and release acceptance
remain explicitly unqualified.

Focused regression: \`pytest -q tests/test_studio_ecosystem_npc_knowledge_exchange.py\`.
