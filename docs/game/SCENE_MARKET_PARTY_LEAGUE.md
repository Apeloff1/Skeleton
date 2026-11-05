# Replay-verified cooperative market league

Run `python -m skeleton scene-market-party-league accept` to play an
original cooperative market campaign, earn victory, record an attempt,
round-trip a portable league export and verify a deterministic ranking.

The league uses the canonical market party reducer, not an independent
economy. Each recorded attempt must have an exact matching authored source,
a replay-verifiable journal and an earned winning phase. Credits, goods,
role contributions, turn counts and passes come from the verified session.
The scoring weights are versioned authored data, bounded to [-1000,1000].
Victory must have a positive weight; penalties cannot reward extra turns
or passes. No credits, items or achievements are created by scoring.

Commands: `create --source-json JSON [--rules-json JSON]`,
`record --league-json JSON --attempt-id ID --checkpoint-json JSON
--expected-revision N`, `rank --league-json JSON`, `verify`, `export`
and `import`. Use `demo` or `accept` for a playable original example.

Every attempt is append-only and uses an optimistic revision lease. Duplicate
attempt IDs, stale revisions, source mismatches, forged rewards and edited
journal receipts fail closed. Equal scores break ties by fewer turns, then
lexicographic attempt ID. Sixteen attempts and a two-MiB serialized budget
bound offline processing. Exports are integrity checks, not signatures;
this is not a hosted competitive anti-cheat or identity authority.
