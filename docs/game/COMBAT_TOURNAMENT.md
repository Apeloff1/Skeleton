# Offline combat tournament (Studio B)

The four-entrant bracket is a complete source→runtime→checkpoint→replay→portable
export feature. It reuses canonical `turn_combat` for every turn and
`tactical_policy` for offline decisions. It does not execute authored scripts,
invoke an LLM, or accept a client-reported winner. Every persisted bracket
reconstructs its three canonical duels before it can resume or export.

## Play

```sh
python -m skeleton combat-tournament demo
python -m skeleton combat-tournament simulate --source-json '{"schema_version":"skeleton.combat_tournament.v1","world_id":"lantern_harbor","tournament_id":"four_tides","match_turn_limit":32,"entrants":[{"id":"lantern_scout","max_hp":14,"attack":6,"defense":2,"speed":5},{"id":"marsh_warden","max_hp":12,"attack":4,"defense":2,"speed":3},{"id":"harbor_guard","max_hp":13,"attack":5,"defense":2,"speed":4},{"id":"tide_runner","max_hp":11,"attack":4,"defense":1,"speed":6}]}'
```

Use `advance --session-json` to play one match, `resume --session-json`
to complete a verified partial bracket, and `verify --session-json` to
reconstruct every match. `export --session-json` produces a bounded portable
bundle; `import --bundle-json` validates checksum, source identity and the
entire replay. CLI JSON inputs and outputs are bounded to 128 KiB.

The first two duels pair entrants 0–1 and 2–3. The final pairs their
verified winners. Each duel resets actor HP to its authored baseline; there
are no fabricated bonuses or transfers between rounds. A timed-out duel
ends the bracket as a draw, never silently selects a champion. Source
digests prevent accidental resume against edited content but are **not**
cryptographic proof of trusted authorship. The application must separately
authorize the original source.

Acceptance: `python -m pytest -q skeleton/testing/test_combat_tournament.py`.
Require exact-head CI/security and independent gameplay review before release.
