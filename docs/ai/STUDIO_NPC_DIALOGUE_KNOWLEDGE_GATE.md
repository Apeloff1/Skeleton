# Source-bound NPC dialogue knowledge gate

This Studio A feature binds a typed knowledge fact and its authored NPC scene
to a replay-verified relay proof. It rejects unknown facts, mismatched NPCs,
duplicate gates, stale proof digests, noncanonical receipts and unauthorized
execution. An NPC's original scene must be **available**, not locked or already
completed, before its knowledge can be previewed. No model guesses at lore.

Operators can propose exact gates from a canonical relay receipt, edit the
typed `gates` list in a private JSON file, recompile and publish an immutable
private receipt, then restore and replay it. Each gate names `fact_id`,
`recipient_scene_id`, `target_scene_id` and
`expected_relay_proof_digest`. The compiler independently replays both
the original quest staging and the causal knowledge relay.

`python -m scripts.studio_npc_dialogue_knowledge_gate_cli --project PROJECT
--expected-source SHA256 --relay-file PRIVATE_RELAY_JSON --prompt
--publish PRIVATE_DIRECTORY`

For edited gates replace `--prompt` with `--authoring-file PRIVATE_JSON`.
For a stored receipt use `--restore PRIVATE_DIRECTORY`. The directory must
exist and be private; publication never overwrites, and restore rejects
symlinks, public modes, duplicate JSON keys and stale source digests.

Jeeves registers `studio_original_npc_dialogue_knowledge_gate` with schema
`skeleton.jeeves.studio_npc_dialogue_knowledge_gate_request.v1`. The
read-only tool is operator-gated and bounded. A playable manifest is
available only when every gate is allowed and the underlying relay qualifies
for canonical HTML5 handoff. Native NPC memory, spoken dialogue, physical
interaction and release qualification remain explicitly unverified.

An offline, source-leased HTML editor is available with `--render-editor
PRIVATE_DIRECTORY`. Its embedded script is CSP-hash pinned and only exports
a typed JSON edit, never commits gameplay itself. Recompile that export with
`--editor-export-file PRIVATE_JSON --baseline-gate-file PRIVATE_BASELINE_GATE
--relay-file PRIVATE_RELAY`. The importer checks private file custody,
unique JSON keys, project/source/session/relay identity, baseline gate digest,
and bounded authoring before replaying the revised gate. No overwrite occurs.
