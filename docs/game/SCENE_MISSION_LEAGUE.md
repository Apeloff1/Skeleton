# Offline scene mission league

The player-facing command is `python -m skeleton scene-mission-league`.
It creates a deterministic local competition from *real completed*
`scene-mission` sessions, not a service or user identity provider.

## Playable path

Run `python -m skeleton scene-mission-league demo` to produce two original
harbor missions with different player choices. Use `inspect --league-json JSON`
to see score order. The score is computed from earned mission objectives,
reputation, canonical scene victory or defeat and action count; players cannot
submit a claimed score. Ranking breaks ties by fewer actions and attempt ID.

For custom worlds use `new --source-json JSON --rules-json JSON`.
Play a mission with `scene-mission` or `scene-mission-play` until finished.
Then call `submit --league-json JSON --session-json JSON --attempt-id ID
--expected-digest DIGEST`. The digest is a compare-and-swap precondition:
stale local writers must reload the latest league and retry. An attempt must
be terminal, source-matched, replay-verifiable, distinct by attempt ID and
distinct by resulting state digest. A replay is not a person identifier.

`verify`, `export` and `import` re-run every canonical mission session
and recompute every score. Portable export uses a checksum for accidental
corruption detection. It is **not** a signature or proof of authorship.
Untrusted league JSON must not be interpreted as authenticated tournament
results. No remote storage, scripts, plugins, filesystem writes, provider
calls or networking are required.

## Resource and failure contracts

The source must satisfy the canonical mission schema and scoring rules
must use exact fields and bounded integers. League entries are capped at 8,
the JSON payload at 8 MiB, and individual sessions at the canonical
2 MiB budget. Replayed rewards cannot be inserted without legal source-bound
actions. Duplicate entries, malformed scores, stale revision preconditions,
unearned endings, changed sources, unknown keys, oversized JSON and invalid
replay journals fail closed with exit status 2. Original examples are homebrew.

This is an offline score competition, not anti-cheat attestation. A local
author can alter a source and replay a new valid game; external authenticity
requires an independently trusted source digest or signature policy.
