# Offline mission consequence audit

`scene-consequences` makes authored choices and their downstream effects
inspectable. It replays the canonical mission/event director to attribute
each reputation change, newly completed quest, scene transition and ending
to its exact original action receipt. No player-reported reputation or
client-provided ending is accepted as authority.

```sh
python -m skeleton scene-consequences demo
python -m skeleton scene-consequences inspect --session-json "$MISSION_SAVE"
python -m skeleton scene-consequences compare --left-json "$LEFT_SAVE" --right-json "$RIGHT_SAVE"
python -m skeleton scene-consequences export --left-json "$LEFT_SAVE" --right-json "$RIGHT_SAVE"
python -m skeleton scene-consequences import --bundle-json "$BUNDLE"
```

Comparison requires identical authored mission source digests. It reports
the common action prefix, divergent choice decisions, missions unique to
either path, earned endings, reputation deltas and state receipts. Portable
exports include both bounded original replay witnesses, the recomputed
comparison and a checksum. Import independently replays both histories and
rejects forged consequences even if the attacker recomputes the checksum.

The original Lantern Harbor example contrasts restoring the lantern
against declining the pledge and taking an unpledged victory. All paths are
source-authored; no third-party game content or generated filler is used.
Digest integrity does not establish author identity or user authorization.

Acceptance: `python -m pytest -q skeleton/testing/test_scene_mission_consequences.py`.
Exact-head CI, rights review and consumer/device release qualification remain
separate requirements.
