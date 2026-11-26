# Replay-verified combat supply checkpoint timeline

This Studio B production vertical extends the original Lantern Harbor
combat-supply game. The authoritative engine determines battles, health,
earned currency, medkit and ward inventory. The timeline derives these
values from replayed commands and refuses conflicting accounting.

## User-reachable CLI

`python -m skeleton combat-supply-timeline demo` runs the original
two-encounter patrol and returns a replay-derived economic/gameplay timeline.
`timeline --session-json '<save>'` reports each canonical state transition.
`checkpoint --session-json '<save>' --index N` restores the exact prefix.
`fork --session-json '<save>' --index N --actions-json '[...]'` creates
a playable branch from an earned checkpoint. `verify-fork --fork-json`
replays origin and suffix, while `compare --left-json --right-json`
compares source-compatible branches and their common prefix.
`package --session-json` and `import --package-json` round-trip a
bounded, no-extraction portable save with its replay-derived timeline.

The only suffix commands are canonical fight/buy/use. Branches cannot
inherit rewards from abandoned future actions. Malformed source, invalid
index, oversized JSON, noncanonical command, unearned purchase, altered
combat result, forged inventory and mismatched package fail closed.

Checksums detect changes relative to the supplied authored source; they
are **not** signatures, authorization, provenance, ownership or permission
to execute content. Trust the source acquisition channel separately.

Focused test:
`python -m pytest skeleton/testing/test_combat_campaign_supply_timeline.py -q`.
Also run existing supply author, solver and acceptance tests. Required
exact-head CI and consumer/device qualification remain separate holds.
