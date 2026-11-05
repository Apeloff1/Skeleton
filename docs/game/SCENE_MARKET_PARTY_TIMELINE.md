# Cooperative market replay timeline and safe offline forks

The production timeline reads the canonical party journal and replays every
turn from its source. No event can be accepted solely because a receipt hash
looks correct. Every seek replays canonical role checks, movement, collision,
trading, crafting and delivery through the existing market reducer.

## Commands

`python -m skeleton scene-market-party-timeline demo` forks the original
cooperative campaign at the midpoint and verifies its earned terminal save.

`python -m skeleton scene-market-party-timeline page --session-json '<checkpoint>' --start 0 --limit 16`
returns up to 32 replayed events, their actors, legal actions, state/save
digests, market deltas, round, phase, next cursor and a portable checkpoint
checksum. A page never claims a globally complete journal unless
`has_more` is false.

`python -m skeleton scene-market-party-timeline seek --session-json '<checkpoint>' --sequence 4`
reconstructs the exact four-turn checkpoint and verifies export/import.

`python -m skeleton scene-market-party-timeline fork --session-json '<checkpoint>' --sequence 4 --turns-json '[...]'`
creates a separate offline playthrough from that boundary. It does not
overwrite the original, merge saves, grant items, or impersonate a player.
The portable bundle can be imported by the canonical party runtime.
`verify-page` and `verify-fork` recompute the entire receipt from
the supplied checkpoint and reject altered or stale results.

Inputs are bounded by the existing gameplay size and turn limits. Boolean
indexes, negative indexes, oversized pages, invalid actors, unauthorized
roles, illegal trades, and corrupted checkpoint lineage fail closed.
Checksums demonstrate deterministic replay integrity, not identity
authentication, device qualification or multiplayer network authority.
