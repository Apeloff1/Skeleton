# Transactional Lantern Quay championship authoring

Use `season-author` to revise an authored championship with a canonical
source digest and season digest as compare-and-swap leases. All edits are
validated as a transaction, and the command returns a portable, replayable
revision; it does not mutate the source files.

Accepted edits are `set_points` with a full points table, `append_round`
with a unique id and authored course, `replace_round` with an existing id
and a replacement course, and `remove_last` with the id of the final round.
Each transaction has at most 16 edits and must leave a valid 1–8 round
season. A new course must satisfy the original world's collision geometry,
ordered checkpoints, deadline and medal thresholds.

Pass `--preview-season-record <record.json>` to protect earned progress.
The editor independently verifies that save, refuses to rescore any earned
round, and refuses to remove or rewrite any completed course. It rebuilds
the player preview using the revised season and the actual saved game
replays, so a newly appended round appears as playable but unearned.

Example:

```sh
python -m skeleton.game.gameplay.harbor_crafting_cli season-author \
  --source world.json --season season.json --season-edits edits.json \
  --expected-source-digest SOURCE_SHA256 \
  --expected-season-digest SEASON_SHA256 \
  --preview-season-record earned.json > revision.json
python -m skeleton.game.gameplay.harbor_crafting_cli season-verify-author \
  --season-revision revision.json
```

The revision digest detects corruption, not malicious substitution or
identity fraud. The caller must store the new revision and new season
atomically if persistence is needed. Source/game replay remains canonical.
Focused regression: `pytest -q skeleton/testing/test_harbor_crafting_season_authoring.py`.
