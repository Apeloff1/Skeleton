# Original salvage championship — two-round playable vertical

The championship composes independently replay-verified salvage rounds using the
same canonical Lantern Quay movement, collision, crafting, NPC and earned-ending
contracts. Round-specific authored boards define finite salvage sites, cargo,
hull, tide, minimum earned rewards and minimum surviving hull. An unearned round
cannot be added to the season; no scores, inventory or currency are fabricated.

## Commands

`python -m scripts.game.harbor_salvage_season --help` exposes:
`start`, `next`, `verify`, `at`, `compare`, `fast-forward`, `live`,
`author`, `verify-author`, `package`, `verify-package`, `play`,
`verify-play`, `leaderboard`, `verify-leaderboard`, `accept`,
`verify-accept`.

`start` emits an initial JSON save. `next --save save.json --actions
round.json --expected-tip DIGEST` adds a genuinely completed round only when
the tip matches. `at --save save.json --index 1` recreates a historical
checkpoint, and `compare`/`fast-forward` reject divergent histories.
`author --edits edits.json --expected-board-digest DIGEST` applies validated
round-rule or nested salvage-board edits, optionally replaying all existing
rounds with `--preview-rounds rounds.json`.

`package` exports source and authored season, `play --package package.json
--rounds rounds.json --require-complete` runs both rounds offline, and
`verify-play` independently rebuilds the source-bound package play.
`leaderboard --entries entries.json` ranks verified scores deterministically
without trusting submitted totals. `accept --rounds rounds.json` requires
complete package play, scoreboard and replay custody. All outputs are bounded
canonical JSON to stdout for deliberate redirection.

## Canonical fixture and end-to-end path

`harbor_lantern_quay_salvage_season.json` defines two original rounds:
recover the wrecked skiff and tide cache, then return for a final tide-cache
recovery. Both rounds require genuine dock offloading, crafted cargo delivery,
and a signal-rescue ending. The example earned championship score is 36
(points + recovered salvage value + surviving hull across both rounds).

Save digests and package digests detect mutation but are not signatures.
The user-provided source and package must be treated as untrusted data; no
network, dynamic code or filesystem extraction is performed. Windows/device
qualification, production asset rights and exact-head CI remain separate holds.
