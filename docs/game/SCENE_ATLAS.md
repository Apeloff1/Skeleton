# Scene atlas: playable exploration and offline map export

The installed `python -m skeleton scene-atlas` command derives a fog-of-war
map from actual source-bound scene traversal. It never fabricates exploration,
unlocks an item gate, reads external files or executes authored scripts.

## Gameplay flow

```bash
python -m skeleton scene-travel demo
python -m skeleton scene-atlas demo
```

The scene-travel engine remains authoritative for moves, pickups, inventory,
endings and save lineage. Scene atlas replay-verifies the save before exposing
visited rooms, visible pickups and exits, actual collected items, source-bound
turn history, current room and terminal ending.

`inspect --session-json '<saved-session>'` shows the current explored map.
`route --session-json '<saved-session>' --target-scene gate` searches only
previously visited rooms, respecting current inventory and authored item
requirements. Undiscovered rooms are not traversed or revealed as route nodes.
The result is a suggestion, not a movement grant; the player must still
perform legal scene-travel actions.

`compare --left-json ... --right-json ...` compares two verified sessions
from identical authored source and reports common replay prefix, discovered
rooms and item differences. `export --session-json ...` packages the
authoritative save with a derived map. `verify --bundle-json ...` replays
the save and recomputes the map; a recomputed checksum over forged map data
does not bypass canonical verification.

## Limits and security

The canonical world has at most 128 scenes and 512 actions. Route search is
breadth-first, visits each discovered room at most once, and does not traverse
unknown destinations. Portable bundles are capped at 2 MiB, with strict
JSON parsing, source digests, exact field sets and checksum consistency.
Hashes are not authenticity signatures; the caller still enforces project
ownership, source provenance and authorization.

## Acceptance

```bash
python -m pytest -q skeleton/testing/test_scene_atlas.py
```

Regression coverage includes visited-only visibility, item gates, real
history, alternate endings, branch comparison, source mismatch, replay
tampering, recomputed forged-map checksums, CLI and portable import/export.
Device qualification and full exact-head CI remain separate requirements.
