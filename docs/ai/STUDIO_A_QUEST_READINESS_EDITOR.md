# Studio A — offline quest readiness budget editor

This interactive HTML editor is an original, offline, CSP-hashed interface
for changing the **bounded exploration budget**, not game canon or release
authority. It displays the current source-replayed proof and exports a
strictly typed JSON request with project, source and empty-session leases.

Use `python -m scripts.studio_quest_readiness_cli --project PROJECT
--expected-source QUEST_SHA --expected-session SESSION_SHA --prompt
--editor-preview` to produce the HTML. Save it locally, open in a browser,
edit the two bounded integer fields and export `quest_readiness_budget.json`.

The exported file must be private (0600 on POSIX) before import. Recompile
with `--editor-export FILE` on the same readiness CLI, optionally
`--playable` or `--publish DIRECTORY`. Alternatively, feed the exact
same export to `scripts.studio_quest_readiness_playable_cli` for the real
catalog HTML5 bundle. The importer independently rechecks canonical source,
initial session, project identity, budget limits and both proof owners.

The HTML cannot invoke network APIs, submit forms, write arbitrary paths,
change quest stage graphs or claim native qualification. The JSON importer
rejects duplicate keys, nonfinite values, symlinks, hardlinks, FIFOs,
world-readable files, stale leases and extra authority fields.

Tests: `tests/test_studio_quest_readiness_editor.py`.
