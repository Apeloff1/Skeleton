# Combat campaign branching — original offline production vertical

The installed command `python -m skeleton combat-campaign-player` now exposes
`branch-demo`, `branch-evaluate`, `branch-verify`, `branch-choose`,
`branch-export`, `branch-import` and `branch-accept`. The dedicated module
can also run `python -m skeleton.game.gameplay.combat_campaign_branches accept`.

## Source → playable choices → save/replay → export

A verified, active player campaign checkpoint is the only branch root. Candidate
plans are strictly typed combat actions, capped at eight candidates, 32 actions
per candidate and 96 total actions. The canonical hero turn reducer applies
every action; blocked moves yield an explicit non-committable result. The source,
checkpoint, actions, outcomes and heuristic selection are re-evaluated by
`verify_branches`, including when an attacker recomputes a JSON checksum.

`choose_branch` accepts only a replayed legal candidate and returns an ordinary
campaign save. It independently verifies the portable campaign export/import.
`export_branches` and `import_branches` bind a complete offline decision report
to its source and checkpoint digests. Ranking favors a proved win, then earned
currency and surviving hero health; it does **not** claim global optimality.

## User-facing acceptance

`branch-accept` plays the original two-encounter Lantern Harbor campaign,
branches after an earned hero turn, compares finishing the patrol against
guarding, selects the earned victory, verifies ordinary saves and portable
exports, and returns a bounded checksum-bearing receipt. All author content is
JSON data; no scripts, filesystem operations, network calls, or provider
credentials are executed. This is offline replay evidence, not multiplayer
actor authentication, device certification, or release qualification.

The focused test module is
`skeleton/testing/test_combat_campaign_branches.py`; required exact-head
security, hygiene, E2E and merge gates must still pass before promotion.
