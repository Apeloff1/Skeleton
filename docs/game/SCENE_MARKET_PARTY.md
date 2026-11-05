# Cooperative market party — source to playable export

The party layer reuses the canonical market reducer for every pickup, tile
collision, finite-stock purchase, craft and one-shot delivery. It adds ordered
player turns, role permissions, optional passes and individual contribution
receipts. Neither a pass nor a role edit mints currency or goods.

Run `python -m skeleton scene-market-party demo` for a full cooperative
campaign. Run `python -m skeleton scene-market-party accept` to verify a
mid-campaign checkpoint, portable export/import, exact replay and victory.
`scene-market-party-author demo` produces a source-digest-fenced role edit
with a playable preview and replay-verifiable receipt.
`scene-market-party-play demo` produces a complete portable session.

For custom content, supply `scene-market-party simulate --source-json JSON
--turns-json JSON`. The source is a strict `skeleton.scene_market_party.v1`
object with `market_source` and 2–4 ordered `players`; each player has
a unique `player_id` and a nonempty set of roles. All four production roles
must be represented. `navigator` controls tile movement/collection/travel,
`merchant` buys, `artisan` crafts and `courier` delivers. A turn object
is `{"player_id":"rowan","action":{"kind":"pass"}}` or a canonical
market action. The actor must match the current player. The journal is
bounded, checksummed and fully replayed from authored source.

`scene-market-party-play play --source-json JSON` accepts one JSON action
per line from the current player. It prints legal actor/roles, shared earned
resources and periodic full checkpoints; EOF or three rejected commands
emits a replayable checkpoint before failing closed. Use `--session-json`
to restart, optionally with `--source-digest` pinned to a trusted source.
No terminal result is inferred from an incomplete or budget-exhausted run.

`scene-market-party export --session-json JSON` and `import --bundle-json
JSON` provide portable integrity-checked, replay-verified saves. Checksums
detect corruption and accidental tampering; they do not authenticate authors
or grant remote-player authority. Source changes intentionally invalidate old
checkpoints; the editor never rewrites a saved session in place.

Focused tests:
`pytest -q skeleton/testing/test_scene_market_party.py
skeleton/testing/test_scene_market_party_author.py
skeleton/testing/test_scene_market_party_interactive.py`.

Release remains held until those tests and all exact-head CI, provenance,
security, original-content and consumer acceptance checks pass.

The read-only `scene-market-party-board demo` command enumerates the current
player's replay-verified legal actions. `scene-market-party-board inspect
--session-json JSON` rejects forged checkpoints and never changes the
original session. The interactive player emits the same legal-action board
before each turn. This is a local gameplay aid, not a network permission grant.
