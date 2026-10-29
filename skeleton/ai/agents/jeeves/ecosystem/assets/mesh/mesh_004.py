"""mesh asset 004.
"""
from __future__ import annotations

ASSET_ID = "mesh_004"
ERA_HINT = ["NES", "SNES", "N64", "PS1", "PS2", "ash", "crystal"][4 % 7]

def describe() -> dict:
    return {"id": ASSET_ID, "kind": "mesh", "era": ERA_HINT, "lod": 0}

def respray(target_era: str) -> dict:
    if not target_era:
        return {"ok": False, "reason": "empty_era"}
    return {"ok": True, "id": ASSET_ID, "from": ERA_HINT, "to": target_era, "fidelity": 0.93}
