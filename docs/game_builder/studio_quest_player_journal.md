# Studio A — canonical quest player journal

The player journal is a real source-bound authored edit flow, not an AI
invented playthrough. Jeeves can draft a note from each **actually replayed**
stage choice and its authored reward. The operator edits that note in a
CSP-restricted offline HTML page and exports a typed JSON plan. The CLI
validates the exact current quest source, completed stages, and initial
session lease before compiling the note receipt.

Plan schema: `skeleton.game_builder.studio_quest_player_journal_plan.v1`.
Fields: `schema`, `actions` (canonical [stage, alternative] pairs),
`entries` ([stage_id, note] records) and `target_ending`.
Only completed stages may receive notes. No duplicate stages, control
characters, oversized notes, or invented external evidence are accepted.

Run `python -m scripts.studio_quest_player_journal_cli --project <id>
--expected-source <64-hex> --expected-session <64-hex> --plan-file plan.json`.
Use `--editor-html` to edit and export a new plan, `--publish <private-dir>`
for exclusive fsynced publication, or `--restore <private-dir>` for
descriptor-anchored private read and exact-source replay. `--handoff`
requires the target ending to be sandbox-eligible. The handoff binds
the verified journal digest to the canonical quest session, but it does
**not** certify native gameplay, external evidence, rights, or release.

Focused regression: `pytest -q tests/test_studio_quest_player_journal.py`.
