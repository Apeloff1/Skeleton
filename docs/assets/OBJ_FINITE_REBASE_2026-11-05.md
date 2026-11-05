# OBJ Non-finite Vertex Rejection Rebase

Source: PR #4636 (conflicted on automated update).

Required change in skeleton/game/build/asset_ingest/importers.py _obj:
- After float conversion of vertex args, check math.isfinite on all axes.
- Raise AssetImportError on non-finite before appending to verts.

Corresponding tests in tests/game_asset_ingest/test_asset_ingest.py for NaN/Infinity/-Infinity/1e309.

Apply on exact current main head, then exact-head CI. No padding.
