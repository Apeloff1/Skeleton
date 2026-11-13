# Transactional offline combat league editor

Entry: python -m skeleton combat-league-author demo

Author the original eight-entrant league without bypassing the canonical
gameplay engine. The editor accepts source-digest-leased stat changes,
entrant renaming, season length and match turn-limit changes. Each edit
produces a replayable journal event with before/after source digests.
Stale edits, duplicate entrant IDs, invalid stat types and budget overflow
fail closed; the input source remains unchanged.

CLI: demo, new --source-json JSON, edit --author-json JSON --edit-json JSON,
verify --author-json JSON, preview --author-json JSON,
export --author-json JSON, import --bundle-json JSON.
Preview runs the complete canonical league and returns standings plus
verified game save. Export/import reconstructs the complete edit history.
A hash detects corruption but does not authenticate an external creator.

Example edit JSON: {"kind":"set_stat","entrant_id":"amber_guard",
"field":"attack","value":8,"expected_source_digest":"<64-hex-current>"}

Bounds: 32 edits per author journal, 2 MiB per JSON value, canonical
eight-entrant and four-round league limits. Regression:
python -m pytest skeleton/testing/test_combat_league_author.py -q
