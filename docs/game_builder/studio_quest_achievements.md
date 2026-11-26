# Original quest achievements (Studio A)

The typed Jeeves tool \`studio_original_quest_achievements\` drafts original
achievement definitions from a source-bound quest DAG. It does not grant
external platform achievements, coins, payment value or release approval.

## End-user flow

Load an original blueprint, compile its \`compile_quest_program\` and
\`start_quest\` digests, then ask Jeeves to draft achievements for a canonical
action sequence and target ending. Tool routing requires explicit out-of-band
authoring authorization. Edit the returned private plan: IDs must be unique,
stage references must exist, optional required choices must belong to the
stage, and optional required effect tokens must be authored by that choice.
Titles, descriptions and points (1..100) are editable.

Run \`python -m scripts.studio_quest_achievements_cli --project
studio_puzzle_expedition_copper_mesa --expected-source DIGEST
--expected-session DIGEST --plan-file /private/achievements.json\`.
Use \`--editor-html\` to export a CSP-hashed offline editor for titles,
\`--publish /private/directory\` for an exclusive private receipt,
\`--restore /private/directory\` to verify it, and \`--handoff\` to
produce a deterministic display/unlock payload for the playable builder.

## Verification and limits

Only canonical replay earns a sandbox milestone. Authored text cannot mint
session choices, change choice effects, award external accounts or alter ending
predicates. Source and session digests fence edits; receipt replay rejects
tampering. Private input is bounded, descriptor-anchored, symlink-resistant
and duplicate-key rejecting. Exclusive 0600 output is fsynced with rollback.
HTML escapes authored strings and disables network access. Regression:
\`pytest tests/test_studio_quest_achievements.py\`. Native gameplay,
device acceptance, external awards and release certification remain unproven.
