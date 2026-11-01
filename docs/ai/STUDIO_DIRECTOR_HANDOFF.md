# Original offline playable director handoff — Studio A

This is an integrated original game creation flow, not a design catalog.
An operator submits a typed scene schedule and explicit source-to-visual
asset recipe bindings, with exact canon, visual and quest-session digests.

The canonical scene scheduler verifies NPC turnaround and quest causality.
The canonical asset binding compiler verifies that every scene asset and
interactive object resolves to a registered original design recipe. The
existing game builder compiles an actual standalone offline HTML5 game and
replays a winning trace. The director verifies all three identities and
creates a deterministic ZIP containing `index.html`, `scene_schedule.json`,
`scene_asset_bindings.json`, and `director_manifest.json`, with per-file
SHA-256 receipts and a deterministic ZIP SHA-256.

CLI: `python -m scripts.studio_director_handoff_cli --project PROJECT
--expected-source CANON_DIGEST --expected-visual VISUAL_DIGEST
--schedule SCHEDULE_JSON --assignments ASSIGNMENTS_JSON
--publish-directory EXISTING_DIR`

A separate `--verify-directory` re-compiles from the same exact source and
compares the published ZIP byte-for-byte. Publication is private, exclusive,
atomic and fsynced. Existing bundles cannot be overwritten. The static
Jeeves `studio_original_director_handoff` tool returns only the manifest
and does not write to disk or grant itself publication authority.

The playable HTML5 maze is real, but original NPC dialogues, temporal
duration, visual design recipes and native genre runtime are **not**
implemented by that HTML5 compiler. All unverified claims remain false.
