# Studio A — Original quest choice consequence comparison

This user-facing vertical compares two independently replayed authored quest
histories against one exact original source. It never invents rewards or endings.

Use python -m scripts.studio_quest_consequence_cli with --project PROJECT,
--expected-source SOURCE_SHA, --expected-session SESSION_SHA, and --prompt.
The prompt selects the first valid authored root alternative pair.

For editing, supply --authoring-file PATH containing private 0600 JSON with
exactly baseline_actions and candidate_actions lists of [stage, alternative].
The CLI verifies both traces against the original authored quest source.

Use --html-preview for inert escaped CSP HTML. Use --publish DIRECTORY for
immutable private source-bound receipts and --restore DIRECTORY to replay.
Use --playable only if both branches have an authored sandbox ending; the
result explicitly denies native gameplay and release certification.

Jeeves exposes studio_original_quest_consequences through a strictly typed,
read-only request schema and explicit authorization. The adapter never writes
to a project or grants new privileges.

Focused regression: pytest -q tests/test_studio_quest_consequence_diff.py

The tests cover deterministic consequences, malformed edits, source leases,
tampering, type substitution, HTML escaping, private persistence, duplicate
JSON, symlinks, directory fsync rollback and typed Jeeves authorization.
