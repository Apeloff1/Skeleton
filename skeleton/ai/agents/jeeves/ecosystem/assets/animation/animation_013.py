"""animation asset 013.
"""
from __future__ import annotations

ASSET_ID = "animation_013"
ERA_HINT = ["NES", "SNES", "N64", "PS1", "PS2", "ash", "crystal"][13 % 7]

def describe() -> dict:
    return {"id": ASSET_ID, "kind": "animation", "era": ERA_HINT, "lod": 1}

def respray(target_era: str) -> dict:
    if not target_era:
        return {"ok": False, "reason": "empty_era"}
    return {"ok": True, "id": ASSET_ID, "from": ERA_HINT, "to": target_era, "fidelity": 0.93}
