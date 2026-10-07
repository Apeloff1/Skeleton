"""
╔════════════════════════════════════════════════════════════════════════╗
║  ASSET FORGE — 10× assets per gamefile, folded into the Vault.          ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Every forged item spawns a full 10-asset production pack (sprite, normal║
║  map, icon, thumbnail, sfx, vfx, material, LOD mesh, anim clip, palette  ║
║  swatch) so a creator gets a ready-to-drop asset bundle alongside the    ║
║  GDD. Deterministic (seed-reproducible) descriptors grounded in the      ║
║  item's skin/palette.                                                    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

# The 10× asset pack — one of each per forged item.
ASSET_TYPES: list[tuple[str, str, str]] = [
    ("sprite_sheet", "png", "2048x2048"),
    ("normal_map", "png", "1024x1024"),
    ("icon", "png", "256x256"),
    ("thumbnail", "webp", "512x512"),
    ("sfx", "ogg", "stereo 48kHz"),
    ("vfx", "json", "particle-graph"),
    ("material", "json", "pbr"),
    ("lod_mesh", "glb", "3 LODs"),
    ("anim_clip", "json", "30fps"),
    ("palette_swatch", "aco", "8-swatch"),
]


def _rng(*parts: Any) -> random.Random:
    key = "|".join(str(p) for p in parts)
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


def forge_assets_for_item(item: dict, seed: int = 0, era: str | None = None) -> list[dict]:
    """Forge the era-appropriate asset pack for ONE item, grounded in its skin.
    The era decides WHICH asset types exist (2D eras skip meshes/normal maps)
    and each asset's format, dimensions, size and polygon budget."""
    from core import eras as _eras
    skin = item.get("skin") or {}
    era_key = era or skin.get("era")
    era_spec = _eras.get_era(era_key)
    allowed = set(era_spec["asset_types"])
    applied = skin.get("applied_choices") or {}
    # Dimension choice: a 2D game forges no 3D geometry assets.
    if str(applied.get("dimension", "")).lower() in (
            "2d", "two_d", "2", "pixel", "side_2d", "topdown_2d"):
        allowed -= {"lod_mesh", "normal_map"}
    palette = skin.get("palette") or ["#888888"]
    item_id = item.get("item_id", "itm_x")
    stage = item.get("stage", "—")
    assets: list[dict] = []
    for idx, (atype, _fmt, _spec) in enumerate(ASSET_TYPES):
        if atype not in allowed:
            continue  # not produced in this era
        rng = _rng("asset", item_id, atype, seed, era_spec["key"])
        spec = _eras.asset_spec(era_spec["key"], atype, rng)
        aid = "ast_" + hashlib.sha256(
            f"{item_id}{atype}{seed}{era_spec['key']}".encode()).hexdigest()[:10]
        assets.append({
            "asset_id": aid,
            "item_id": item_id,
            "stage": stage,
            "type": atype,
            "format": spec["format"],
            "dims": spec["dims"],
            "spec": _spec,
            "era": era_spec["key"],
            "era_label": era_spec["label"],
            "palette": palette,
            "material": skin.get("material"),
            "vfx_hint": skin.get("vfx"),
            "poly": spec["poly"],
            "lod": idx % 3 if atype == "lod_mesh" else None,
            "size_kb": spec["size_kb"],
            "checksum": hashlib.md5(f"{aid}{spec['dims']}".encode()).hexdigest()[:12],  # noqa: S324
            "filename": f"{item_id}_{atype}.{spec['format']}",
            "applied_choices": dict(applied),
        })
    return assets


def forge_build_assets(build_id: str, items: list[dict], seed: int = 0,
                       persist: bool = True, era: str | None = None) -> dict:
    """Forge the era-appropriate asset pack for EVERY item; fold into the Vault."""
    all_assets: list[dict] = []
    by_type: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    total_bytes = 0
    for it in items:
        pack = forge_assets_for_item(it, seed, era)
        all_assets.extend(pack)
        for a in pack:
            by_type[a["type"]] = by_type.get(a["type"], 0) + 1
            by_stage[a["stage"]] = by_stage.get(a["stage"], 0) + 1
            total_bytes += int(a["size_kb"]) * 1024

    if persist and all_assets:
        try:
            from core.databases import get_sync_db
            col = get_sync_db()["galaxy_build_assets"]
            col.create_index([("build_id", 1), ("item_id", 1)])
            for a in all_assets:
                col.update_one(
                    {"build_id": build_id, "asset_id": a["asset_id"]},
                    {"$set": {**a, "build_id": build_id}}, upsert=True)
        except Exception:
            pass

    from core import eras as _eras
    era_spec = _eras.get_era(era or (items[0].get("skin", {}).get("era") if items else None))
    return {
        "build_id": build_id,
        "era": era_spec["key"], "era_label": era_spec["label"],
        "total_assets": len(all_assets),
        "assets_per_item": len(era_spec["asset_types"]),
        "items": len(items),
        "total_bytes": total_bytes,
        "total_size": _eras.humanize_bytes(total_bytes),
        "by_type": [{"type": k, "count": by_type[k]} for k in sorted(by_type)],
        "by_stage": [{"stage": k, "count": v} for k, v in by_stage.items()],
        "assets": all_assets,
    }


def list_assets(build_id: str, item_id: str | None = None, limit: int = 500) -> list[dict]:
    try:
        from core.databases import get_sync_db
        q: dict = {"build_id": build_id}
        if item_id:
            q["item_id"] = item_id
        return list(get_sync_db()["galaxy_build_assets"]
                    .find(q, {"_id": 0}).limit(max(1, min(limit, 2000))))
    except Exception:
        return []
