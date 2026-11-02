# Lantern Quay mission-board production vertical

The authored mission board is stored in `skeleton/game/gameplay/fixtures/harbor_lantern_quay_missions.json`.
It binds to the original playable world's ID, checks mission prerequisites in source
order, and rejects cycles, duplicate IDs, unknown items, blocked destinations,
oversized boards, impossible objective types and noncanonical objective fields.

Progress is **earned by actual canonical player actions**. A mission's objectives
are credited only after its prerequisites were complete *before* the current
tick. Gathering, crafting, trading, movement, cargo delivery and final player
choices are evaluated against the same transitions that power interactive play.
Per-mission deadlines and the global gameplay tick budget remain enforced.

The `mission-report` CLI reads a portable gameplay bundle and mission board,
replays the complete source-bound action history, and writes a canonical report
with a per-tick hash-linked mission journal. `verify-mission-report` does not
trust saved points or mission flags: it independently recomputes the entire
journal from the embedded world and verified gameplay event chain.

`solve-missions` executes the canonical bounded campaign planner and refuses
to report mission success unless **every authored objective** is earned.
For the sample board, the signal ending earns salvage (10), workshop (20),
and dispatch (30) points. The shelter ending is a legitimate game ending but
cannot earn the signal-only dispatch mission.

## Example

```sh
python -m scripts.game.harbor_crafting demo --require-win > /tmp/lantern-bundle.json
python -m scripts.game.harbor_crafting mission-report --bundle /tmp/lantern-bundle.json --require-all > /tmp/lantern-missions.json
python -m scripts.game.harbor_crafting verify-mission-report --report /tmp/lantern-missions.json --require-all
python -m scripts.game.harbor_crafting solve-missions --choice signal --require-all
```

These portable JSON digests provide tamper evidence and replay consistency,
not authenticated authorship or a signed distribution. No network, dynamic
execution, paid assets, device qualification or release claim is involved.

## Authored mission revisions and branching acceptance

`author-missions --missions BOARD --source WORLD --mission-edits EDITS
--expected-board-digest DIGEST` applies bounded, allowlisted optimistic edits
to the authored mission board. An optional `--preview-bundle BUNDLE`
generates a real replay-derived quest preview. The portable revision records
the source, original board, operations, resulting board and verified preview.
`verify-mission-author --mission-revision REVISION` replays the edit from
its original source, rejecting stale leases, reordered prerequisites,
duplicate edit targets, forged previews and altered final boards.

`mission-checkpoint --bundle SAVE --tick N` reconstructs an actual historical
gameplay checkpoint and derives the quest journal for that prefix.
`mission-resume --bundle SAVE --actions ACTIONS
--expected-terminal-digest DIGEST` uses the existing CAS-protected save
continuation and then derives the complete new quest journal. Both can use
`--require-all` to reject unearned completion.

`mission-portfolio --bundle PORTFOLIO` accepts a canonical verified game
branch portfolio, independently verifies every branch's save and derives
separate mission completion and earned points for each ending.
`verify-mission-portfolio --report REPORT` reconstructs all source,
branch and mission results. A shelter ending cannot claim signal-only
dispatch points. A scorecard is a deterministic gameplay consequence,
not an authenticated leaderboard or financial reward.

## Deterministic edit consequences

`compare-mission-revision --mission-revision REVISION --bundle BUNDLE`
evaluates the original and edited mission boards against the *same*
verified gameplay save. It exports two independently replayable quest journals,
the exact change in earned points, and mission IDs newly gained or lost.
`verify-mission-comparison --comparison COMPARISON` replays both sides
and rejects fabricated scores, tampered rules, mismatched source worlds,
altered save events, and forged before/after consequences.

This is a production authoring preview, not a claim that changing a
mission board rewrites the original gameplay save. A mission may be
lost after an edit even though the underlying player's earned game
ending remains unchanged.
