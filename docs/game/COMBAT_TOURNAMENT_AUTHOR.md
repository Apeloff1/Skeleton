# Offline tournament authoring

The tournament builder supports transactional edits to a complete original
four-entrant tournament. `new` normalizes source; `edit` accepts exactly
one source-digest-leased change; `verify` reconstructs all edit receipts;
`preview` compiles the edited source into a playable, replay-verified bracket.

```sh
python -m skeleton tournament-author demo
python -m skeleton tournament-author new --source-json "$SOURCE"
python -m skeleton tournament-author edit --session-json "$EDITOR_SAVE" --edit-json "$EDIT"
python -m skeleton tournament-author verify --session-json "$EDITOR_SAVE"
python -m skeleton tournament-author preview --session-json "$EDITOR_SAVE"
```

Edits are `set_stat` (bounded max_hp, attack, defense or speed),
`swap_seeds` (two distinct existing entrant IDs) and `set_turn_limit`
(1..64). Every edit includes `expected_source_digest` matching the exact
current authored source. Stale edits, unknown actors, malformed values,
extra fields and forged receipts fail without changing prior snapshots.
The editor retains the original source and replays up to 64 edits.

Preview uses canonical `combat_tournament.finish_tournament` and emits
the verified game session, author receipt and result receipt. The builder
never grants gameplay currency, writes arbitrary files or executes scripts.
Checksums are integrity evidence only, not an authorization layer.

Acceptance: `python -m pytest -q skeleton/testing/test_combat_tournament_author.py`.
Require focused acceptance, exact-head CI and independent review before release.
