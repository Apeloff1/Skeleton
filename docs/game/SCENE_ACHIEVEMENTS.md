# Replay-derived scene achievements

A standalone authored achievement catalog binds to the canonical world source
digest. It can be evaluated on any verified partial or completed scene-travel
save. Each milestone records its **first replayed tick**, the exact state digest
and the originating action receipt. A starting-scene milestone is earned at
tick zero. No unverified client claim can grant an achievement.

Supported conditions are `visit_scene`, `collect_item`, `ending` (victory
or failure), and `finish_within` (positive maximum step count). Source
validation rejects duplicate identifiers, unknown authored scenes/items,
unknown conditions and invalid thresholds. Rules are declarative data only.

```sh
python -m skeleton scene-achievements demo
python -m skeleton scene-achievements inspect --session-json "$SESSION" --catalog-json "$CATALOG"
python -m skeleton scene-achievements export --session-json "$SESSION" --catalog-json "$CATALOG"
python -m skeleton scene-achievements import --bundle-json "$BUNDLE"
```

The portable bundle includes the canonical session, catalog, derived report,
source/state identity and a bounded 2 MiB checksum. Import replays the entire
session and independently recomputes every achievement; recalculating a
checksum over fabricated achievements does not make them valid. Hashes are
integrity checks, not trusted author signatures or authorization grants.

Acceptance: `python -m pytest -q skeleton/testing/test_scene_achievements.py`.
Require exact-head CI, independent gameplay review and release gates.
