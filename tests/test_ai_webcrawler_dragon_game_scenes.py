"""Stub for dragon game scenes fixtures."""
from typing import Any
GODOT = "godot"
UNITY = "unity"
USDA = "usda"
LDRAW = "ldraw"
def game_scene(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "game_scene"}
