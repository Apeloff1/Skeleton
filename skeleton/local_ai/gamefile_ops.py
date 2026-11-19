"""
Create, validate, convert, and pack game source files for Skeleton GameForge emits. Godot 4 pack trees, world.tscn, data catalogs, provenance meta, headless checks.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

PACKS = ["project.godot", "world.tscn"]


def process(data: dict) -> dict:
    refused = admit("gamefile_ops", data)
    if refused:
        return refused
    pack = data.get("pack")
    if pack is None:
        return stamp("gamefile_ops", data, {"packs": PACKS})
    if pack not in PACKS:
        return {
            "ok": False,
            "error": "unknown pack",
            "card": "gamefile_ops",
            "packs": list(PACKS),
        }
    return stamp("gamefile_ops", data, {"packs": PACKS, "pack": pack})
