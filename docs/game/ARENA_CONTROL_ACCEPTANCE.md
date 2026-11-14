# End-to-End Offline Capture-Game Acceptance

`python -m skeleton arena-control-accept demo` exercises an actual playable
vertical rather than merely checking a source inventory. It transactionally
edits the original Lantern Harbor beacon game, verifies a replayable tactical
solver witness, feeds the player-owned decisions into the interactive JSON-line
game, checks canonical opponent actions and capture scores, exports and
reimports a portable control checkpoint, then runs the same earned victory
through a one-stage campaign with replay-verified currency.

`accept --source-json ... --team ... --operations-json ...
--preview-actions-json ... [--max-nodes 256]` runs an authored version.
`verify --receipt-json ...` reexecutes the entire sequence from original
source and rejects altered editor receipts, solver actions, interactive
transcripts, campaign rewards, save lineage or portable manifests.

A successful result is labeled `passed_offline_gameplay_witness` and is
not a release certificate. A bounded search with no witness returns
`unproven_within_budget`, without claiming the game is impossible or
qualified. No network calls, external assets or model-provider dependencies
are needed. Device rendering, graphics UI, licensing and performance remain
separate release holds.
