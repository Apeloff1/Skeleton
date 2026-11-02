# Source-leased original quest save migration

This Studio A vertical migrates a canonical quest save across an operator-
authored, canon-reviewed prose revision. It uses the existing
`preview_canon_revision` editor/compiler, the immutable quest DAG and
canonical replay on both old and revised source. It never silently rewrites a
player choice when the authored alternative text has changed.

A typed plan contains `revision_request`, `actions`, `remaps` and
`target_ending`. Each explicit remap must name the exact selected stage,
old choice and new choice **at the same authored alternative index**.
A missing remap stops at the longest replayable prefix, preserves the
dropped suffix as diagnostic evidence and blocks playable handoff.
A forged remap, changed protected quest structure, stale source/session lease,
unknown ending, unverified original ending or revised ending also blocks it.

`python -m scripts.studio_quest_revision_migration_cli --project PROJECT
--expected-source QUEST_SHA256 --expected-session INITIAL_SHA256
--plan-file PRIVATE_JSON --publish DIRECTORY` creates a private,
exclusive migration receipt. `--restore DIRECTORY` replays it against the
current canonical source; `--handoff` emits a verified **sandbox**
revised-HTML digest only when the complete migration and ending witness pass.

The Jeeves world-tool registry exposes
`studio_original_quest_revision_migration` as an **authoring** tool:
out-of-band `--allow-authoring` is required. No source lease, rights proof,
native game qualification or release gate is bypassed.

Focused regression:
`pytest -q tests/test_studio_quest_revision_migration.py`.

## Accessible offline migration editor

`--editor-preview` renders a CSP-hashed, network-disabled HTML editor for
explicit remaps and the reviewed source revision. The browser exports typed
JSON only. Publish a baseline first, then pass `--editor-export PRIVATE_JSON
--baseline DIRECTORY` with the exact old quest-source and initial-session
leases. The CLI rejects stale baselines, duplicate JSON keys, symlinks,
world-readable files and oversized exports; it recompiles both canonical
replays before allowing any playable handoff. The HTML never grants authority.
