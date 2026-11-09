"""Original text-asset theme contracts; no executable or external asset ingestion."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage import validate_salvage_board

SCHEMA = "skeleton.game.harbor.salvage-assets.v1"
MAX_BYTES = 16384
GLYPHS = {"wall", "floor", "fog", "player", "npc", "dock", "site"}
FIELDS = {"schema", "source_id", "glyphs", "labels"}


def validate_salvage_assets(assets: Any, source: Any, board: Any) -> dict[str, Any]:
    authored = validate_salvage_board(board, source)
    _keys(assets, FIELDS, "salvage text assets")
    if assets["schema"] != SCHEMA or assets["source_id"] != source["id"]:
        raise HarborError("salvage assets source mismatch")
    if len(canonical(assets)) > MAX_BYTES:
        raise HarborError("salvage assets byte budget exceeded")
    _keys(assets["glyphs"], GLYPHS, "salvage glyph set")
    glyphs = list(assets["glyphs"].values())
    if (any(type(g) is not str or len(g) != 1 or not 33 <= ord(g) <= 126
            for g in glyphs) or len(set(glyphs)) != len(glyphs)):
        raise HarborError("invalid or ambiguous salvage glyphs")
    labels = assets["labels"]
    names = {site["id"] for site in authored["sites"]}
    if not isinstance(labels, dict) or set(labels) != names:
        raise HarborError("salvage site labels do not match authored sites")
    for name, label in labels.items():
        _identifier(name, "salvage asset site id")
        if (type(label) is not str or not 1 <= len(label) <= 80
                or any(ord(c) < 32 or ord(c) == 127 for c in label)):
            raise HarborError("invalid salvage site label")
    return deepcopy(assets)


def salvage_asset_manifest(assets: Any, source: Any, board: Any) -> dict[str, Any]:
    validated = validate_salvage_assets(assets, source, board)
    return {"schema": SCHEMA, "source_id": validated["source_id"],
            "asset_count": len(GLYPHS) + len(validated["labels"]),
            "assets_digest": digest(validated)}
